from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models
from datetime import timedelta
import logging
from monitoring.models import (
    DyeingIdentity, DataAnomaly, AnomalyThresholdMaster, 
    AnomalyRuleConfig, AnomalySeverityLevel, MachineMinuteLog
)
from monitoring.utils.batch_analyzer import detect_multi_heating_cycles

logger = logging.getLogger(__name__)


def evaluate_identity_anomaly(r, rules=None, severities=None):
    """
    Mengevaluasi satu record DyeingIdentity yang sudah terhubung ke DyeingProcess & Program.
    Mendeteksi:
    1. Deviasi terhadap AnomalyThresholdMaster (SUHU, HEAT, KEEP, COOL, SUHU_HARD)
    2. Deteksi Forensik Bagian 5.1:
       - REHEATING (Pemanasan berulang >= 2x siklus)
       - OVER_HOLD (Over-holding suhu puncak > 8 menit)
       - LATE_STOP (Durasi pasca-cooling <70°C s/d OFF > 45 menit)
       - COOL_STAGNATION (Stagnasi fase cooling >= 15 menit di suhu >= 70°C)
       - SLOW_COOL (Cooling lambat melebihi target)
       - MID_HEAT_PAUSE (Jeda / stagnasi di tengah fase heating)
       - START_TEMP_HIGH (Suhu awal pengisian > 60°C)
    Return: ('inserted' | 'updated' | 'none', anomaly_obj_or_None)
    """
    if not (r.dyeing_process_id and r.program_id and r.dyeing_process.is_valid_process):
        return 'none', None

    machine = r.machine
    if not machine or machine.code.startswith('Temp_') or machine.code in ('Steam_Pr', 'Oil_Temp', 'Batu_Bara'):
        return 'none', None

    program = r.program
    b = r.dyeing_process

    if rules is None:
        rules = list(AnomalyRuleConfig.objects.filter(is_active=True))
    if severities is None:
        severities = list(AnomalySeverityLevel.objects.order_by('-min_flags_required'))

    master = AnomalyThresholdMaster.objects.filter(machine=machine, program=program).first()

    flags = []
    forced_severity = None

    diff_suhu = (b.max_temp - program.suhu_max) if program.suhu_max and b.max_temp else None
    diff_heat = (b.heating_duration - program.durasi_heating_ideal) if program.durasi_heating_ideal and b.heating_duration is not None else None
    diff_keep = (b.steady_duration - program.durasi_keeping_ideal) if program.durasi_keeping_ideal and b.steady_duration is not None else None
    diff_cool = (b.cooling_duration - program.durasi_cooling_ideal) if program.durasi_cooling_ideal and b.cooling_duration is not None else None

    # 1. Deviasi Master Threshold
    if master:
        if diff_suhu is not None and master.suhu_lower_bound is not None and master.suhu_upper_bound is not None:
            if diff_suhu < master.suhu_lower_bound or diff_suhu > master.suhu_upper_bound:
                flags.append('SUHU')
        if diff_heat is not None and master.heat_lower_bound is not None and master.heat_upper_bound is not None:
            if diff_heat < master.heat_lower_bound or diff_heat > master.heat_upper_bound:
                flags.append('HEAT')
        if diff_keep is not None and master.keep_lower_bound is not None and master.keep_upper_bound is not None:
            if diff_keep < master.keep_lower_bound or diff_keep > master.keep_upper_bound:
                flags.append('KEEP')
        if diff_cool is not None and master.cool_lower_bound is not None and master.cool_upper_bound is not None:
            if diff_cool < master.cool_lower_bound or diff_cool > master.cool_upper_bound:
                flags.append('COOL')

    # Hard Limit Suhu (> 25°C)
    if diff_suhu is not None and abs(diff_suhu) > 25:
        if 'SUHU_HARD' not in flags:
            flags.append('SUHU_HARD')
        forced_severity = 'CRITICAL'

    # 2. Forensik 5.1: Multi-Heating / Re-Heating
    multi_heat = detect_multi_heating_cycles(b)
    if multi_heat['is_multi_heating']:
        if 'REHEATING' not in flags:
            flags.append('REHEATING')
        forced_severity = 'CRITICAL' if multi_heat['reheat_extra_mins'] > 120 else 'HIGH'

    # 3. Forensik 5.1: Over-Holding Suhu Puncak (> 8 menit)
    keep_ideal_m = (program.durasi_keeping_ideal or 0.0) if program else 0.0
    hold_dur = b.steady_duration or 0.0
    over_hold_mins = max(0.0, hold_dur - keep_ideal_m) if keep_ideal_m > 0 else 0.0
    if keep_ideal_m > 0 and over_hold_mins > 8:
        if 'OVER_HOLD' not in flags:
            flags.append('OVER_HOLD')
        if over_hold_mins > 25:
            forced_severity = 'CRITICAL'
        elif not forced_severity:
            forced_severity = 'MEDIUM'

    # 4. Forensik 5.1: Late Stop Pasca-Cooling (> 45 menit)
    late_stop_mins = 0.0
    if b.reached_70c_time and b.end_time and b.end_time > b.reached_70c_time:
        late_stop_mins = max(0.0, (b.end_time - b.reached_70c_time).total_seconds() / 60.0)
    if late_stop_mins > 45:
        if 'LATE_STOP' not in flags:
            flags.append('LATE_STOP')
        if late_stop_mins > 60:
            forced_severity = 'CRITICAL'
        elif not forced_severity:
            forced_severity = 'MEDIUM'

    # 5. Forensik 5.1: Stagnasi Fase Cooling & Slow Cooling
    cool_ideal_m = (program.durasi_cooling_ideal or 0.0) if program else 0.0
    cool_dur = b.cooling_duration or 0.0
    cool_overrun_mins = max(0.0, cool_dur - cool_ideal_m) if cool_ideal_m > 0 else 0.0
    cooling_stagnant_mins = 0.0

    if b.cooling_start_time and not multi_heat['is_multi_heating'] and (cool_overrun_mins > 10 or cool_dur > 35):
        c_end_bound = b.reached_70c_time or b.end_time
        if c_end_bound:
            cool_logs = list(MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__range=(b.cooling_start_time, c_end_bound),
                temperature__gte=70.0
            ).order_by('timestamp').values_list('timestamp', 'temperature'))
            if len(cool_logs) >= 10:
                stag_indices = []
                win = 5
                for idx in range(win, len(cool_logs)):
                    t_prev = cool_logs[idx - win][1]
                    t_curr = cool_logs[idx][1]
                    if t_prev is not None and t_curr is not None:
                        dt_m = max(1.0, (cool_logs[idx][0] - cool_logs[idx - win][0]).total_seconds() / 60.0)
                        drop_rate = (t_prev - t_curr) / dt_m
                        if drop_rate < 0.08:
                            stag_indices.append(idx)
                if stag_indices:
                    cooling_stagnant_mins = float(len(stag_indices))
                    if cooling_stagnant_mins >= 15:
                        flags.append('COOL_STAGNATION')
                        if cooling_stagnant_mins >= 30 or cool_overrun_mins >= 45:
                            forced_severity = 'CRITICAL'
                        elif not forced_severity:
                            forced_severity = 'MEDIUM'

    if 'COOL_STAGNATION' not in flags and not multi_heat['is_multi_heating'] and cool_dur > 0:
        if (cool_ideal_m > 0 and cool_overrun_mins > 15 and cool_dur > cool_ideal_m * 1.4) or (cool_ideal_m == 0 and cool_dur > 45):
            flags.append('SLOW_COOL')
            co_m = cool_overrun_mins if cool_ideal_m > 0 else (cool_dur - 30.0)
            if co_m >= 40:
                forced_severity = 'CRITICAL'
            elif not forced_severity:
                forced_severity = 'MEDIUM'

    # 6. Forensik 5.1: Mid-Heating Pause
    heat_span = b.heating_span or 0.0
    heat_dur = b.real_heating_duration or b.heating_duration or 0.0
    if heat_span > 0 and heat_dur > 0 and (heat_span - heat_dur) > 10:
        flags.append('MID_HEAT_PAUSE')
        if not forced_severity:
            forced_severity = 'MEDIUM'

    # 7. Forensik 5.1: Suhu Awal Tinggi (> 60°C)
    if b.start_temp and b.start_temp > 60:
        flags.append('START_TEMP_HIGH')
        if not forced_severity:
            forced_severity = 'MEDIUM'

    for rule in rules:
        if rule.rule_type == 'THRESHOLD_DIFF':
            params = rule.parameter_json
            if 'max_absolute_diff' in params:
                limit = params['max_absolute_diff']
                if diff_suhu is not None and abs(diff_suhu) > limit:
                    if rule.adds_flag not in flags:
                        flags.append(rule.adds_flag)
                    if rule.forces_severity != 'NONE':
                        forced_severity = rule.forces_severity

    if not flags:
        return 'none', None

    # Tentukan anomaly_type utama yang deskriptif
    if 'REHEATING' in flags:
        anomaly_type = 'REHEATING'
    elif 'OVER_HOLD' in flags or 'LATE_STOP' in flags:
        anomaly_type = 'OPERATIONAL_DELAY'
    elif 'COOL_STAGNATION' in flags or 'SLOW_COOL' in flags:
        anomaly_type = 'COOLING_ANOMALY'
    elif 'MID_HEAT_PAUSE' in flags:
        anomaly_type = 'HEATING_ANOMALY'
    elif 'START_TEMP_HIGH' in flags:
        anomaly_type = 'PROCEDURAL_ANOMALY'
    elif 'SUHU_HARD' in flags:
        anomaly_type = 'TEMPERATURE_OUTLIER'
    elif any(f in flags for f in ('SUHU', 'HEAT', 'KEEP', 'COOL')):
        anomaly_type = 'STATISTICAL_DEVIATION'
    else:
        anomaly_type = 'PROCESS_ANOMALY'

    final_severity = 'LOW'
    if forced_severity:
        final_severity = forced_severity
    else:
        flag_count = len(flags)
        for sev in severities:
            if flag_count >= sev.min_flags_required:
                final_severity = sev.severity_name
                break

    details = {
        'flags': flags,
        'diffs': {
            'suhu': diff_suhu,
            'heat': diff_heat,
            'keep': diff_keep,
            'cool': diff_cool,
        },
        'actuals': {
            'suhu': b.max_temp,
            'heat': b.heating_duration,
            'real_heat': b.real_heating_duration,
            'keep': b.steady_duration,
            'cool': b.cooling_duration,
            'start_temp': b.start_temp,
            'late_stop_mins': round(late_stop_mins, 1),
            'over_hold_mins': round(over_hold_mins, 1),
            'cooling_stagnant_mins': round(cooling_stagnant_mins, 1),
        },
        'ideals': {
            'suhu': program.suhu_max,
            'heat': program.durasi_heating_ideal,
            'keep': program.durasi_keeping_ideal,
            'cool': program.durasi_cooling_ideal,
        },
    }
    if multi_heat['is_multi_heating']:
        details['multi_heating'] = {
            'cycle_count': multi_heat['cycle_count'],
            'reheat_extra_mins': multi_heat['reheat_extra_mins'],
            'final_cooling_mins': multi_heat['final_cooling_mins'],
            'valleys': [
                {
                    'cool_start_str': v['cool_start_str'],
                    'valley_str': v['valley_str'],
                    'valley_temp': v['valley_temp'],
                    'to_peak_temp': v['to_peak_temp'],
                }
                for v in multi_heat['valleys']
            ],
        }

    anomaly = DataAnomaly.objects.filter(
        models.Q(identity_record=r) | models.Q(process_record=b)
    ).first()
    if anomaly:
        if not anomaly.is_resolved:
            anomaly.anomaly_type = anomaly_type
            anomaly.severity = final_severity
            anomaly.details = details
            anomaly.identity_record = r
            anomaly.process_record = b
            anomaly.save()
            return 'updated', anomaly
        return 'none', anomaly
    else:
        anomaly = DataAnomaly.objects.create(
            identity_record=r,
            process_record=b,
            anomaly_type=anomaly_type,
            severity=final_severity,
            details=details,
        )
        return 'inserted', anomaly


class Command(BaseCommand):
    help = 'Deteksi anomali harian (berdasarkan Master Threshold & Kurva Multi-Heating)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=1, help='Jumlah hari ke belakang untuk reprocess')

    def handle(self, *args, **kwargs):
        self.stdout.write("Memulai deteksi anomali harian (V2 + Multi-Heating)...")
        days_back = kwargs['days']

        now = timezone.localtime(timezone.now())
        if now.hour < 6:
            end_time = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start_time = end_time - timedelta(days=days_back + 1)
        else:
            end_time = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start_time = end_time - timedelta(days=days_back)

        self.stdout.write(f"Rentang pencarian: {start_time} - {end_time}")

        qs = DyeingIdentity.objects.filter(
            dyeing_process__isnull=False,
            program__isnull=False,
            dyeing_process__is_valid_process=True,
            dyeing_process__start_time__gte=start_time,
            dyeing_process__start_time__lt=end_time
        ).select_related('machine', 'dyeing_process', 'program')

        rules = list(AnomalyRuleConfig.objects.filter(is_active=True))
        severities = list(AnomalySeverityLevel.objects.order_by('-min_flags_required'))

        inserted = 0
        updated = 0

        for r in qs:
            status_str, _ = evaluate_identity_anomaly(r, rules=rules, severities=severities)
            if status_str == 'inserted':
                inserted += 1
            elif status_str == 'updated':
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Selesai! {inserted} anomali baru, {updated} diupdate."))
