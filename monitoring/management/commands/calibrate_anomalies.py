import math
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from monitoring.models import AnomalyThresholdMaster, AnomalyThresholdProposal, DyeingIdentity, AnomalyRuleConfig

def get_iqr_bounds(data_list, metric_type='duration', multiplier=2.5):
    valid_data = sorted(x for x in data_list if x is not None)
    n = len(valid_data)
    
    if n < 4:
        return -99999.0, 99999.0

    def percentile(data, p):
        idx = (len(data) - 1) * p
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        frac = idx - lo
        return data[lo] + (data[hi] - data[lo]) * frac

    q1 = percentile(valid_data, 0.25)
    median = percentile(valid_data, 0.50)
    q3 = percentile(valid_data, 0.75)
    iqr = q3 - q1

    fallback = 1.5 if metric_type == 'suhu' else 5.0
    iqr = max(iqr, abs(median) * 0.10, fallback)

    return q1 - (multiplier * iqr), q3 + (multiplier * iqr)

class Command(BaseCommand):
    help = 'Kalibrasi mingguan batas anomali (Welford Update dengan IQR Filter)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Memulai Kalibrasi Mingguan V2...")
        
        now = timezone.localtime(timezone.now())
        end_time = now
        start_time = now - timedelta(days=7)
        
        qs = DyeingIdentity.objects.filter(
            dyeing_process__isnull=False,
            program__isnull=False,
            dyeing_process__is_valid_process=True,
            dyeing_process__start_time__gte=start_time,
            dyeing_process__start_time__lte=end_time
        ).select_related('machine', 'dyeing_process', 'program')
        
        data_map = {}
        for r in qs:
            key = (r.machine_id, r.program_id)
            if key not in data_map:
                data_map[key] = []
            data_map[key].append(r)
            
        proposals_created = 0
        skipped = 0

        with transaction.atomic():
            for (machine_id, program_id), records in data_map.items():
                master = AnomalyThresholdMaster.objects.filter(machine_id=machine_id, program_id=program_id).first()
                if not master:
                    master = AnomalyThresholdMaster.objects.create(
                        machine_id=machine_id, program_id=program_id, update_mode='AUTO'
                    )
                
                if master.update_mode == 'MANUAL':
                    AnomalyThresholdProposal.objects.create(
                        master=master, week_start_date=start_time.date(), week_end_date=end_time.date(),
                        status='AUTO_SKIPPED', warning_message='Di-skip karena Master diset MANUAL.'
                    )
                    skipped += 1
                    continue
                
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
                    
                    if ds is not None and abs(ds) > 50: continue
                    
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
                rejection_stats = {'suhu': 0, 'heat': 0, 'keep': 0, 'cool': 0, 'old_zscore': 0}
                total_processed = len(raw_records)
                
                for item in raw_records:
                    rejected = False
                    
                    if item['ds'] is not None and (item['ds'] < suhu_lb or item['ds'] > suhu_ub):
                        rejection_stats['suhu'] += 1
                        rejected = True
                    elif item['dh'] is not None and (item['dh'] < heat_lb or item['dh'] > heat_ub):
                        rejection_stats['heat'] += 1
                        rejected = True
                    elif item['dk'] is not None and (item['dk'] < keep_lb or item['dk'] > keep_ub):
                        rejection_stats['keep'] += 1
                        rejected = True
                    elif item['dc'] is not None and (item['dc'] < cool_lb or item['dc'] > cool_ub):
                        rejection_stats['cool'] += 1
                        rejected = True
                        
                    # Cek batas lama Z-Score (agar baseline master tidak perlahan geser)
                    if not rejected and master.suhu_count > 0:
                        if item['ds'] is not None and master.suhu_lower_bound is not None and master.suhu_upper_bound is not None:
                            if item['ds'] < master.suhu_lower_bound or item['ds'] > master.suhu_upper_bound:
                                rejected = True; rejection_stats['old_zscore'] += 1
                        elif item['dh'] is not None and master.heat_lower_bound is not None and master.heat_upper_bound is not None:
                            if item['dh'] < master.heat_lower_bound or item['dh'] > master.heat_upper_bound:
                                rejected = True; rejection_stats['old_zscore'] += 1
                        elif item['dk'] is not None and master.keep_lower_bound is not None and master.keep_upper_bound is not None:
                            if item['dk'] < master.keep_lower_bound or item['dk'] > master.keep_upper_bound:
                                rejected = True; rejection_stats['old_zscore'] += 1
                        elif item['dc'] is not None and master.cool_lower_bound is not None and master.cool_upper_bound is not None:
                            if item['dc'] < master.cool_lower_bound or item['dc'] > master.cool_upper_bound:
                                rejected = True; rejection_stats['old_zscore'] += 1
                    
                    if not rejected:
                        pure_records.append(item)
                        
                def welford_update(count, mean, m2, new_value):
                    if new_value is None: return count, mean, m2
                    count += 1
                    delta = new_value - mean
                    mean += delta / count
                    delta2 = new_value - mean
                    m2 += delta * delta2
                    return count, mean, m2
                    
                n_suhu = master.suhu_count; m_suhu = master.suhu_mean; m2_suhu = master.suhu_m2
                n_heat = master.heat_count; m_heat = master.heat_mean; m2_heat = master.heat_m2
                n_keep = master.keep_count; m_keep = master.keep_mean; m2_keep = master.keep_m2
                n_cool = master.cool_count; m_cool = master.cool_mean; m2_cool = master.cool_m2
                
                for a in pure_records:
                    n_suhu, m_suhu, m2_suhu = welford_update(n_suhu, m_suhu, m2_suhu, a['ds'])
                    n_heat, m_heat, m2_heat = welford_update(n_heat, m_heat, m2_heat, a['dh'])
                    n_keep, m_keep, m2_keep = welford_update(n_keep, m_keep, m2_keep, a['dk'])
                    n_cool, m_cool, m2_cool = welford_update(n_cool, m_cool, m2_cool, a['dc'])
                
                def calc_bounds(n, m, m2, z=3):
                    if n < 2: return m, 0.0, None, None
                    stddev = math.sqrt(m2 / (n - 1))
                    return m, stddev, m - (z * stddev), m + (z * stddev)
                    
                sm, sstd, sl, su = calc_bounds(n_suhu, m_suhu, m2_suhu, z=5)
                hm, hstd, hl, hu = calc_bounds(n_heat, m_heat, m2_heat, z=3)
                km, kstd, kl, ku = calc_bounds(n_keep, m_keep, m2_keep, z=3)
                cm, cstd, cl, cu = calc_bounds(n_cool, m_cool, m2_cool, z=3)
                
                is_warning = False
                warning_message = ""
                total_rejected = sum(rejection_stats.values())
                if total_processed > 0 and (total_rejected / total_processed) > 0.20:
                    is_warning = True
                    warning_message = f"Warning: Rejection Rate > 20% ({total_rejected}/{total_processed}). Breakdown: Suhu:{rejection_stats['suhu']} Heat:{rejection_stats['heat']} Keep:{rejection_stats['keep']} Cool:{rejection_stats['cool']} ZScore:{rejection_stats['old_zscore']}. Metode ini mungkin memihak kondisi mesin yang rusak kronis."

                AnomalyThresholdProposal.objects.create(
                    master=master,
                    week_start_date=start_time.date(),
                    week_end_date=end_time.date(),
                    suhu_mean_new=sm, suhu_stddev_new=sstd, suhu_lower_bound_new=sl, suhu_upper_bound_new=su,
                    heat_mean_new=hm, heat_stddev_new=hstd, heat_lower_bound_new=hl, heat_upper_bound_new=hu,
                    keep_mean_new=km, keep_stddev_new=kstd, keep_lower_bound_new=kl, keep_upper_bound_new=ku,
                    cool_mean_new=cm, cool_stddev_new=cstd, cool_lower_bound_new=cl, cool_upper_bound_new=cu,
                    new_data_count=len(pure_records),
                    outlier_rejected_count=total_rejected,
                    is_warning=is_warning,
                    warning_message=warning_message,
                    status='DRAFT'
                )
                proposals_created += 1

        self.stdout.write(self.style.SUCCESS(f"Selesai! {proposals_created} proposal kalibrasi dibuat, {skipped} diskip."))
