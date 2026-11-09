import math

from datetime import datetime, timedelta

from collections import defaultdict

from django.utils import timezone

from django.db.models import Q

from monitoring.models import (

    Machine, DyeingProcess, ProgramMaster, GlobalSettings, MachineStatusSnapshot, DataAnomaly

)

from monitoring.api_report import sort_machines_custom





def linear_regression(points):

    """

    Menghitung regresi linier y = slope * x + intercept dan koefisien korelasi r.

    points: list of dict with 'x' (tekanan) and 'y' (delay heating).

    """

    n = len(points)

    if n < 2:

        return None

    sum_x = sum(p['x'] for p in points)

    sum_y = sum(p['y'] for p in points)

    sum_xy = sum(p['x'] * p['y'] for p in points)

    sum_xx = sum(p['x'] * p['x'] for p in points)

    sum_yy = sum(p['y'] * p['y'] for p in points)



    denominator = (n * sum_xx - sum_x * sum_x)

    if denominator == 0:

        return None



    slope = (n * sum_xy - sum_x * sum_y) / denominator

    intercept = (sum_y - slope * sum_x) / n



    r_denom = math.sqrt(denominator * (n * sum_yy - sum_y * sum_y))

    r = 0.0 if r_denom == 0 else (n * sum_xy - sum_x * sum_y) / r_denom



    pred_4_5 = slope * 4.5 + intercept



    return {

        'slope': round(slope, 3),

        'intercept': round(intercept, 2),

        'r': round(r, 2),

        'pred_at_4_5_bar': round(pred_4_5, 1)

    }





def compute_machine_fleet_summary(date_str: str, window_str: str = "1D") -> dict:

    """

    Engine terpadu Machine Fleet Health, SPC & Energy Waste Intelligence.

    Menghitung skor kesehatan mesin (MHI), evaluasi 3 fase (heat/keep/cool),

    presisi suhu, korelasi boiler, dan proyeksi finansial energi terbuang.

    """

    try:

        dt = datetime.strptime(date_str, "%Y-%m-%d")

    except (ValueError, TypeError):

        dt = timezone.localtime(timezone.now()).date()



    day_start = timezone.make_aware(datetime.combine(dt, datetime.min.time()).replace(hour=6, minute=0, second=0))

    day_end = day_start + timedelta(days=1)



    window = (window_str or "1D").upper()

    if window == "30D":

        window_start = day_start - timedelta(days=29)

        window_days = 30.0

    elif window == "7D":

        window_start = day_start - timedelta(days=6)

        window_days = 7.0

    else:

        window = "1D"

        window_start = day_start

        window_days = 1.0



    total_window_minutes = window_days * 1440.0



    settings = GlobalSettings.load()

    steam_rate = getattr(settings, 'steam_cost_per_kg', 350.0) or 350.0

    lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8

    wbp_mult = getattr(settings, 'wbp_multiplier', 1.4) or 1.4

    threshold_pressure = getattr(settings, 'steam_healthy_threshold', 3.8) or 3.8



    # 1. Mesin yang dievaluasi

    valid_machines = Machine.objects.filter(is_active=True).exclude(

        group__code='MC_BOILER'

    ).exclude(code__in=['Steam_Pr', 'Oil_Temp']).select_related('group').order_by('name')



    valid_machine_ids = set(valid_machines.values_list('id', flat=True))



    # 2. Proses dalam window terpilih (termasuk yang sedang berjalan atau overlap batas)

    window_processes = list(

        DyeingProcess.objects.filter(

            machine_id__in=valid_machine_ids,

            is_valid_process=True

        ).filter(

            Q(start_time__gte=window_start, start_time__lt=day_end) |

            Q(start_time__lt=window_start, end_time__gt=window_start) |

            Q(start_time__lt=window_start, end_time__isnull=True)

        ).select_related('machine', 'machine__group', 'identity', 'identity__program').order_by('-start_time')

    )



    # 3. Proses 1-hari (hari acuan terpilih) untuk evaluasi harian

    day_processes = [

        p for p in window_processes

        if (p.start_time and day_start <= p.start_time < day_end) or

           (p.start_time and p.start_time < day_start and (p.end_time is None or p.end_time > day_start))

    ]



    # Map processes by machine

    p_by_m_window = defaultdict(list)

    for p in window_processes:

        p_by_m_window[p.machine_id].append(p)



    p_by_m_day = defaultdict(list)

    for p in day_processes:

        p_by_m_day[p.machine_id].append(p)



    # 4. Ambil semua batch dari mesin itu di 1 bulan terakhir yang memiliki identitas program

    one_month_ago = day_end - timedelta(days=30)

    month_processes = list(

        DyeingProcess.objects.filter(

            machine_id__in=valid_machine_ids,

            is_valid_process=True,

            start_time__gte=one_month_ago,

            start_time__lt=day_end,

            identity__isnull=False,

            identity__program__isnull=False

        ).select_related('machine', 'identity', 'identity__program').order_by('-start_time')

    )

    p_by_m_month = defaultdict(list)

    for p in month_processes:

        p_by_m_month[p.machine_id].append(p)



    recent_processes_map = {}

    for m in valid_machines:

        m_batches = p_by_m_month.get(m.id, [])

        if m_batches:

            recent_processes_map[m.id] = m_batches

        else:

            # Fallback jika mesin tidak ada proses dalam 30 hari, ambil riwayat mundur yang berprogram

            hist = list(

                DyeingProcess.objects.filter(

                    machine=m,

                    is_valid_process=True,

                    start_time__lt=day_end,

                    identity__isnull=False,

                    identity__program__isnull=False

                ).select_related('machine', 'identity', 'identity__program').order_by('-start_time')[:35]

            )

            recent_processes_map[m.id] = hist



    # 4b. Pre-fetch DataAnomaly untuk seluruh recent processes mesin

    all_recent_proc_ids = [p.id for procs in recent_processes_map.values() for p in procs]

    anomalies_qs = DataAnomaly.objects.filter(

        process_record_id__in=all_recent_proc_ids

    ).select_related('process_record')



    anomalies_by_process = {}

    for a in anomalies_qs:

        flags = a.details.get('flags', []) if isinstance(a.details, dict) else []

        anomalies_by_process[a.process_record_id] = {

            'id': a.id,

            'anomaly_type': a.anomaly_type,

            'severity': a.severity,

            'flags': flags,

            'details': a.details

        }



    # Helper untuk menghitung total waktu aktif mesin (menit) dengan merge interval overlap

    def _compute_uptime_minutes(procs, eval_start, eval_end):

        raw_intervals = []

        for p in procs:

            r_start = p.start_time or p.heating_start_time

            if not r_start:

                continue

            r_end = p.end_time or min(timezone.now(), eval_end)

            c_start = max(r_start, eval_start)

            c_end = min(r_end, eval_end)

            if c_end > c_start:

                raw_intervals.append((c_start, c_end))



        if not raw_intervals:

            return 0.0



        raw_intervals.sort(key=lambda x: x[0])

        merged = [raw_intervals[0]]

        for cur_s, cur_e in raw_intervals[1:]:

            prev_s, prev_e = merged[-1]

            if cur_s <= prev_e:

                merged[-1] = (prev_s, max(prev_e, cur_e))

            else:

                merged.append((cur_s, cur_e))



        return sum((e - s).total_seconds() / 60.0 for s, e in merged)



    # 5. Availability untuk window terpilih & hari acuan
    # Dihitung dari rata-rata availability harian (hanya hari aktif beroperasi saat mesin/uap berjalan)
    avail_map = {}
    for m in valid_machines:
        target_procs = p_by_m_window.get(m.id, []) if window in ("30D", "7D") else p_by_m_day.get(m.id, [])
        total_uptime_minutes = _compute_uptime_minutes(target_procs, window_start, day_end)
        day_uptime_mins = _compute_uptime_minutes(p_by_m_day.get(m.id, []), day_start, day_end)

        if window in ("30D", "7D"):
            n_days = 30 if window == "30D" else 7
            active_daily_avails = []
            for i in range(n_days):
                d_s = window_start + timedelta(days=i)
                d_e = d_s + timedelta(days=1)
                d_p = [
                    p for p in target_procs
                    if (p.start_time and d_s <= p.start_time < d_e) or
                       (p.start_time and p.start_time < d_s and (p.end_time is None or p.end_time > d_s))
                ]
                u = _compute_uptime_minutes(d_p, d_s, d_e)
                if u > 0:
                    active_daily_avails.append(min(100.0, (u / 1440.0) * 100.0))

            if active_daily_avails:
                avail_pct = round(sum(active_daily_avails) / len(active_daily_avails), 1)
            else:
                avail_pct = 0.0
        else:
            if day_uptime_mins > 0:
                avail_pct = round((min(day_uptime_mins, 1440.0) / 1440.0) * 100.0, 1)
            else:
                avail_pct = 0.0

        if total_uptime_minutes > 0:
            h = int(total_uptime_minutes // 60)
            mins = int(total_uptime_minutes % 60)
            avail_str = f"{h}j {mins}m" if h > 0 else f"{mins}m"
        else:
            avail_str = "0m"

        avail_map[m.id] = {
            "pct": avail_pct,
            "str": avail_str,
            "mins": round(total_uptime_minutes, 1),
            "day_mins": round(day_uptime_mins, 1),
            "day_pct": round((min(day_uptime_mins, 1440.0) / 1440.0) * 100.0, 1)
        }



    # 6. Komputasi per Mesin

    result_machines = []



    fleet_total_eff = []

    fleet_total_steam_waste_kg = 0.0

    fleet_total_power_waste_kwh = 0.0

    fleet_total_loss_rp = 0

    fleet_total_loss_hours = 0.0



    category_waste_rp = {

        'heating_waste_rp': 0,

        'cooling_waste_rp': 0,

        'holding_waste_rp': 0,

        'boiler_drop_waste_rp': 0

    }



    for m in valid_machines:

        m_id = m.id

        eval_batches = recent_processes_map.get(m_id, [])

        day_batches = p_by_m_day.get(m_id, [])

        win_batches = p_by_m_window.get(m_id, [])



        # Jika mesin sama sekali tidak ada riwayat proses, abaikan dari tabel analitik operasional

        if not eval_batches and not day_batches:

            continue



        # Nominal power mesin

        nom_power = getattr(m, 'nominal_power', 0) or 0.0

        avg_steam_rate_h = getattr(m, 'average_steam_usage', 0) or 0.0



        heat_scores = []

        cool_scores = []

        temp_scores = []

        keep_scores = []

        anom_scores = []



        delta_heats = []

        delta_cools = []

        delta_steadiest = []

        delta_totals = []

        delta_temps = []



        heat_gradients = []

        cool_gradients = []

        pressures = []



        temp_overshoot_cnt = 0

        temp_under_cnt = 0

        reheat_cnt = 0

        problem_batch_cnt = 0



        machine_waste_steam_kg = 0.0

        machine_waste_power_kwh = 0.0

        machine_waste_rp = 0



        corr_points = []

        spc_points = []

        recent_batch_rows = []



        programs_agg = defaultdict(lambda: {

            'count': 0,

            'anomaly_count': 0,

            'critical_anomaly_count': 0,

            'minor_anomaly_count': 0,

            'today_count': 0,

            'today_anomaly_count': 0,

            'today_critical_count': 0,

            'suhu_max': None,

            'ideal_heat': None,

            'ideal_cool': None,

            'ideal_steady': None,

            'ideal_total': None,

            'heat_list': [],

            'cool_list': [],

            'steady_list': [],

            'total_list': [],

            'temp_list': [],

            'pressure_list': []

        })



        # Evaluasi setiap batch dalam sample (eval_batches)

        for b in eval_batches:

            ident = getattr(b, 'identity', None)

            prog = ident.program if ident else None



            # Durasi aktual

            b_heat = round(b.real_heating_duration or b.heating_duration or 0.0, 1)

            b_cool = round(b.cooling_duration or 0.0, 1)

            b_steady = round(b.steady_duration or 0.0, 1)

            b_total = round(b.duration_effective or (b_heat + b_steady + b_cool) or 0.0, 1)



            p_steam = round(b.avg_steam_pressure, 2) if b.avg_steam_pressure is not None else 4.0

            pressures.append(p_steam)



            if b.heating_avg_gradient:

                heat_gradients.append(round(b.heating_avg_gradient, 2))

            if b.cooling_avg_gradient:

                cool_gradients.append(round(abs(b.cooling_avg_gradient), 2))



            # Resep ideal

            i_heat = prog.durasi_heating_ideal if prog else None

            i_cool = prog.durasi_cooling_ideal if prog else None

            i_steady = prog.durasi_keeping_ideal if prog else None

            i_total = prog.durasi_ideal if prog else None

            t_max_prog = prog.suhu_max if prog else None



            # Efisiensi batch

            eff = None

            if i_total and b_total > 0:

                eff = round((i_total / b_total) * 100, 1)

                if eff < 85:

                    problem_batch_cnt += 1



            # Delat durasi

            dh = round(b_heat - i_heat, 1) if (i_heat and b_heat > 0) else None

            dc = round(b_cool - i_cool, 1) if (i_cool and b_cool > 0) else None

            ds = round(b_steady - i_steady, 1) if (i_steady and b_steady > 0) else None

            dtot = round(b_total - i_total, 1) if (i_total and b_total > 0) else None



            if dh is not None: delta_heats.append(dh)

            if dc is not None: delta_cools.append(dc)

            if ds is not None: delta_steadiest.append(ds)

            if dtot is not None: delta_totals.append(dtot)



            # ── 1. Skor Heating (Terkoreksi Tekanan Uap) ──

            if dh is not None:

                if dh <= 4:

                    s_h = 100

                elif dh <= 12:

                    s_h = 85 if p_steam >= threshold_pressure else 92

                elif dh <= 25:

                    s_h = 60 if p_steam >= threshold_pressure else 78

                elif dh <= 40:

                    s_h = 40 if p_steam >= threshold_pressure else 65

                else:

                    s_h = 20 if p_steam >= threshold_pressure else 50

                heat_scores.append(s_h)



            # ── 2. Skor Cooling ──

            if dc is not None:

                if dc <= 4:

                    s_c = 100

                elif dc <= 12:

                    s_c = 82

                elif dc <= 25:

                    s_c = 60

                elif dc <= 40:

                    s_c = 40

                else:

                    s_c = 20

                cool_scores.append(s_c)



            # ── 3. Skor Presisi Suhu ──

            d_temp = None

            if b.max_temp and t_max_prog:

                d_temp = round(b.max_temp - t_max_prog, 1)

                delta_temps.append(d_temp)

                if d_temp > 2.5:

                    temp_overshoot_cnt += 1

                elif d_temp < -2.5:

                    temp_under_cnt += 1



                if abs(d_temp) <= 1.2:

                    s_t = 100

                elif abs(d_temp) <= 2.5:

                    s_t = 82

                elif abs(d_temp) <= 4.0:

                    s_t = 55

                else:

                    s_t = 30

                temp_scores.append(s_t)



            # ── 4. Skor Holding & Siklus ──

            if ds is not None:

                if abs(ds) <= 6:

                    s_k = 100

                elif ds <= 15:

                    s_k = 80

                elif ds <= 30:

                    s_k = 55

                else:

                    s_k = 30

                keep_scores.append(s_k)



            # ── 5. Skor Bebas Anomali ──

            s_a = 100

            # Check re-heating

            if b.heating_start_time and b.steady_start_time and b.cooling_start_time:

                # jika heating span >> heating duration, ada indikasi multiple heat

                if b.heating_span and b.heating_duration and (b.heating_span > b.heating_duration * 1.8):

                    reheat_cnt += 1

                    s_a -= 30

            anom_scores.append(max(0, s_a))



            # ── 6. Perhitungan Energi & Finansial Terbuang per Batch ──

            # Uap

            st_waste = 0.0

            if b.predicted_steam_kg and b.predicted_steam_ideal_kg:

                st_waste = max(0.0, b.predicted_steam_kg - b.predicted_steam_ideal_kg)

            elif b.predicted_steam_kg and i_total and b_total > i_total:

                # Fallback rasio waktu molor

                st_waste = max(0.0, (b.predicted_steam_kg * (b_total - i_total) / b_total) * 0.65)

            elif dtot and dtot > 0 and avg_steam_rate_h > 0:

                st_waste = round((dtot / 60.0) * (avg_steam_rate_h * 0.4), 1)



            # Listrik pompa

            pwr_waste = 0.0

            if b.power_consumption_kwh and b.ideal_power_consumption_kwh:

                pwr_waste = max(0.0, b.power_consumption_kwh - b.ideal_power_consumption_kwh)

            elif dtot and dtot > 0 and nom_power > 0:

                pwr_waste = round((dtot / 60.0) * nom_power, 2)



            batch_cost_loss = round((st_waste * steam_rate) + (pwr_waste * lwbp_rate))



            machine_waste_steam_kg += st_waste

            machine_waste_power_kwh += pwr_waste

            machine_waste_rp += batch_cost_loss



            # Alokasi kategori pemborosan untuk fleet breakdown

            if dh and dh > 5:

                category_waste_rp['heating_waste_rp'] += round(dh * (st_waste / max(1, (dh + max(0, dc or 0) + max(0, ds or 0)))) * steam_rate)

            if dc and dc > 5:

                category_waste_rp['cooling_waste_rp'] += round(dc * 15 * lwbp_rate) # pompa cooling running extra

            if ds and ds > 8:

                category_waste_rp['holding_waste_rp'] += round(ds * 25 * lwbp_rate)

            if p_steam < threshold_pressure and dh and dh > 10:

                category_waste_rp['boiler_drop_waste_rp'] += round(st_waste * 0.4 * steam_rate)



            # ── 7. Data Poin Korelasi & SPC ──

            start_dt_local = timezone.localtime(b.start_time) if b.start_time else None

            date_label = start_dt_local.strftime("%d/%m") if start_dt_local else "-"

            time_label = start_dt_local.strftime("%H:%M") if start_dt_local else "-"



            if b.avg_steam_pressure:

                p_val = round(b.avg_steam_pressure, 2)

                # Tentukan kuadran analitik

                quad = "OPTIMAL"

                if p_val < 3.8 and (dh is not None and dh > 10):

                    quad = "BOILER_DROP"

                elif p_val >= 3.8 and (dh is not None and dh > 10):

                    quad = "MECHANICAL_DEGRADATION"

                elif dh is not None and dh > 25:

                    quad = "SEVERE_LAG"



                corr_points.append({

                    "id": b.id,

                    "batch": b.batch_number,

                    "batch_number": b.batch_number,

                    "x": p_val,

                    "y": dh if dh is not None else 0,

                    "avg_steam_pressure": p_val,

                    "real_heat": b_heat,

                    "ideal_heat": i_heat,

                    "delta_heat": dh,

                    "real_cool": b_cool,

                    "ideal_cool": i_cool,

                    "delta_cool": dc,

                    "program_name": prog.nama if prog else "Tanpa Program",

                    "quadrant": quad,

                    "date": date_label,

                    "time": time_label

                })



            if b.max_temp:

                spc_points.append({

                    "id": b.id,

                    "batch": b.batch_number,

                    "temp": round(b.max_temp, 1),

                    "target": t_max_prog,

                    "diff": d_temp,

                    "date": date_label

                })



            anom_info = anomalies_by_process.get(b.id, None)

            has_anom = anom_info is not None

            is_critical = bool(has_anom and anom_info.get('severity') in ('CRITICAL', 'HIGH'))

            is_minor = bool(has_anom and not is_critical)

            is_today = bool(b.start_time and day_start <= b.start_time < day_end)



            # Data row batch untuk recent drawer (SEMUA batch 1 bulan terakhir berprogram)

            recent_batch_rows.append({

                    "id": b.id,

                    "batch_number": b.batch_number,

                    "order_no": ident.nomor_order if ident and ident.nomor_order else "-",

                    "program_name": prog.nama if prog else "Tanpa Program",

                    "date_str": date_label,

                    "time_str": time_label,

                    "is_today": is_today,

                    "heat_mins": b_heat,

                    "ideal_heat": i_heat,

                    "delta_heat": dh,

                    "cool_mins": b_cool,

                    "ideal_cool": i_cool,

                    "delta_cool": dc,

                    "steady_mins": b_steady,

                    "ideal_steady": i_steady,

                    "delta_steady": ds,

                    "total_mins": b_total,

                    "ideal_total": i_total,

                    "eff": eff,

                    "max_temp": round(b.max_temp, 1) if b.max_temp else None,

                    "target_temp": t_max_prog,

                    "avg_pressure": round(b.avg_steam_pressure, 2) if b.avg_steam_pressure else None,

                    "waste_steam_kg": round(st_waste, 1),

                    "waste_cost_rp": batch_cost_loss,

                    "has_anomaly": has_anom,

                    "is_critical_anomaly": is_critical,

                    "is_minor_anomaly": is_minor,

                    "anomaly": anom_info

                })



            # ── 8. Akumulasi Program Compliance ──

            prog_name = prog.nama if prog else "Tanpa Master Program"

            p_agg = programs_agg[prog_name]

            p_agg['count'] += 1

            if has_anom:

                p_agg['anomaly_count'] += 1

                if is_critical:

                    p_agg['critical_anomaly_count'] += 1

                else:

                    p_agg['minor_anomaly_count'] += 1

            if is_today:

                p_agg['today_count'] += 1

                if has_anom:

                    p_agg['today_anomaly_count'] += 1

                    if is_critical:

                        p_agg['today_critical_count'] += 1

            if t_max_prog and p_agg['suhu_max'] is None: p_agg['suhu_max'] = t_max_prog

            if i_heat and p_agg['ideal_heat'] is None: p_agg['ideal_heat'] = i_heat

            if i_cool and p_agg['ideal_cool'] is None: p_agg['ideal_cool'] = i_cool

            if i_steady and p_agg['ideal_steady'] is None: p_agg['ideal_steady'] = i_steady

            if i_total and p_agg['ideal_total'] is None: p_agg['ideal_total'] = i_total



            if b_heat > 0: p_agg['heat_list'].append(b_heat)

            if b_cool > 0: p_agg['cool_list'].append(b_cool)

            if b_steady > 0: p_agg['steady_list'].append(b_steady)

            if b_total > 0: p_agg['total_list'].append(b_total)

            if b.max_temp: p_agg['temp_list'].append(b.max_temp)

            if b.avg_steam_pressure: p_agg['pressure_list'].append(b.avg_steam_pressure)



        # ── Rata-rata Skor Sub-Indeks & MHI ──

        n_eval = len(eval_batches)

        avg_sh = round(sum(heat_scores) / len(heat_scores), 1) if heat_scores else 75.0

        avg_sc = round(sum(cool_scores) / len(cool_scores), 1) if cool_scores else 75.0

        avg_st = round(sum(temp_scores) / len(temp_scores), 1) if temp_scores else 85.0

        avg_sk = round(sum(keep_scores) / len(keep_scores), 1) if keep_scores else 80.0

        avg_sa = round(sum(anom_scores) / len(anom_scores), 1) if anom_scores else 90.0



        mhi = round(0.30 * avg_sh + 0.25 * avg_sc + 0.20 * avg_st + 0.15 * avg_sk + 0.10 * avg_sa, 1)



        if mhi >= 85:

            grade = "A"

        elif mhi >= 70:

            grade = "B"

        elif mhi >= 55:

            grade = "C"

        else:

            grade = "D"



        # Deteksi Tren MHI (separuh awal vs separuh akhir)

        if len(heat_scores) >= 10:

            half = len(heat_scores) // 2

            early_avg = sum(heat_scores[half:]) / len(heat_scores[half:])

            recent_avg = sum(heat_scores[:half]) / len(heat_scores[:half])

            if recent_avg - early_avg >= 4.0:

                trend = "improving"

            elif early_avg - recent_avg >= 4.0:

                trend = "declining"

            else:

                trend = "stable"

        else:

            trend = "stable"



        # ── Rata-rata Metrik Fisika & Statistik ──

        avg_dh = round(sum(delta_heats) / len(delta_heats), 1) if delta_heats else None

        avg_dc = round(sum(delta_cools) / len(delta_cools), 1) if delta_cools else None

        avg_ds = round(sum(delta_steadiest) / len(delta_steadiest), 1) if delta_steadiest else None

        avg_dtemp = round(sum(delta_temps) / len(delta_temps), 1) if delta_temps else None



        avg_h_grad = round(sum(heat_gradients) / len(heat_gradients), 2) if heat_gradients else None

        avg_c_grad = round(sum(cool_gradients) / len(cool_gradients), 2) if cool_gradients else None

        avg_pr_val = round(sum(pressures) / len(pressures), 2) if pressures else None



        # Linear regression delay vs pressure

        reg_result = linear_regression(corr_points)

        r_val = reg_result['r'] if reg_result else None

        pred_4_5 = reg_result['pred_at_4_5_bar'] if reg_result else None



        # ── Proyeksi Finansial 30 Hari & Rata-rata per Batch ──

        avg_waste_rp_batch = round(machine_waste_rp / max(1, n_eval))

        avg_waste_steam_batch = round(machine_waste_steam_kg / max(1, n_eval), 1)

        avg_waste_power_batch = round(machine_waste_power_kwh / max(1, n_eval), 2)



        # Estimasi frekuensi batch harian mesin ini (rata-rata dari window atau 3.2 batch/hari)

        daily_freq = round(len(win_batches) / 30.0, 1) if window == "30D" else (round(len(win_batches) / 7.0, 1) if window == "7D" else len(day_batches))

        if daily_freq <= 0.3:

            daily_freq = 3.0  # standar kapasitas normal jet



        proj_30d_rp = round(avg_waste_rp_batch * daily_freq * 30)

        proj_30d_steam_kg = round(avg_waste_steam_batch * daily_freq * 30)

        proj_30d_power_kwh = round(avg_waste_power_batch * daily_freq * 30)

        proj_7d_rp = round(avg_waste_rp_batch * daily_freq * 7)



        # ── Diagnosis Utama Preskriptif ──

        if avg_sh < 60 and (pred_4_5 is not None and pred_4_5 > 14):

            diag_tag = "MECHANICAL_DEGRADATION"

            diag_title = "Degradasi Penukar Panas (HE) / Steam Trap"

            diag_tone = "rose"

            diag_summary = f"Pemanasan konsisten molor rata-rata +{avg_dh} mnt bahkan saat tekanan uap 4.5 bar (proyeksi delay {pred_4_5} mnt)."

            diag_prescription = "Jadwalkan chemical descaling pada tabung Heat Exchanger dan periksa strainer/katup steam trap dari sumbatan kerak."

        elif avg_sc < 60 and (avg_dc and avg_dc > 16):

            diag_tag = "COOLING_BOTTLENECK"

            diag_title = "Hambatan Sirkulasi Air Pendingin"

            diag_tone = "blue"

            diag_summary = f"Fase cooling lambat rata-rata +{avg_dc} mnt (laju pendinginan rendah {avg_c_grad or '-'} °C/mnt)."

            diag_prescription = "Periksa bukaan pneumatic cooling valve, bersihkan saringan inlet air pendingin, dan cek debit pompa booster."

        elif avg_sh < 68 and (r_val is not None and r_val < -0.45) and (avg_pr_val and avg_pr_val < 3.8):

            diag_tag = "BOILER_DROP"

            diag_title = "Sensitif Terhadap Drop Tekanan Boiler"

            diag_tone = "amber"

            diag_summary = f"Pemanasan melambat saat tekanan uap drop (korelasi r={r_val}, rata-rata {avg_pr_val} bar). Kondisi fisik mesin relatif stabil."

            diag_prescription = "Bukan kerusakan internal mesin. Koordinasikan penyeimbangan beban uap boiler (staggering start time pemanasan antar-mesin)."

        elif avg_sk < 65 and (avg_ds and avg_ds > 18):

            diag_tag = "OPERATIONAL_HOLD"

            diag_title = "Inefisiensi Operasional (Over-Holding)"

            diag_tone = "amber"

            diag_summary = f"Waktu steady holding melebihi resep rata-rata +{avg_ds} mnt. Membuang uap dan listrik sirkulasi berlebih."

            diag_prescription = "Audit SOP operator saat pengambilan sampel kain dan pastikan pengujian lab warna tepat waktu."

        elif mhi >= 85:

            diag_tag = "PRIMA"

            diag_title = "Performa Prima & Termal Efisien"

            diag_tone = "emerald"

            diag_summary = f"Seluruh siklus heating, holding, dan cooling berjalan presisi sesuai resep standar (MHI {mhi})."

            diag_prescription = "Pertahankan kondisi mesin. Mesin ini dapat dijadikan benchmark kalibrasi DNA fisika untuk mesin sejenis."

        else:

            diag_tag = "MODERATE_DEVIATION"

            diag_title = "Deviasi Wajar Terpantau"

            diag_tone = "slate"

            diag_summary = f"Performa mesin dalam batas toleransi kerja dengan efisiensi memadai (MHI {mhi})."

            diag_prescription = "Lakukan pemantauan preventif berkala pada katup pneumatik dan sensor suhu JUMO."



        # ── Formulasi Tabel Program Compliance ──

        program_matrix = []

        for pname, pinfo in programs_agg.items():

            cnt = pinfo['count']

            a_heat = round(sum(pinfo['heat_list']) / len(pinfo['heat_list']), 1) if pinfo['heat_list'] else None

            a_cool = round(sum(pinfo['cool_list']) / len(pinfo['cool_list']), 1) if pinfo['cool_list'] else None

            a_steady = round(sum(pinfo['steady_list']) / len(pinfo['steady_list']), 1) if pinfo['steady_list'] else None

            a_total = round(sum(pinfo['total_list']) / len(pinfo['total_list']), 1) if pinfo['total_list'] else None

            a_temp = round(sum(pinfo['temp_list']) / len(pinfo['temp_list']), 1) if pinfo['temp_list'] else None

            a_pr = round(sum(pinfo['pressure_list']) / len(pinfo['pressure_list']), 2) if pinfo['pressure_list'] else None



            # Standar deviasi suhu

            std_temp = None

            if len(pinfo['temp_list']) >= 2 and a_temp is not None:

                variance = sum((x - a_temp) ** 2 for x in pinfo['temp_list']) / (len(pinfo['temp_list']) - 1)

                std_temp = round(math.sqrt(variance), 2)



            program_matrix.append({

                "program_name": pname,

                "batch_count": cnt,

                "anomaly_count": pinfo['anomaly_count'],

                "critical_anomaly_count": pinfo['critical_anomaly_count'],

                "minor_anomaly_count": pinfo['minor_anomaly_count'],

                "today_count": pinfo['today_count'],

                "today_anomaly_count": pinfo['today_anomaly_count'],

                "today_critical_count": pinfo['today_critical_count'],

                "suhu_max": pinfo['suhu_max'],

                "ideal_heat": pinfo['ideal_heat'],

                "avg_heat": a_heat,

                "delta_heat": round(a_heat - pinfo['ideal_heat'], 1) if (a_heat and pinfo['ideal_heat']) else None,

                "ideal_cool": pinfo['ideal_cool'],

                "avg_cool": a_cool,

                "delta_cool": round(a_cool - pinfo['ideal_cool'], 1) if (a_cool and pinfo['ideal_cool']) else None,

                "ideal_steady": pinfo['ideal_steady'],

                "avg_steady": a_steady,

                "delta_steady": round(a_steady - pinfo['ideal_steady'], 1) if (a_steady and pinfo['ideal_steady']) else None,

                "ideal_total": pinfo['ideal_total'],

                "avg_total": a_total,

                "avg_temp": a_temp,

                "stddev_temp": std_temp,

                "avg_pressure": a_pr

            })



        program_matrix.sort(key=lambda x: x['batch_count'], reverse=True)



        # Akumulasi Fleet Totals

        fleet_total_eff.append(mhi)

        fleet_total_steam_waste_kg += machine_waste_steam_kg

        fleet_total_power_waste_kwh += machine_waste_power_kwh

        fleet_total_loss_rp += machine_waste_rp

        if delta_totals:

            pos_deltas = [d for d in delta_totals if d > 0]

            if pos_deltas:

                fleet_total_loss_hours += round(sum(pos_deltas) / 60.0, 1)



        result_machines.append({

            "machine_id": m.id,

            "machine_name": m.name,

            "machine_code": getattr(m, 'code', None) or m.name,

            "group_name": m.group.name if m.group else "Lain-lain",

            "group_code": m.group.code if m.group else "OTHER",

            "nominal_power_kw": nom_power,

            "total_processes_day": len(day_batches),

            "total_processes_window": len(win_batches),

            "evaluated_batches_count": n_eval,

            "health_score": mhi,

            "health_grade": grade,

            "health_trend": trend,

            "sub_scores": {

                "heat": avg_sh,

                "cool": avg_sc,

                "temp": avg_st,

                "keep": avg_sk,

                "anom": avg_sa

            },

            "availability_pct": avail_map[m_id]['pct'],

            "uptime_str": avail_map[m_id]['str'],

            "avg_heating_grad": avg_h_grad,

            "avg_cooling_grad": avg_c_grad,

            "avg_delta_heat": avg_dh,

            "avg_delta_cool": avg_dc,

            "avg_delta_steady": avg_ds,

            "avg_delta_temp": avg_dtemp,

            "temp_overshoot_count": temp_overshoot_cnt,

            "temp_under_count": temp_under_cnt,

            "reheat_count": reheat_cnt,

            "avg_steam_pressure": avg_pr_val,

            "correlation_r": r_val,

            "pred_at_4_5_bar": pred_4_5,

            "waste_steam_kg": round(machine_waste_steam_kg, 1),

            "waste_power_kwh": round(machine_waste_power_kwh, 1),

            "waste_cost_rp": machine_waste_rp,

            "avg_waste_rp_batch": avg_waste_rp_batch,

            "projected_7d_rp": proj_7d_rp,

            "projected_30d_rp": proj_30d_rp,

            "projected_30d_steam_kg": proj_30d_steam_kg,

            "projected_30d_power_kwh": proj_30d_power_kwh,

            "primary_diagnosis": {

                "tag": diag_tag,

                "title": diag_title,

                "tone": diag_tone,

                "summary": diag_summary,

                "prescription": diag_prescription

            },

            "programs": program_matrix,

            "recent_batches": recent_batch_rows,

            "correlation_points": corr_points,

            "scatter_data": corr_points,

            "spc_points": spc_points,

            "total_processes": len(day_batches),

            "analyzed_processes": n_eval

        })



    sort_machines_custom(result_machines, name_key="machine_name")



    # ── Executive Fleet KPIs ──

    total_active_machines = len(result_machines)

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}

    for rm in result_machines:

        g = rm["health_grade"]

        if g in grade_counts:

            grade_counts[g] += 1



    fleet_avg_mhi = round(sum(fleet_total_eff) / len(fleet_total_eff), 1) if fleet_total_eff else 0.0



    # Total proyeksi 30 hari untuk mesin yang berstatus perlu perbaikan (Grade C & D)

    fleet_proj_30d_critical_rp = sum(rm['projected_30d_rp'] for rm in result_machines if rm['health_grade'] in ['C', 'D'])

    fleet_proj_30d_total_rp = sum(rm['projected_30d_rp'] for rm in result_machines)

    fleet_proj_30d_steam_kg = sum(rm['projected_30d_steam_kg'] for rm in result_machines)

    fleet_proj_30d_power_kwh = sum(rm['projected_30d_power_kwh'] for rm in result_machines)



    return {

        "date": date_str,

        "window": window,

        "date_range_label": f"{window_start.strftime('%d %b %Y')} - {day_end.strftime('%d %b %Y')}",

        "date_range": f"{window_start.strftime('%d %b %Y')} - {day_end.strftime('%d %b %Y')}",

        "tariffs": {

            "steam_cost_per_kg": steam_rate,

            "electricity_base_rate": lwbp_rate

        },

        "fleet_kpi": {

            "total_machines": total_active_machines,

            "healthy_count": grade_counts["A"] + grade_counts["B"],

            "warning_count": grade_counts["C"],

            "critical_count": grade_counts["D"],

            "grade_breakdown": grade_counts,

            "avg_health_score": fleet_avg_mhi,

            "total_loss_hours": fleet_total_loss_hours,

            "total_steam_waste_kg": round(fleet_total_steam_waste_kg, 1),

            "total_power_waste_kwh": round(fleet_total_power_waste_kwh, 1),

            "total_financial_loss_rp": fleet_total_loss_rp,

            "projected_30d_loss_rp": fleet_proj_30d_total_rp,

            "projected_30d_critical_loss_rp": fleet_proj_30d_critical_rp,

            "projected_30d_steam_waste_kg": fleet_proj_30d_steam_kg,

            "projected_30d_power_waste_kwh": fleet_proj_30d_power_kwh,

            "top_waste_breakdown": category_waste_rp

        },

        "machines": result_machines

    }

