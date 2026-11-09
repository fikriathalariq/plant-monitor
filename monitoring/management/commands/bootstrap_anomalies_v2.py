from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging
import math
from django.db import transaction

from monitoring.models import (
    AnomalySeverityLevel, AnomalyRuleConfig, AnomalyThresholdMaster,
    DyeingIdentity, Machine, DyeingProcess
)

logger = logging.getLogger(__name__)

def get_iqr_bounds(data_list, metric_type='duration', multiplier=2.5):
    valid_data = sorted(x for x in data_list if x is not None)
    n = len(valid_data)
    
    if n < 4:
        return -9999.0, 9999.0

    def percentile(data, p):
        idx = (len(data) - 1) * p
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        frac = idx - lo
        return data[lo] + (data[hi] - data[lo]) * frac

    q1 = percentile(valid_data, 0.25)
    median = percentile(valid_data, 0.50)
    q3 = percentile(valid_data, 0.75)
    iqr = q3 - q1

    # Buffer Minimal Absolut: 1.5 derajat untuk Suhu, 5.0 menit untuk Durasi
    fallback = 1.5 if metric_type == 'suhu' else 5.0
    # Pastikan IQR minimal tidak pernah lebih kecil dari 10% median atau fallback absolut
    iqr = max(iqr, abs(median) * 0.10, fallback)

    return q1 - (multiplier * iqr), q3 + (multiplier * iqr)

class Command(BaseCommand):
    help = 'Seeding tabel konfigurasi anomali V2 dan kalibrasi awal (180 hari terakhir)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Memulai Bootstrap Anomali V2 (Robust IQR)...")
        
        with transaction.atomic():
            self.stdout.write("1. Mengisi AnomalySeverityLevel...")
            severities = [('CRITICAL', 3), ('MEDIUM', 2), ('LOW', 1)]
            for name, min_flags in severities:
                obj, created = AnomalySeverityLevel.objects.get_or_create(
                    severity_name=name, defaults={'min_flags_required': min_flags}
                )
                if not created and obj.min_flags_required != min_flags:
                    obj.min_flags_required = min_flags
                    obj.save()
                    
            self.stdout.write("2. Mengisi AnomalyRuleConfig...")
            rules = [{
                'code': 'HARD_TEMP_LIMIT', 'type': 'THRESHOLD_DIFF', 'params': {'max_absolute_diff': 25},
                'flag': 'SUHU_HARD', 'severity': 'CRITICAL'
            }]
            for r in rules:
                obj, created = AnomalyRuleConfig.objects.get_or_create(
                    rule_code=r['code'],
                    defaults={
                        'rule_type': r['type'], 'parameter_json': r['params'],
                        'adds_flag': r['flag'], 'forces_severity': r['severity'], 'is_active': True
                    }
                )

            self.stdout.write("3. Membentuk Baseline Master Threshold (data 180 hari terakhir)...")
            
            now = timezone.localtime(timezone.now())
            start_time = now - timedelta(days=180)
            
            qs = DyeingIdentity.objects.filter(
                dyeing_process__isnull=False,
                program__isnull=False,
                dyeing_process__is_valid_process=True,
                dyeing_process__start_time__gte=start_time,
                dyeing_process__start_time__lte=now
            ).select_related('machine', 'dyeing_process', 'program')
            
            data_map = {}
            for r in qs:
                key = (r.machine_id, r.program_id)
                if key not in data_map:
                    data_map[key] = []
                data_map[key].append(r)
                
            masters_created = 0
            masters_updated = 0
            
            def welford_update(count, mean, m2, new_value):
                if new_value is None: return count, mean, m2
                count += 1
                delta = new_value - mean
                mean += delta / count
                delta2 = new_value - mean
                m2 += delta * delta2
                return count, mean, m2
                
            def calc_bounds(n, m, m2, z=3):
                if n < 2: return m, 0.0, None, None
                stddev = math.sqrt(m2 / (n - 1))
                return m, stddev, m - (z * stddev), m + (z * stddev)

            for (machine_id, program_id), records in data_map.items():
                master, created = AnomalyThresholdMaster.objects.get_or_create(
                    machine_id=machine_id, program_id=program_id, defaults={'update_mode': 'AUTO'}
                )
                
                raw_records = []
                suhu_vals, heat_vals, keep_vals, cool_vals = [], [], [], []
                
                for r in records:
                    b = r.dyeing_process
                    p = r.program
                    
                    if b.avg_steam_pressure is not None and b.avg_steam_pressure < 3.8:
                        continue
                        
                    ds = (b.max_temp - p.suhu_max) if p.suhu_max and b.max_temp else None
                    dh = (b.heating_duration - p.durasi_heating_ideal) if p.durasi_heating_ideal and b.heating_duration is not None else None
                    dk = (b.steady_duration - p.durasi_keeping_ideal) if p.durasi_keeping_ideal and b.steady_duration is not None else None
                    dc = (b.cooling_duration - p.durasi_cooling_ideal) if p.durasi_cooling_ideal and b.cooling_duration is not None else None
                    
                    if ds is not None and abs(ds) > 50: continue # extreme impossible sanity check
                    
                    raw_records.append({'ds': ds, 'dh': dh, 'dk': dk, 'dc': dc})
                    if ds is not None: suhu_vals.append(ds)
                    if dh is not None: heat_vals.append(dh)
                    if dk is not None: keep_vals.append(dk)
                    if dc is not None: cool_vals.append(dc)
                
                suhu_lb, suhu_ub = get_iqr_bounds(suhu_vals, 'suhu')
                heat_lb, heat_ub = get_iqr_bounds(heat_vals, 'duration')
                keep_lb, keep_ub = get_iqr_bounds(keep_vals, 'duration')
                cool_lb, cool_ub = get_iqr_bounds(cool_vals, 'duration')
                
                pure_records = []
                for item in raw_records:
                    if item['ds'] is not None and (item['ds'] < suhu_lb or item['ds'] > suhu_ub): continue
                    if item['dh'] is not None and (item['dh'] < heat_lb or item['dh'] > heat_ub): continue
                    if item['dk'] is not None and (item['dk'] < keep_lb or item['dk'] > keep_ub): continue
                    if item['dc'] is not None and (item['dc'] < cool_lb or item['dc'] > cool_ub): continue
                    pure_records.append(item)
                
                n_suhu = n_heat = n_keep = n_cool = 0
                m_suhu = m_heat = m_keep = m_cool = 0.0
                m2_suhu = m2_heat = m2_keep = m2_cool = 0.0
                
                for a in pure_records:
                    n_suhu, m_suhu, m2_suhu = welford_update(n_suhu, m_suhu, m2_suhu, a['ds'])
                    n_heat, m_heat, m2_heat = welford_update(n_heat, m_heat, m2_heat, a['dh'])
                    n_keep, m_keep, m2_keep = welford_update(n_keep, m_keep, m2_keep, a['dk'])
                    n_cool, m_cool, m2_cool = welford_update(n_cool, m_cool, m2_cool, a['dc'])

                sm, sstd, sl, su = calc_bounds(n_suhu, m_suhu, m2_suhu, z=5)
                hm, hstd, hl, hu = calc_bounds(n_heat, m_heat, m2_heat, z=3)
                km, kstd, kl, ku = calc_bounds(n_keep, m_keep, m2_keep, z=3)
                cm, cstd, cl, cu = calc_bounds(n_cool, m_cool, m2_cool, z=3)
                
                master.suhu_count = n_suhu; master.suhu_mean = sm; master.suhu_m2 = m2_suhu; master.suhu_stddev = sstd; master.suhu_lower_bound = sl; master.suhu_upper_bound = su
                master.heat_count = n_heat; master.heat_mean = hm; master.heat_m2 = m2_heat; master.heat_stddev = hstd; master.heat_lower_bound = hl; master.heat_upper_bound = hu
                master.keep_count = n_keep; master.keep_mean = km; master.keep_m2 = m2_keep; master.keep_stddev = kstd; master.keep_lower_bound = kl; master.keep_upper_bound = ku
                master.cool_count = n_cool; master.cool_mean = cm; master.cool_m2 = m2_cool; master.cool_stddev = cstd; master.cool_lower_bound = cl; master.cool_upper_bound = cu
                
                master.save()
                
                if created: masters_created += 1
                else: masters_updated += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Selesai! {masters_created} Master baru dibuat, {masters_updated} Master diperbarui."))
