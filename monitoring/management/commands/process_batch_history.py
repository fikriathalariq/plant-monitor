"""
Advanced Batch Detection & Efficiency Analysis System (Fixed Cooling Logic)

Changes:
- Cooling Start Logic: Uses 'Forward Validation' on Raw Data.
  Finds a drop point, checks future 10 mins. If valid, locks it.
  (Steady Start logic left untouched as per user request).
"""

import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from monitoring.models import Machine, MachineMinuteLog, DyeingProcess

# Import shared batch analysis functions
from monitoring.utils.batch_analyzer import (
    BatchProcessingConfig,
    FilterState,
    BatchGradientProcessor,
    analyze_batch_details,
    calculate_ideal_time,
    pressure_to_steam_temp,
)


# ==========================================
# 5. DJANGO MANAGEMENT COMMAND
# ==========================================
class Command(BaseCommand):
    help = "Advanced Batch Detection v3.12 (Fixed Cooling Logic)"

    def add_arguments(self, parser):
        parser.add_argument("--machine", type=str, help="Machine code")
        parser.add_argument("--reprocess", action="store_true", help="Reprocess all history")
        parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
        parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")

    def handle(self, *args, **options):
        from datetime import datetime
        
        machine_code = options["machine"]
        reprocess = options["reprocess"]
        start_date_str = options.get("start_date")
        end_date_str = options.get("end_date")
        
        start_date = None
        end_date = None
        
        if start_date_str:
            try: start_date = timezone.make_aware(datetime.strptime(start_date_str, "%Y-%m-%d"))
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid start date: {start_date_str}"))
                return
        
        if end_date_str:
            try: end_date = timezone.make_aware(datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid end date: {end_date_str}"))
                return
        
        machines = Machine.objects.all()
        if machine_code: machines = machines.filter(code=machine_code)
        
        self.stdout.write("=" * 60)
        self.stdout.write("  BATCH PROCESSOR v3.12 (FIXED COOLING)")
        self.stdout.write("=" * 60)
        
        for m in machines:
            self.stdout.write(f"\n[{m.code}] {m.name}")
            logs = MachineMinuteLog.objects.filter(machine=m).order_by("timestamp")
            
            if reprocess:
                delete_query = DyeingProcess.objects.filter(machine=m)
                if start_date: delete_query = delete_query.filter(start_time__gte=start_date)
                if end_date: delete_query = delete_query.filter(start_time__lte=end_date)
                cnt = delete_query.count()
                
                from monitoring.models import DataAnomaly
                from django.core.cache import cache
                for b_del in delete_query:
                    cache.set(f"dyeing_process_meta_{b_del.id}", {
                        "machine": m.code,
                        "batch": b_del.batch_number,
                    }, timeout=259200)
                DataAnomaly.objects.filter(process_record__in=delete_query).delete()
                
                delete_query.delete()
                self.stdout.write(f"  -> Reprocess: Deleted {cnt} batches.")
            else:
                last_batch = DyeingProcess.objects.filter(machine=m).order_by('-end_time').first()
                if last_batch and last_batch.end_time:
                    start_check = last_batch.end_time - timedelta(hours=2)
                    logs = logs.filter(timestamp__gte=start_check)
                    self.stdout.write(f"  -> Incremental: Logs since {start_check}")
                else:
                    self.stdout.write("  -> Full Processing.")
            
            if start_date: logs = logs.filter(timestamp__gte=start_date)
            if end_date: logs = logs.filter(timestamp__lte=end_date)

            if not logs.exists():
                self.stdout.write("  -> No logs found.")
                continue
            
            self.process_machine(m, logs)

    def process_machine(self, machine, logs):
        config = BatchProcessingConfig()
        processor = BatchGradientProcessor(config)
        
        last_batch = DyeingProcess.objects.filter(machine=machine).order_by('-batch_number').first()
        next_batch_num = (last_batch.batch_number + 1) if last_batch else 1
        
        self.stdout.write("  -> Filtering...")
        
        processed_logs = []
        state = FilterState()
        prev_timestamp = None
        consecutive_gap_minutes = 0.0
        
        for log in logs.iterator(chunk_size=2000):
            dt_minutes = (log.timestamp - prev_timestamp).total_seconds()/60.0 if prev_timestamp else 1.0
            dt_minutes = max(0.5, dt_minutes)
            
            kx, gx, st, state, consecutive_gap_minutes = processor.process_single_with_grace(
                log.temperature, state, dt_minutes, consecutive_gap_minutes
            )
            
            processed_logs.append({
                'timestamp': log.timestamp,
                'filtered_temp': kx or 0.0,
                'gradient': gx,
                'state': st,
                'raw_temp': log.temperature or 0.0
            })
            prev_timestamp = log.timestamp
        
        pressure_map = {}
        if processed_logs:
            min_t, max_t = processed_logs[0]['timestamp'], processed_logs[-1]['timestamp']
            try:
                steam_logs = MachineMinuteLog.objects.filter(
                    machine__code="Steam_Pr", timestamp__range=(min_t, max_t)
                ).values('timestamp', 'temperature')
                pressure_map = {
                    l['timestamp'].replace(second=0, microsecond=0): l['temperature'] 
                    for l in steam_logs if l['temperature']
                }
            except:
                pass

        self.stdout.write("  -> Segmenting...")
        
        in_batch = False
        curr_start_time = None
        curr_start_idx = 0
        curr_peak = 0.0
        curr_peak_idx = 0
        has_cooling_phase = False
        batches_created = 0
        last_batch_end_idx = 0
        
        for i in range(1, len(processed_logs)):
            log = processed_logs[i]
            prev_log = processed_logs[i-1]
            state = log['state']
            temp = log['filtered_temp']
            
            if not in_batch:
                if state != "OFF" and prev_log['state'] == "OFF":
                    # Constraint: Never look back past the end of the previous batch
                    search_start = max(last_batch_end_idx, i - config.START_SEARCH_WINDOW)
                    window = processed_logs[search_start:i+1]
                    min_idx = min(range(len(window)), key=lambda idx: window[idx]['filtered_temp'])
                    actual_start_idx = search_start + min_idx
                    
                    in_batch = True
                    curr_start_idx = actual_start_idx
                    curr_start_time = processed_logs[actual_start_idx]['timestamp']
                    curr_peak = temp
                    curr_peak_idx = i
                    has_cooling_phase = False
            
            if in_batch:
                if temp > curr_peak:
                    curr_peak = temp
                    curr_peak_idx = i
                    has_cooling_phase = False
                
                if i > curr_peak_idx and state == "COOL":
                    has_cooling_phase = True
                
                if state == "OFF" and prev_log['state'] != "OFF":
                    if curr_peak > config.MIN_PEAK_TEMP:
                        self.save_batch(
                            machine, next_batch_num, processed_logs[curr_start_idx:i+1],
                            curr_start_time, log['timestamp'], curr_peak, config, pressure_map
                        )
                        next_batch_num += 1
                        batches_created += 1
                        last_batch_end_idx = i
                    in_batch = False
                    curr_peak = 0.0
                    has_cooling_phase = False
                
                elif state == "HEAT" and prev_log['state'] != "HEAT" and curr_peak > config.MIN_PEAK_TEMP:
                    if has_cooling_phase:
                        window = processed_logs[curr_peak_idx:i+1]
                        min_idx = min(range(len(window)), key=lambda idx: window[idx]['filtered_temp'])
                        min_temp = window[min_idx]['filtered_temp']
                        min_abs_idx = curr_peak_idx + min_idx
                        
                        if min_temp <= config.RESTART_TEMP:
                            self.save_batch(
                                machine, next_batch_num, processed_logs[curr_start_idx:min_abs_idx+1],
                                curr_start_time, processed_logs[min_abs_idx]['timestamp'], curr_peak, config, pressure_map
                            )
                            next_batch_num += 1
                            batches_created += 1
                            
                            curr_start_idx = min_abs_idx
                            curr_start_time = processed_logs[min_abs_idx]['timestamp']
                            curr_peak = temp
                            curr_peak_idx = i
                            has_cooling_phase = False
                            last_batch_end_idx = min_abs_idx
        
        if in_batch and curr_peak > config.MIN_PEAK_TEMP:
            self.save_batch(
                machine, next_batch_num, processed_logs[curr_start_idx:],
                curr_start_time, processed_logs[-1]['timestamp'], curr_peak, config, pressure_map, is_complete=False
            )
            batches_created += 1
            
        self.stdout.write(f"  -> Created {batches_created} batches.")

    def save_batch(self, machine, batch_num, batch_logs, start_time, end_time, peak_temp, config, pressure_map, is_complete=True):
        if DyeingProcess.objects.filter(machine=machine, batch_number=batch_num).exists():
             return

        metrics = analyze_batch_details(batch_logs, peak_temp, config, pressure_map)
        
        start_temp = batch_logs[0]['filtered_temp']
        end_temp = batch_logs[-1]['filtered_temp']
        
        rise_time = 0.0
        if metrics['heating_start_time'] and metrics['steady_start_time']:
            diff = (metrics['steady_start_time'] - metrics['heating_start_time']).total_seconds() / 60.0
            if diff > 0: rise_time = diff
            
        lag_time = 0.0
        if metrics['ideal_heating_time'] > 0 and rise_time > 0:
            lag_time = rise_time - metrics['ideal_heating_time']
        
        duration_effective = 0.0
        if metrics['heating_start_time']:
            if metrics['reached_70c_time']:
                duration_effective = (metrics['reached_70c_time'] - metrics['heating_start_time']).total_seconds() / 60.0
            else:
                duration_effective = (end_time - metrics['heating_start_time']).total_seconds() / 60.0

        heat_grads = [l['gradient'] for l in batch_logs if l['state'] == 'HEAT']
        avg_heat_grad = sum(heat_grads)/len(heat_grads) if heat_grads else 0.0
        cool_grads = [l['gradient'] for l in batch_logs if l['state'] == 'COOL']
        avg_cool_grad = sum(cool_grads)/len(cool_grads) if cool_grads else 0.0

        # === KALKULASI KONSUMSI DAYA (kWh) & TAGIHAN WBP/LWBP ===
        nominal_power = machine.nominal_power
        ref_start = metrics.get('heating_start_time') or start_time
        power_consumption = None
        
        power_wbp = None
        power_lwbp = None
        cost_wbp = None
        cost_lwbp = None
        cost_total = None
        
        if ref_start and end_time and nominal_power is not None and nominal_power > 0:
            duration_hours = (end_time - ref_start).total_seconds() / 3600.0
            if duration_hours > 0:
                power_consumption = round(duration_hours * nominal_power, 2)
                
                from monitoring.models import GlobalSettings
                settings = GlobalSettings.objects.first()
                if settings:
                    from datetime import datetime, timedelta
                    from django.utils import timezone
                    
                    wbp_start = settings.wbp_start_time
                    wbp_end = settings.wbp_end_time
                    
                    current_date = ref_start.date()
                    end_date = end_time.date()
                    
                    total_wbp_seconds = 0
                    
                    while current_date <= end_date:
                        wbp_dt_start = timezone.make_aware(datetime.combine(current_date, wbp_start))
                        wbp_dt_end = timezone.make_aware(datetime.combine(current_date, wbp_end))
                        
                        overlap_start = max(ref_start, wbp_dt_start)
                        overlap_end = min(end_time, wbp_dt_end)
                        
                        if overlap_end > overlap_start:
                            total_wbp_seconds += (overlap_end - overlap_start).total_seconds()
                            
                        current_date += timedelta(days=1)
                        
                    wbp_hours = total_wbp_seconds / 3600.0
                    lwbp_hours = duration_hours - wbp_hours
                    
                    power_wbp = wbp_hours * nominal_power
                    power_lwbp = lwbp_hours * nominal_power
                    
                    cost_wbp = power_wbp * settings.electricity_base_rate * settings.wbp_multiplier
                    cost_lwbp = power_lwbp * settings.electricity_base_rate
                    cost_total = cost_wbp + cost_lwbp
        # ========================================================

        DyeingProcess.objects.create(
            machine=machine,
            batch_number=batch_num,
            start_time=start_time,
            end_time=end_time,
            
            heating_start_time=metrics['heating_start_time'],
            steady_start_time=metrics['steady_start_time'],
            cooling_start_time=metrics['cooling_start_time'],
            reached_70c_time=metrics['reached_70c_time'],
            
            heating_duration=sum(1 for l in batch_logs if l['state']=='HEAT'),
            heating_avg_gradient=round(avg_heat_grad, 4),
            steady_duration=metrics['steady_duration'],
            cooling_duration=round(metrics['cooling_70_duration'], 1),
            cooling_avg_gradient=round(avg_cool_grad, 4),
            
            start_temp=round(start_temp, 2),
            end_temp=round(end_temp, 2),
            max_temp=round(peak_temp, 2),
            
            avg_heating_efficiency=round(metrics['avg_heating_efficiency'], 5),
            heating_gradient_duration=metrics['real_heating_duration'],
            heating_span=round(metrics['heating_span'], 1),
            
            real_heating_duration=round(rise_time, 1),
            duration_effective=round(duration_effective, 1),
            ideal_heating_time=round(metrics['ideal_heating_time'], 1),
            heating_lag_time=round(lag_time, 1),
            avg_steam_temp=round(metrics['avg_steam_temp'], 1),
            avg_steam_pressure=round(metrics['avg_steam_pressure'], 2),

            # +++ NEW FIELDS +++
            machine_nominal_power=nominal_power,
            power_consumption_kwh=power_consumption,
            power_consumption_wbp_kwh=round(power_wbp, 2) if power_wbp is not None else None,
            power_consumption_lwbp_kwh=round(power_lwbp, 2) if power_lwbp is not None else None,
            power_cost_wbp=round(cost_wbp, 2) if cost_wbp is not None else None,
            power_cost_lwbp=round(cost_lwbp, 2) if cost_lwbp is not None else None,
            power_cost_total=round(cost_total, 2) if cost_total is not None else None,
            # ++++++++++++++++++
            
            is_complete=is_complete
        )