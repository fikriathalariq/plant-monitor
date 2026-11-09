from ninja import Router, Schema
from ninja.errors import HttpError
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Case, When, Value, IntegerField
from monitoring.models import Machine, MachineGroup, DyeingProcess, MachineMinuteLog, UserFavoriteBatch
from monitoring.decorators import user_can_access_page
from django.shortcuts import get_object_or_404
from collections import defaultdict
report_router = Router(tags=["Report"])


def _require_permission(request, page_code):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, page_code):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


class BatchFavoriteIn(Schema):
    process_id: int

def sort_machines_custom(machine_list, name_key='name'):
    zet_order = ['ZET 9', 'ZET 8', 'ZET 7', 'ZET 6', 'ZET 5', 'ZET 4', 'ZET 1', 'ZET 10', 'ZET 11', 'ZET 12']
    
    def get_sort_key(m):
        name = m.get(name_key, '')
        if name.startswith('JR ') or name.startswith('JR_'):
            try:
                num = int(name.replace('JR_', '').replace('JR ', ''))
                return (1, -num, name)
            except:
                return (1, 0, name)
        elif name.startswith('JD ') or name.startswith('JD_') or name == 'Jet Mini HSK':
            if name == 'Jet Mini HSK' or name == 'JD_JetMiniHisaka':
                return (2, 9999, name)
            try:
                num = int(name.replace('JD_', '').replace('JD ', ''))
                return (2, num, name)
            except:
                return (2, 999, name)
        elif name.startswith('ZET ') or name.startswith('ZET_'):
            norm = name.replace('ZET_', 'ZET ')
            try:
                idx = zet_order.index(norm)
                return (3, idx, name)
            except ValueError:
                return (3, 999, name)
        return (4, 0, name)
        
    machine_list.sort(key=get_sort_key)

def classify_process_problems(process, program, pressure_threshold=None):
    if not process.duration_effective or not program.durasi_ideal:
        return []
    
    overall_eff = (program.durasi_ideal / process.duration_effective) * 100
    if overall_eff >= 85:
        return []
    
    problems = []

    if pressure_threshold is None:
        try:
            from monitoring.models import GlobalSettings
            settings = GlobalSettings.load()
            pressure_threshold = getattr(settings, 'steam_healthy_threshold', 3.8) or 3.8
        except Exception:
            pressure_threshold = 3.8
    
    # 1. PRESSURE_LOW vs 2. HEATING_SLOW
    # PERATURAN MUTLAK:
    # Proses yang mengalami Tekanan Steam Kurang (PRESSURE_LOW) TIDAK BOLEH masuk ke Heating Lambat (HEATING_SLOW).
    # Walaupun tekanan kurang pasti menyebabkan heating lambat, penyebab utamanya adalah pasokan steam (boiler/pipa).
    # Kategori HEATING_SLOW HANYA untuk proses dengan tekanan steam CUKUP (>= threshold) tapi pemanasan tetap lambat,
    # yang mengindikasikan murni masalah mesin hari itu (valve macet, trap jebol, koil kotor, dll).
    is_pressure_low = (
        process.avg_steam_pressure is not None and 
        process.avg_steam_pressure < pressure_threshold
    )
    
    if is_pressure_low:
        problems.append("PRESSURE_LOW")
    else:
        # 2. HEATING_SLOW (Hanya dievaluasi jika tekanan steam CUKUP / BUKAN masalah tekanan)
        ideal_heat_keep = (program.durasi_heating_ideal or 0) + (program.durasi_keeping_ideal or 0)
        real_heat = process.real_heating_duration or 0
        steady = process.steady_duration or 0
        
        if real_heat + steady > 0 and ideal_heat_keep > 0:
            heat_eff = (ideal_heat_keep / (real_heat + steady)) * 100
            if heat_eff < 85:
                problems.append("HEATING_SLOW")
                
    # 3. COOLING_SLOW
    if program.durasi_cooling_ideal and process.cooling_duration and process.cooling_duration > 0:
        cool_eff = (program.durasi_cooling_ideal / process.cooling_duration) * 100
        if cool_eff < 85:
            problems.append("COOLING_SLOW")
            
    # 4. START_TEMP_HIGH
    if process.start_temp and process.start_temp > 60:
        problems.append("START_TEMP_HIGH")
        
    if len(problems) == 0:
        problems.append("OTHERS")
        
    return problems


def _compute_downtime_ranking(machine_buckets, machine_meta, interval_minutes):
    """Hitung idle time (state OFF) per mesin dari bucket availability."""
    total_buckets = (24 * 60) // interval_minutes
    ranking = []

    for m_id, meta in machine_meta.items():
        buckets = machine_buckets.get(m_id, {})
        off_minutes = 0.0
        stop_events = 0
        in_off_run = False

        for i in range(total_buckets):
            state = buckets.get(i, "OFF")
            if state == "OFF":
                off_minutes += interval_minutes
                if not in_off_run:
                    stop_events += 1
                    in_off_run = True
            else:
                in_off_run = False

        if off_minutes > 0:
            hours = int(off_minutes // 60)
            mins = int(off_minutes % 60)
            idle_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            ranking.append({
                "machine_id": meta["id"],
                "machine_name": meta["name"],
                "idle_minutes": round(off_minutes, 1),
                "idle_str": idle_str,
                "stop_events": stop_events,
            })

    ranking.sort(key=lambda x: x["idle_minutes"], reverse=True)
    return ranking


def _compute_batch_electricity_metrics(p, program=None, lwbp_rate=1035.8, wbp_rate=None):
    """
    Hitung metrik listrik batch dengan menambahkan durasi keluar-masuk kain
    (pasca-cooling <70°C s/d OFF maksimal 45 menit) ke dalam Durasi Ideal Listrik.
    """
    if program is None:
        ident = getattr(p, 'identity', None)
        program = ident.program if ident else None

    if wbp_rate is None:
        wbp_rate = round(lwbp_rate * 1.4, 2)

    late_stop_mins = 0.0
    if p.reached_70c_time and p.end_time and p.end_time > p.reached_70c_time:
        late_stop_mins = max(0.0, (p.end_time - p.reached_70c_time).total_seconds() / 60.0)

    fabric_allowance_mins = min(late_stop_mins, 45.0)
    recipe_ideal_mins = (program.durasi_ideal or 0.0) if (program and program.durasi_ideal) else (p.program_ideal_duration_mins or 0.0)
    elec_ideal_duration_mins = (recipe_ideal_mins + fabric_allowance_mins) if recipe_ideal_mins > 0 else 0.0

    nom_kw = p.machine_nominal_power or getattr(p.machine, 'nominal_power', 0) or 0
    actual_kwh = p.power_consumption_kwh
    lwbp_kwh = p.power_consumption_lwbp_kwh or 0.0
    wbp_kwh = p.power_consumption_wbp_kwh or 0.0

    cost_lwbp_rp = round(p.power_cost_lwbp if p.power_cost_lwbp is not None else (lwbp_kwh * lwbp_rate), 2)
    cost_wbp_rp = round(p.power_cost_wbp if p.power_cost_wbp is not None else (wbp_kwh * wbp_rate), 2)
    cost_actual_rp = round(p.power_cost_total if p.power_cost_total is not None else (cost_lwbp_rp + cost_wbp_rp), 2)

    ideal_kwh = None
    if elec_ideal_duration_mins > 0 and nom_kw > 0:
        ideal_kwh = round((elec_ideal_duration_mins / 60.0) * nom_kw, 2)
    elif p.ideal_power_consumption_kwh is not None:
        ideal_kwh = round(p.ideal_power_consumption_kwh + (fabric_allowance_mins / 60.0) * nom_kw, 2)

    raw_diff_kwh = None
    pos_loss_kwh = 0.0
    power_eff = None
    cost_ideal_rp = None
    cost_loss_rp = 0.0

    if actual_kwh is not None and ideal_kwh is not None:
        raw_diff_kwh = round(actual_kwh - ideal_kwh, 2)
        pos_loss_kwh = round(max(0.0, actual_kwh - ideal_kwh), 2)
        if actual_kwh > 0:
            power_eff = round(min(100.0, (ideal_kwh / actual_kwh) * 100.0), 1)
        cost_ideal_rp = round(ideal_kwh * lwbp_rate, 2)
        if cost_actual_rp > 0:
            cost_loss_rp = round(max(0.0, cost_actual_rp - cost_ideal_rp), 2)
        else:
            cost_loss_rp = round(pos_loss_kwh * lwbp_rate, 2)

    return {
        "actual_kwh": actual_kwh,
        "ideal_kwh": ideal_kwh,
        "raw_diff_kwh": raw_diff_kwh,
        "pos_loss_kwh": pos_loss_kwh,
        "power_eff": power_eff,
        "cost_lwbp_rp": cost_lwbp_rp,
        "cost_wbp_rp": cost_wbp_rp,
        "cost_actual_rp": cost_actual_rp,
        "cost_ideal_rp": cost_ideal_rp,
        "cost_loss_rp": cost_loss_rp,
        "recipe_ideal_mins": round(recipe_ideal_mins, 1),
        "fabric_allowance_mins": round(fabric_allowance_mins, 1),
        "elec_ideal_duration_mins": round(elec_ideal_duration_mins, 1),
        "late_stop_mins": round(late_stop_mins, 1),
    }


def _compute_changeover_stats(processes):
    """Hitung rata-rata changeover (gap antar batch) per mesin."""
    by_machine = defaultdict(list)
    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
    for p in processes:
        if p.end_time and p.is_complete:
            by_machine[p.machine_id].append(p)

    machine_changeover = {}
    all_gaps = []

    for m_id, m_procs in by_machine.items():
        m_procs.sort(key=lambda x: x.start_time or datetime.min)
        gaps = []
        for i in range(1, len(m_procs)):
            prev = m_procs[i - 1]
            curr = m_procs[i]
            if not prev.end_time:
                continue
            next_start = curr.heating_start_time or curr.start_time
            if not next_start:
                continue
            gap_minutes = (next_start - prev.end_time).total_seconds() / 60.0
            if 0 < gap_minutes < 24 * 60:
                gaps.append(gap_minutes)

        if gaps:
            avg_gap = sum(gaps) / len(gaps)
            machine_changeover[m_id] = round(avg_gap, 1)
            all_gaps.extend(gaps)

    plant_avg = round(sum(all_gaps) / len(all_gaps), 1) if all_gaps else 0
    return machine_changeover, plant_avg


@report_router.get("/daily-summary")
def get_daily_summary(request, date: str):
    _require_permission(request, "daily_report")
    return _compute_daily_summary_data(date)


def _compute_daily_summary_data(date: str):
    """Logika inti daily-summary, dipisah dari guard permission agar bisa
    dipanggil langsung secara internal (misal oleh dashboard steam-sales)
    tanpa terkena gerbang izin halaman 'daily_report'."""
    # Parsing date
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}
    # Set range: 06:00 to 06:00 next day
    start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time = start_time + timedelta(days=1)
    # ─────────────────────────────────────────────────────────────────
    # 1. STEAM TRAFFIC (24 Jam) & TOTAL STEAM (dari MachineStatusSnapshot)
    # ─────────────────────────────────────────────────────────────────
    from monitoring.models import MachineStatusSnapshot
    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp')
    all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0).select_related('group')
    machines_dict = {m.code: m for m in all_steam_machines}
    interval_minutes = 10
    TARGET_POINTS = 144
    interval_data = defaultdict(lambda: {'steam_total': 0.0, 'count': 0})
    for snapshot in snapshots:
        time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
        bucket_index = int(time_diff / interval_minutes)
        if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
        if bucket_index < 0: bucket_index = 0
        steam_total = 0.0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = machines_dict.get(machine_code)
            if machine:
                is_active = False
                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                is_active = is_steam_active_from_snapshot(snap_data)
                if is_active:
                    steam_total += machine.average_steam_usage
        interval_data[bucket_index]['steam_total'] += steam_total
        interval_data[bucket_index]['count'] += 1
    steam_pr_logs = MachineMinuteLog.objects.filter(
        machine__code="Steam_Pr",
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp')
    pressure_data = defaultdict(lambda: {'total': 0.0, 'count': 0})
    for log in steam_pr_logs:
        if log.temperature is not None:
            time_diff = (log.timestamp - start_time).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
            if bucket_index < 0: bucket_index = 0
            pressure_data[bucket_index]['total'] += log.temperature
            pressure_data[bucket_index]['count'] += 1
    steam_series = []
    total_steam_usage = 0.0
    for i in range(TARGET_POINTS):
        bucket_start = start_time + timedelta(minutes=i * interval_minutes)
        avg_steam = 0.0
        avg_steam_jet = 0.0
        avg_steam_non_jet = 0.0
        if interval_data[i]['count'] > 0:
            c = interval_data[i]['count']
            avg_steam = interval_data[i]['steam_total'] / c
            avg_steam_jet = interval_data[i].get('steam_total_jet', 0.0) / c
            avg_steam_non_jet = interval_data[i].get('steam_total_non_jet', 0.0) / c
        avg_pressure = 0.0
        if pressure_data[i]['count'] > 0:
            avg_pressure = pressure_data[i]['total'] / pressure_data[i]['count']
        steam_series.append({
            "time": timezone.localtime(bucket_start).strftime("%H:%M"),
            "usage": round(avg_steam, 1),
            "usage_jet": round(avg_steam_jet, 1),
            "usage_non_jet": round(avg_steam_non_jet, 1),
            "pressure": round(avg_pressure, 2)
        })
        total_steam_usage += avg_steam * (interval_minutes / 60.0)
    # ─────────────────────────────────────────────────────────────────
    # 2. DYEING PROCESSES — Heatmap & History Table (termasuk Data Kain)
    # ─────────────────────────────────────────────────────────────────
    processes = DyeingProcess.objects.filter(
        start_time__gte=start_time,
        start_time__lt=end_time,
        is_valid_process=True
    ).exclude(
        machine__group__code='MC_BOILER'
    ).select_related('machine', 'machine__group', 'identity', 'identity__program')
    process_counts = {}
    history_table = {}
    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
    
    total_power_lwbp_kwh = 0.0
    total_power_wbp_kwh = 0.0
    total_power_kwh = 0.0
    total_fresh_yd = 0.0
    total_creaping_yd = 0.0
    total_other_yd = 0.0

    for p in processes:
        m_id = p.machine_id
        if m_id not in process_counts:
            process_counts[m_id] = 0
        process_counts[m_id] += 1
        group_name = p.machine.group.name if p.machine.group else "Lain-lain"
        if group_name not in history_table:
            history_table[group_name] = []
        # Ambil data kain dari DyeingIdentity (jika sudah diisi)
        identity = getattr(p, 'identity', None)
        
        # Akumulasi Listrik Global
        if p.power_consumption_lwbp_kwh: total_power_lwbp_kwh += p.power_consumption_lwbp_kwh
        if p.power_consumption_wbp_kwh: total_power_wbp_kwh += p.power_consumption_wbp_kwh
        if p.power_consumption_kwh: total_power_kwh += p.power_consumption_kwh

        # Akumulasi Yard Global
        if identity:
            jp = identity.jenis_proses or ""
            oy = identity.output_yard or 0.0
            if jp == "FRESH": total_fresh_yd += oy
            elif jp.startswith("CREAPING"): total_creaping_yd += oy
            else: total_other_yd += oy
            
        nomor_order  = identity.nomor_order  if identity and identity.nomor_order  else "-"
        artikel_kain = identity.artikel_kain if identity and identity.artikel_kain else "-"
        batch_kain   = identity.batch        if identity and identity.batch        else "-"
        history_table[group_name].append({
            "id":           p.id,
            "machine_id":   p.machine.id,
            "machine_name": p.machine.name,
            "machine_code": p.machine.code,
            "batch_number": p.batch_number,
            "start_time":   timezone.localtime(p.start_time).strftime("%H:%M") if p.start_time else "-",
            "end_time":     timezone.localtime(p.end_time).strftime("%H:%M")   if p.end_time   else "-",
            "duration":     round(p.total_duration, 1) if p.total_duration else "-",
            "max_temp":     round(p.max_temp, 1)       if p.max_temp       else "-",
            "status":       "Selesai" if p.is_complete else "Berjalan",
            # Data kain
            "nomor_order":  nomor_order,
            "artikel_kain": artikel_kain,
            "batch_kain":   batch_kain,
            "jenis_proses": identity.jenis_proses if identity and identity.jenis_proses else "-",
            "output_yard":  identity.output_yard if identity and identity.output_yard else 0.0,
        })
    history_groups = []
    for gname, items in history_table.items():
        items.sort(key=lambda x: x["start_time"])
        sort_machines_custom(items, name_key="machine_name")
        history_groups.append({"group_name": gname, "items": items})
    history_groups.sort(key=lambda x: x["group_name"])
    # ─────────────────────────────────────────────────────────────────
    # 3. HEATMAP GROUPS
    # ─────────────────────────────────────────────────────────────────
    groups = MachineGroup.objects.filter(machine__is_active=True).exclude(code='MC_BOILER').distinct().order_by('name')
    active_machines_all = list(Machine.objects.filter(is_active=True).exclude(group__code='MC_BOILER').select_related('group').order_by('name'))
    machines_by_group_dict = defaultdict(list)
    for m in active_machines_all:
        if m.group_id:
            machines_by_group_dict[m.group_id].append(m)

    groups_data = []
    for group in groups:
        machines = machines_by_group_dict.get(group.id, [])
        if not machines:
            continue
        group_processes = 0
        machines_data = []
        for m in machines:
            count = process_counts.get(m.id, 0)
            group_processes += count
            machines_data.append({"id": m.id, "name": m.name, "process_count": count})
            
        sort_machines_custom(machines_data, name_key="name")
        
        groups_data.append({
            "group_name":            group.name,
            "machine_count":         len(machines),
            "total_group_processes": group_processes,
            "machines":              machines_data,
        })
    # ─────────────────────────────────────────────────────────────────
    # 4. MACHINE AVAILABILITY CHART
    #    Downsampling ke 5 menit. State mapping:
    #    HEAT → "HEAT", STEADY → "STEADY", COOL → "COOL",
    #    Running (MANUAL) → "RUNNING", selebihnya → "OFF"
    # ─────────────────────────────────────────────────────────────────
    AVAIL_INTERVAL = interval_minutes   # pakai interval snapshot (misal 10 menit)
    TOTAL_MINUTES  = 24 * 60
    machine_buckets = defaultdict(dict)
    machine_meta    = {}
    code_to_id      = {}
    # Ambil data meta mesin yang valid (exclude BOILER & Sensor)
    valid_machines = Machine.objects.filter(is_active=True).exclude(
        group__code='MC_BOILER'
    ).exclude(code__in=['Steam_Pr', 'Oil_Temp']).select_related('group')
    for m in valid_machines:
        machine_meta[m.id] = {
            "id":         m.id,
            "name":       m.name,
            "group_name": m.group.name if m.group else "Lain-lain",
        }
        code_to_id[m.code] = m.id
    # Menggunakan ulang 'snapshots' dari proses di atas (0 query log tambahan!)
    for snapshot in snapshots:
        time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
        bucket_index = int(time_diff / AVAIL_INTERVAL)
        if 0 <= bucket_index < (TOTAL_MINUTES // AVAIL_INTERVAL):
            for machine_code, snap_data in snapshot.snapshot_data.items():
                m_id = code_to_id.get(machine_code)
                if m_id:
                    if snap_data.get('mode') == 'MANUAL':
                        state = "RUNNING" if snap_data.get('status') == "Running" else "OFF"
                    else:
                        ts = snap_data.get('detail', '')
                        if ts in ("HEAT", "STEADY", "COOL"): state = ts
                        else: state = "OFF"
                    machine_buckets[m_id][bucket_index] = state
    # Konversi bucket → segments (runs of same state)
    def buckets_to_segments(buckets):
        total_buckets = TOTAL_MINUTES // AVAIL_INTERVAL   # 288
        segments = []
        current_state = None
        seg_start     = 0
        for i in range(total_buckets):
            s = buckets.get(i, "OFF")
            if s != current_state:
                if current_state is not None:
                    segments.append({
                        "state":     current_state,
                        "start_pct": round(seg_start / total_buckets * 100, 2),
                        "width_pct": round((i - seg_start) / total_buckets * 100, 2),
                    })
                current_state = s
                seg_start     = i
        # Tutup segment terakhir
        total_buckets_real = TOTAL_MINUTES // AVAIL_INTERVAL
        if current_state is not None:
            segments.append({
                "state":     current_state,
                "start_pct": round(seg_start / total_buckets_real * 100, 2),
                "width_pct": round((total_buckets_real - seg_start) / total_buckets_real * 100, 2),
            })
        return segments
    # Susun per group
    avail_group_map = defaultdict(list)
    for m_id, meta in machine_meta.items():
        segs = buckets_to_segments(machine_buckets.get(m_id, {}))
        avail_group_map[meta["group_name"]].append({
            "machine_id":   meta["id"],
            "machine_name": meta["name"],
            "segments":     segs,
        })
        
    # ─────────────────────────────────────────────────────────────────
    # 5. AVAILABILITY SUMMARY LIST
    # ─────────────────────────────────────────────────────────────────
    machine_availabilities = []
    
    from django.db.models import Q
    # Pre-fetch all JET DyeingProcess records in 1 bulk query
    jet_machine_ids = [m.id for m in valid_machines if m.group and getattr(m.group, 'process_type', None) == 'JET']
    jet_processes_by_mc = defaultdict(list)
    if jet_machine_ids:
        all_jet_proc_qs = (
            DyeingProcess.objects
            .filter(machine_id__in=jet_machine_ids, is_valid_process=True)
            .filter(
                Q(start_time__gte=start_time, start_time__lt=end_time) | 
                Q(start_time__lt=start_time, end_time__gt=start_time) |
                Q(start_time__lt=start_time, end_time__isnull=True)
            )
            .only("machine_id", "heating_start_time", "start_time", "end_time")
        )
        for proc in all_jet_proc_qs:
            jet_processes_by_mc[proc.machine_id].append(proc)

    for m in valid_machines:
        total_uptime_minutes = 0.0
        
        # For JET machines, calculate uptime from DyeingProcess (Rise Time to End Time)
        if m.group and getattr(m.group, 'process_type', None) == 'JET':
            m_processes = jet_processes_by_mc.get(m.id, [])
            for p in m_processes:
                r_start = p.heating_start_time if p.heating_start_time else p.start_time
                r_end = p.end_time if p.end_time else min(timezone.now(), end_time)
                
                # Clamp limits to current day window (06:00 to 06:00)
                r_start = max(r_start, start_time)
                r_end = min(r_end, end_time)
                
                if r_end > r_start:
                    total_uptime_minutes += (r_end - r_start).total_seconds() / 60.0
                    
        else:
            # For MANUAL or other machines, use the snapshot data
            m_id = m.id
            if m_id in machine_buckets:
                for b_idx, state in machine_buckets[m_id].items():
                    if state in ["RUNNING", "HEAT", "STEADY", "COOL"]:
                        total_uptime_minutes += AVAIL_INTERVAL
                        
        if total_uptime_minutes > 0:
            total_uptime_minutes = min(total_uptime_minutes, 1440.0)
            availability_pct = (total_uptime_minutes / 1440.0) * 100.0
            
            hours = int(total_uptime_minutes // 60)
            mins = int(total_uptime_minutes % 60)
            uptime_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            
            machine_availabilities.append({
                "machine_id": m.id,
                "machine_name": m.name,
                "group_name": m.group.name if m.group else "Lain-lain",
                "availability": round(availability_pct, 1),
                "uptime_str": uptime_str,
                "uptime_minutes": round(total_uptime_minutes, 1)
            })
            
    machine_availabilities.sort(key=lambda x: x['availability'], reverse=True)
    
    avg_avail = 0.0
    if len(machine_availabilities) > 0:
        avg_avail = sum(x['availability'] for x in machine_availabilities) / len(machine_availabilities)
        
    availability_summary = {
        "average": round(avg_avail, 1),
        "machines": machine_availabilities
    }
    
    # Sort machines within group by name
    availability_groups = []
    for gname, machines_avail in sorted(avail_group_map.items()):
        sort_machines_custom(machines_avail, name_key="machine_name")
        availability_groups.append({
            "group_name": gname,
            "machines":   machines_avail,
        })
        
    # ─────────────────────────────────────────────────────────────────
    # 6. EFFICIENCY PROBLEM BREAKDOWN & EFFICIENCY SUMMARY
    # ─────────────────────────────────────────────────────────────────
    eff_problem_data = {
        "PRESSURE_LOW": {"label": "Tekanan Steam Kurang", "color": "red", "processes": []},
        "HEATING_SLOW": {"label": "Heating Lambat", "color": "orange", "processes": []},
        "COOLING_SLOW": {"label": "Cooling Lambat", "color": "blue", "processes": []},
        "START_TEMP_HIGH": {"label": "Suhu Awal Tinggi", "color": "purple", "processes": []},
        "OTHERS": {"label": "Masalah Lainnya", "color": "gray", "processes": []}
    }
    
    total_low_efficiency = 0
    total_analyzed = 0
    
    # Changeover time per mesin (gap antar batch selesai → batch berikutnya)
    machine_changeover, plant_avg_changeover = _compute_changeover_stats(processes)

    # For Efficiency Summary (Average per Machine)
    machine_eff_stats = defaultdict(lambda: {
        'total_eff': 0, 'total_loss_time': 0, 'count': 0, 'batch_count': 0, 'name': '', 'processes': [],
        'total_steam': 0, 'total_steam_ideal': 0, 'total_steam_ideal_measured': 0, 'total_steam_with_ideal': 0,
        'total_power': 0, 'total_power_ideal': 0, 'total_power_ideal_measured': 0, 'total_power_actual_measured': 0,
        'steam_ok_count': 0, 'total_steam_loss_kg': 0, 'total_steam_loss_rp': 0,
        'total_power_lwbp_rp': 0, 'total_power_wbp_rp': 0, 'total_power_loss_rp': 0, 'total_power_total_rp': 0,
        'total_output_yd': 0, 'total_steam_cost_rp': 0, 'total_power_lwbp_kwh': 0, 'total_power_wbp_kwh': 0,
        'group_name': 'Lain-lain', 'total_actual_mins': 0, 'total_ideal_mins': 0, 'total_pos_loss_time': 0,
        'total_power_loss_kwh': 0, 'total_pressure': 0.0, 'pressure_count': 0, 'total_delay_heat': 0.0, 'total_delay_cool': 0.0
    })

    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
    lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8
    wbp_mult = getattr(settings, 'wbp_multiplier', 1.4) or 1.4
    wbp_rate = round(lwbp_rate * wbp_mult, 2)
    steam_rate = getattr(settings, 'steam_cost_per_kg', 350.0) or 350.0

    for p in processes:
        identity = getattr(p, 'identity', None)
        program = identity.program if identity else None

        m_id = p.machine.id
        machine_eff_stats[m_id]['name'] = p.machine.name
        machine_eff_stats[m_id]['group_name'] = p.machine.group.name if p.machine.group else 'Lain-lain'
        machine_eff_stats[m_id]['batch_count'] += 1

        # 1. Akumulasi pemakaian Steam & Listrik Aktual untuk SELURUH batch valid di mesin ini
        if p.predicted_steam_kg:
            machine_eff_stats[m_id]['total_steam'] += p.predicted_steam_kg
            machine_eff_stats[m_id]['total_steam_cost_rp'] += p.predicted_steam_kg * steam_rate
            if p.predicted_steam_ideal_kg:
                machine_eff_stats[m_id]['total_steam_ideal'] += p.predicted_steam_ideal_kg
                machine_eff_stats[m_id]['total_steam_ideal_measured'] += p.predicted_steam_ideal_kg
                machine_eff_stats[m_id]['total_steam_with_ideal'] += p.predicted_steam_kg
                steam_loss = p.predicted_steam_kg - p.predicted_steam_ideal_kg
                if steam_loss > 0:
                    machine_eff_stats[m_id]['total_steam_loss_kg'] += steam_loss
                    machine_eff_stats[m_id]['total_steam_loss_rp'] += steam_loss * steam_rate
            else:
                machine_eff_stats[m_id]['total_steam_ideal'] += p.predicted_steam_kg

        elec_m = _compute_batch_electricity_metrics(p, program, lwbp_rate, wbp_rate)
        if elec_m['actual_kwh']:
            machine_eff_stats[m_id]['total_power'] += elec_m['actual_kwh']
        if p.power_consumption_lwbp_kwh:
            machine_eff_stats[m_id]['total_power_lwbp_kwh'] += p.power_consumption_lwbp_kwh
        if p.power_consumption_wbp_kwh:
            machine_eff_stats[m_id]['total_power_wbp_kwh'] += p.power_consumption_wbp_kwh
        if elec_m['cost_lwbp_rp']:
            machine_eff_stats[m_id]['total_power_lwbp_rp'] += elec_m['cost_lwbp_rp']
        if elec_m['cost_wbp_rp']:
            machine_eff_stats[m_id]['total_power_wbp_rp'] += elec_m['cost_wbp_rp']
        if elec_m['cost_actual_rp']:
            machine_eff_stats[m_id]['total_power_total_rp'] += elec_m['cost_actual_rp']

        if elec_m['ideal_kwh'] is not None and elec_m['actual_kwh'] is not None:
            machine_eff_stats[m_id]['total_power_ideal'] += elec_m['ideal_kwh']
            machine_eff_stats[m_id]['total_power_ideal_measured'] += elec_m['ideal_kwh']
            machine_eff_stats[m_id]['total_power_actual_measured'] += elec_m['actual_kwh']
            if elec_m['pos_loss_kwh'] > 0:
                machine_eff_stats[m_id]['total_power_loss_kwh'] += elec_m['pos_loss_kwh']
            if elec_m['cost_loss_rp'] > 0:
                machine_eff_stats[m_id]['total_power_loss_rp'] += elec_m['cost_loss_rp']
        elif elec_m['actual_kwh']:
            machine_eff_stats[m_id]['total_power_ideal'] += elec_m['actual_kwh']

        if p.avg_steam_pressure is not None:
            machine_eff_stats[m_id]['total_pressure'] += p.avg_steam_pressure
            machine_eff_stats[m_id]['pressure_count'] += 1
            if p.avg_steam_pressure >= threshold:
                machine_eff_stats[m_id]['steam_ok_count'] += 1

        if identity and identity.output_yard:
            machine_eff_stats[m_id]['total_output_yd'] += identity.output_yard

        # 2. Evaluasi Efisiensi Durasi & Pareto Masalah (khusus batch yang memiliki durasi ideal)
        if identity and program and p.duration_effective and program.durasi_ideal:
            total_analyzed += 1
            overall_eff = (program.durasi_ideal / p.duration_effective) * 100
            loss_time = p.duration_effective - program.durasi_ideal

            ideal_heat_keep = (program.durasi_heating_ideal or 0) + (program.durasi_keeping_ideal or 0)
            real_heat_keep = (p.real_heating_duration or 0) + (p.steady_duration or 0)
            delay_heat = real_heat_keep - ideal_heat_keep

            delay_cool = 0
            if program.durasi_cooling_ideal and p.cooling_duration:
                delay_cool = p.cooling_duration - program.durasi_cooling_ideal

            delay_total = p.duration_effective - program.durasi_ideal

            nomor_order  = identity.nomor_order if identity.nomor_order else "-"
            batch_kain   = identity.batch if identity.batch else "-"

            process_info = {
                "id": p.id,
                "machine_name": p.machine.name,
                "batch_number": p.batch_number,
                "nomor_order": nomor_order,
                "batch_kain": batch_kain,
                "jenis_proses": identity.jenis_proses if identity and identity.jenis_proses else "-",
                "output_yard": identity.output_yard if identity and identity.output_yard else 0.0,
                "start_time": timezone.localtime(p.start_time).strftime("%H:%M") if p.start_time else "-",
                "end_time": timezone.localtime(p.end_time).strftime("%H:%M") if p.end_time else "-",
                "total_duration": round(p.total_duration, 1) if p.total_duration else "-",
                "max_temp": round(p.max_temp, 1) if p.max_temp else "-",
                "eff_total": round(overall_eff, 1),
                "delay_heat": round(delay_heat, 1),
                "delay_cool": round(delay_cool, 1),
                "delay_total": round(delay_total, 1),
                "avg_steam_pressure": round(p.avg_steam_pressure, 2) if p.avg_steam_pressure is not None else None,
            }

            machine_eff_stats[m_id]['total_eff'] += overall_eff
            machine_eff_stats[m_id]['total_loss_time'] += loss_time
            machine_eff_stats[m_id]['total_actual_mins'] += (p.duration_effective or 0)
            machine_eff_stats[m_id]['total_ideal_mins'] += (program.durasi_ideal or 0)
            if loss_time > 0:
                machine_eff_stats[m_id]['total_pos_loss_time'] += loss_time
            machine_eff_stats[m_id]['count'] += 1
            if delay_heat > 0:
                machine_eff_stats[m_id]['total_delay_heat'] += delay_heat
            if delay_cool > 0:
                machine_eff_stats[m_id]['total_delay_cool'] += delay_cool

            machine_eff_stats[m_id]['processes'].append(process_info)

            if overall_eff < 85:
                total_low_efficiency += 1
                probs = classify_process_problems(p, program, pressure_threshold=threshold)

                for prob in probs:
                    if prob in eff_problem_data:
                        eff_problem_data[prob]["processes"].append(process_info)

    # -- START CONTINUOUS MACHINES INJECTION --
    cont_machines = Machine.objects.filter(group__process_type='CONTINUOUS', is_active=True).select_related('group')
    cont_dict = {m.code: m for m in cont_machines}
    cont_stats = {m.code: {'running_mins_lwbp': 0, 'running_mins_wbp': 0, 'steam_mins': 0} for m in cont_machines}

    for snapshot in snapshots:
        local_time = timezone.localtime(snapshot.timestamp)
        is_wbp = (17 <= local_time.hour < 22)

        for code, data in snapshot.snapshot_data.items():
            if code in cont_dict:
                status = data.get('status')
                detail = data.get('detail')
                is_machine_active = (status in ["HEAT", "STEADY", "Running", "COOL"]) or (detail in ["HEAT", "STEADY", "Running", "COOL"])
                if is_machine_active:
                    if is_wbp:
                        cont_stats[code]['running_mins_wbp'] += 1
                    else:
                        cont_stats[code]['running_mins_lwbp'] += 1

                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                if is_steam_active_from_snapshot(data):
                    cont_stats[code]['steam_mins'] += 1

    for code, stats in cont_stats.items():
        if stats['running_mins_lwbp'] > 0 or stats['running_mins_wbp'] > 0 or stats['steam_mins'] > 0:
            m = cont_dict[code]

            power_lwbp = (stats['running_mins_lwbp'] / 60.0) * (m.nominal_power or 0)
            power_wbp = (stats['running_mins_wbp'] / 60.0) * (m.nominal_power or 0)
            power = power_lwbp + power_wbp

            steam = (stats['steam_mins'] / 60.0) * (m.average_steam_usage or 0)

            total_power_kwh += power
            total_power_lwbp_kwh += power_lwbp
            total_power_wbp_kwh += power_wbp

            machine_eff_stats[m.id]['name'] = m.name
            machine_eff_stats[m.id]['group_name'] = m.group.name if m.group else 'Lain-lain'
            machine_eff_stats[m.id]['is_continuous'] = True

            machine_eff_stats[m.id]['total_power'] += power
            machine_eff_stats[m.id]['total_power_ideal'] += power
            machine_eff_stats[m.id]['total_steam'] += steam
            machine_eff_stats[m.id]['total_steam_ideal'] += steam
            machine_eff_stats[m.id]['total_power_lwbp_kwh'] += power_lwbp
            machine_eff_stats[m.id]['total_power_wbp_kwh'] += power_wbp

            power_lwbp_cost = power_lwbp * lwbp_rate
            power_wbp_cost = power_wbp * wbp_rate
            power_cost_est = power_lwbp_cost + power_wbp_cost
            steam_cost_est = steam * steam_rate

            machine_eff_stats[m.id]['total_power_total_rp'] += power_cost_est
            machine_eff_stats[m.id]['total_power_wbp_rp'] += power_wbp_cost
            machine_eff_stats[m.id]['total_power_lwbp_rp'] += power_lwbp_cost
            machine_eff_stats[m.id]['total_steam_cost_rp'] += steam_cost_est
    # -- END CONTINUOUS MACHINES INJECTION --

    # Build Efficiency Summary
    efficiency_summary_machines = []
    total_overall_eff = 0
    total_overall_count = 0

    for m_id, stats in machine_eff_stats.items():
        if stats['count'] > 0 or stats['batch_count'] > 0 or stats.get('is_continuous'):
            if stats.get('is_continuous') or stats['count'] == 0:
                avg_eff = None
                loss_time_str = None
            else:
                avg_eff = stats['total_eff'] / stats['count']
                total_loss_time = stats['total_loss_time']
                total_overall_eff += stats['total_eff']
                total_overall_count += stats['count']

                hours = int(total_loss_time // 60)
                mins = int(total_loss_time % 60)
                loss_time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                if total_loss_time < 0:
                    abs_loss = abs(total_loss_time)
                    h = int(abs_loss // 60)
                    m_min = int(abs_loss % 60)
                    loss_time_str = f"-{h}h {m_min}m" if h > 0 else f"-{m_min}m"

            steam_eff = None
            if stats['total_steam_with_ideal'] > 0:
                steam_eff = min(100.0, (stats['total_steam_ideal_measured'] / stats['total_steam_with_ideal']) * 100)

            power_eff = None
            if stats['total_power_actual_measured'] > 0:
                power_eff = min(100.0, (stats['total_power_ideal_measured'] / stats['total_power_actual_measured']) * 100)

            steam_ok_pct = None
            if stats['pressure_count'] > 0:
                steam_ok_pct = (stats['steam_ok_count'] / stats['pressure_count']) * 100

            out_yd = stats['total_output_yd']
            total_cost_rp = stats['total_steam_cost_rp'] + stats['total_power_total_rp']
            steam_cost_per_yd = stats['total_steam_cost_rp'] / out_yd if out_yd > 0 else 0
            power_cost_per_yd = stats['total_power_total_rp'] / out_yd if out_yd > 0 else 0
            total_cost_per_yd = total_cost_rp / out_yd if out_yd > 0 else 0

            efficiency_summary_machines.append({
                "machine_id": m_id,
                "machine_name": stats['name'],
                "group_name": stats.get('group_name', 'Lain-lain'),
                "actual_duration_mins": round(stats.get('total_actual_mins', 0), 1),
                "ideal_duration_mins": round(stats.get('total_ideal_mins', 0), 1),
                "pos_loss_time_mins": round(stats.get('total_pos_loss_time', 0), 1),
                "steam_ideal_kg": round(stats.get('total_steam_ideal', 0), 1),
                "power_ideal_kwh": round(stats.get('total_power_ideal', 0), 1),
                "power_loss_kwh": round(stats.get('total_power_loss_kwh', 0), 1),
                "avg_eff": round(avg_eff, 1) if avg_eff is not None else None,
                "total_loss_time_str": loss_time_str,
                "steam_usage": round(stats['total_steam'], 1),
                "steam_eff": round(steam_eff, 1) if steam_eff is not None else None,
                "steam_ok_pct": round(steam_ok_pct, 1) if steam_ok_pct is not None else None,
                "avg_steam_pressure": round(stats['total_pressure'] / stats['pressure_count'], 2) if stats.get('pressure_count', 0) > 0 else None,
                "delay_heat_mins": round(stats.get('total_delay_heat', 0), 1),
                "delay_cool_mins": round(stats.get('total_delay_cool', 0), 1),
                "power_usage": round(stats['total_power'], 1),
                "power_eff": round(power_eff, 1) if power_eff is not None else None,
                "avg_changeover_minutes": machine_changeover.get(m_id),
                "processes": stats['processes'],

                "steam_loss_kg": round(stats['total_steam_loss_kg'], 1),
                "steam_loss_rp": round(stats['total_steam_loss_rp'], 0),
                "power_lwbp_rp": round(stats['total_power_lwbp_rp'], 0),
                "power_wbp_rp": round(stats['total_power_wbp_rp'], 0),
                "total_power_lwbp_kwh": round(stats.get('total_power_lwbp_kwh', 0), 1),
                "total_power_wbp_kwh": round(stats.get('total_power_wbp_kwh', 0), 1),
                "power_loss_rp": round(stats['total_power_loss_rp'], 0),

                "output_yd": round(out_yd, 1),
                "steam_cost_per_yd": round(steam_cost_per_yd, 0),
                "power_cost_per_yd": round(power_cost_per_yd, 0),
                "total_cost_per_yd": round(total_cost_per_yd, 0)
            })
            
    efficiency_summary_machines.sort(key=lambda x: x['avg_eff'] if x['avg_eff'] is not None else 999)
    
    efficiency_summary = {
        "average": round(total_overall_eff / total_overall_count, 1) if total_overall_count > 0 else 0,
        "machines": efficiency_summary_machines
    }
                    
    # Proteksi ganda: Pastikan tidak ada ID proses yang terhitung ganda di PRESSURE_LOW dan HEATING_SLOW
    pressure_low_ids = set(p["id"] for p in eff_problem_data["PRESSURE_LOW"]["processes"])
    eff_problem_data["HEATING_SLOW"]["processes"] = [
        p for p in eff_problem_data["HEATING_SLOW"]["processes"]
        if p["id"] not in pressure_low_ids
    ]

    # Pareto: sort kategori by count desc + cumulative %
    problem_categories = [
        { "code": k, "label": v["label"], "count": len(v["processes"]), "color": v["color"], "processes": v["processes"] }
        for k, v in eff_problem_data.items()
        if len(v["processes"]) > 0
    ]
    problem_categories.sort(key=lambda x: x["count"], reverse=True)
    cumulative = 0
    for cat in problem_categories:
        cumulative += cat["count"]
        cat["cumulative_pct"] = round((cumulative / total_low_efficiency) * 100, 1) if total_low_efficiency > 0 else 0

    efficiency_problems = {
        "total_low_efficiency": total_low_efficiency,
        "total_analyzed": total_analyzed,
        "categories": problem_categories,
    }

    # ─────────────────────────────────────────────────────────────────
    # 7. DOWNTIME RANKING (dari bucket OFF, tanpa tabel baru)
    # ─────────────────────────────────────────────────────────────────
    downtime_ranking = _compute_downtime_ranking(machine_buckets, machine_meta, AVAIL_INTERVAL)

    # -------------------------------------------------------------
    # 8. DATA LOSSES HARIAN
    # -------------------------------------------------------------
    total_time_loss_mins = 0.0
    total_steam_loss_kg = 0.0
    total_power_loss_kwh = 0.0
    total_avail_loss_hours = 0.0

    # Availability Loss
    for m in machine_availabilities:
        if 'availability' in m:
            loss_pct = max(0.0, 100.0 - m['availability'])
            total_avail_loss_hours += (loss_pct / 100.0) * 24.0

    # Inefficiency Losses (Hanya yg positif)
    for p in processes:
        identity = getattr(p, 'identity', None)
        program = identity.program if identity else None

        # Time Loss
        if program and program.durasi_ideal and p.duration_effective:
            time_diff = p.duration_effective - program.durasi_ideal
            if time_diff > 0:
                total_time_loss_mins += time_diff

        # Steam Loss (Lapis 1 - Lapis 3)
        if p.predicted_steam_kg and p.predicted_steam_ideal_kg:
            steam_diff = p.predicted_steam_kg - p.predicted_steam_ideal_kg
            if steam_diff > 0:
                total_steam_loss_kg += steam_diff
        
        # Power Loss (dengan tambahan toleransi keluar-masuk kain <= 45 menit di durasi ideal)
        elec_m = _compute_batch_electricity_metrics(p, program, lwbp_rate)
        if elec_m['pos_loss_kwh'] > 0:
            total_power_loss_kwh += elec_m['pos_loss_kwh']

    losses_summary = {
        "time_loss_hours": round(total_time_loss_mins / 60.0, 1),
        "avail_loss_hours": round(total_avail_loss_hours, 1),
        "steam_loss_kg": round(total_steam_loss_kg, 1),
        "power_loss_kwh": round(total_power_loss_kwh, 1),
    }

    # ─────────────────────────────────────────────────────────────────
    # 8. OEE-LITE & KPI TURUNAN
    # ─────────────────────────────────────────────────────────────────
    avg_performance = efficiency_summary["average"]
    oee_combined = round(avg_avail * avg_performance / 100, 1) if avg_avail > 0 and avg_performance > 0 else 0

    total_process_count = processes.count()
    steam_per_batch = round(total_steam_usage / total_process_count, 1) if total_process_count > 0 else 0

    hours_availability = f"{round(avg_avail, 1)}%"
    performance_pct = f"{avg_performance}%"

    return {
        "date_range":         f"{start_time.strftime('%d %b %Y %H:%M')} - {end_time.strftime('%d %b %Y %H:%M')}",
        "total_steam_usage":  round(total_steam_usage, 1),
        "total_processes":    total_process_count,
        "steam_per_batch":    steam_per_batch,
        "avg_changeover_minutes": plant_avg_changeover,
        "hours_availability": hours_availability,
        "performance_pct":    performance_pct,
        "oee_lite": {
            "availability": round(avg_avail, 1),
            "performance": avg_performance,
            "combined": oee_combined,
        },
        "world_class": {
            "availability": 90,
            "performance": 95,
            "combined": 85,
        },
        "production_summary": {
            "power_kwh": round(total_power_kwh, 1),
            "power_lwbp_kwh": round(total_power_lwbp_kwh, 1),
            "power_wbp_kwh": round(total_power_wbp_kwh, 1),
            "fresh_yd": round(total_fresh_yd, 1),
            "creaping_yd": round(total_creaping_yd, 1),
            "other_yd": round(total_other_yd, 1),
        },
        "steam_series":       steam_series,
        "heatmap_groups":     groups_data,
        "history_groups":     history_groups,
        "availability_groups": availability_groups,
        "availability_summary": availability_summary,
        "efficiency_problems": efficiency_problems,
        "efficiency_summary": efficiency_summary,
        "downtime_ranking": downtime_ranking,
        "losses_summary": losses_summary,
    }

@report_router.get("/monthly-summary")
def get_monthly_summary(request, start_date: str, end_date: str):
    _require_permission(request, "monthly_report")
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}
    
    # Set range: 06:00 of start_date to 06:00 of (end_date + 1 day)
    start_time = timezone.make_aware(dt_start.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time = timezone.make_aware(dt_end.replace(hour=6, minute=0, second=0, microsecond=0)) + timedelta(days=1)
    
    # Total days in range
    days_count = (end_time - start_time).days
    
    # ─────────────────────────────────────────────────────────────────
    # 1. STEAM TRAFFIC (24 Jam)
    # ─────────────────────────────────────────────────────────────────
    from monitoring.models import MachineStatusSnapshot
    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp')
    
    all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0).select_related('group')
    machines_dict = {m.code: m for m in all_steam_machines}
    
    interval_minutes = 10
    TARGET_POINTS = 144
    
    # Initialize daily buckets: days_count x TARGET_POINTS
    daily_buckets = [[{'steam_total': 0.0, 'steam_count': 0, 'pressure': 0.0, 'pressure_count': 0} for _ in range(TARGET_POINTS)] for _ in range(days_count)]
    
    for snapshot in snapshots:
        local_time = timezone.localtime(snapshot.timestamp)
        shifted_time = local_time - timedelta(hours=6)
        day_diff = (shifted_time.date() - dt_start.date()).days
        if not (0 <= day_diff < days_count):
            continue
            
        day_start = timezone.make_aware(datetime.combine(shifted_time.date(), datetime.min.time()) + timedelta(hours=6))
        time_diff = (local_time - day_start).total_seconds() / 60
        bucket_index = int(time_diff / interval_minutes)
        if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
        if bucket_index < 0: bucket_index = 0
        
        steam_total = 0.0
        steam_total_jet = 0.0
        steam_total_non_jet = 0.0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = machines_dict.get(machine_code)
            if machine:
                is_active = False
                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                is_active = is_steam_active_from_snapshot(snap_data)
                if is_active:
                    steam_total += machine.average_steam_usage
                    if machine.group and machine.group.process_type == 'JET':
                        steam_total_jet += machine.average_steam_usage
                    else:
                        steam_total_non_jet += machine.average_steam_usage
                    
        daily_buckets[day_diff][bucket_index]['steam_total'] += steam_total
        if 'steam_total_jet' not in daily_buckets[day_diff][bucket_index]:
            daily_buckets[day_diff][bucket_index]['steam_total_jet'] = 0.0
            daily_buckets[day_diff][bucket_index]['steam_total_non_jet'] = 0.0
        daily_buckets[day_diff][bucket_index]['steam_total_jet'] += steam_total_jet
        daily_buckets[day_diff][bucket_index]['steam_total_non_jet'] += steam_total_non_jet
        daily_buckets[day_diff][bucket_index]['steam_count'] += 1
        
    steam_pr_logs = MachineMinuteLog.objects.filter(
        machine__code="Steam_Pr",
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp')
    
    for log in steam_pr_logs:
        if log.temperature is not None:
            local_time = timezone.localtime(log.timestamp)
            shifted_time = local_time - timedelta(hours=6)
            day_diff = (shifted_time.date() - dt_start.date()).days
            if not (0 <= day_diff < days_count):
                continue
                
            day_start = timezone.make_aware(datetime.combine(shifted_time.date(), datetime.min.time()) + timedelta(hours=6))
            time_diff = (local_time - day_start).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            if bucket_index >= TARGET_POINTS: bucket_index = TARGET_POINTS - 1
            if bucket_index < 0: bucket_index = 0
            
            daily_buckets[day_diff][bucket_index]['pressure'] += log.temperature
            daily_buckets[day_diff][bucket_index]['pressure_count'] += 1

    # Apply forward fill for each day so sparse logs don't randomly drop to 0
    for d in range(days_count):
        last_pressure = 0.0
        last_usage = 0.0
        for i in range(TARGET_POINTS):
            b = daily_buckets[d][i]
            
            if b['pressure_count'] > 0:
                b['avg_pressure'] = b['pressure'] / b['pressure_count']
                last_pressure = b['avg_pressure']
            else:
                b['avg_pressure'] = last_pressure
                
            if b['steam_count'] > 0:
                b['avg_usage'] = b['steam_total'] / b['steam_count']
                last_usage = b['avg_usage']
            else:
                b['avg_usage'] = last_usage

    steam_series = []
    total_steam_usage = 0.0
    
    for i in range(TARGET_POINTS):
        bucket_start_dummy = start_time + timedelta(minutes=i * interval_minutes)
        valid_usage_sum = 0.0
        valid_pressure_sum = 0.0
        valid_days_count = 0
        
        for d in range(days_count):
            b = daily_buckets[d][i]
            p_val = b['avg_pressure']
            u_val = b['avg_usage']
            
            # Hanya rata-ratakan data hari tsb JIKA pada JAM tsb memenuhi syarat
            if p_val > 1.00 and u_val > 0:
                valid_usage_sum += u_val
                valid_pressure_sum += p_val
                valid_days_count += 1
                
        avg_steam = valid_usage_sum / valid_days_count if valid_days_count > 0 else 0.0
        avg_pressure = valid_pressure_sum / valid_days_count if valid_days_count > 0 else 0.0
        
        steam_series.append({
            "time": timezone.localtime(bucket_start_dummy).strftime("%H:%M"),
            "usage": round(avg_steam, 1),
            "pressure": round(avg_pressure, 2)
        })
        total_steam_usage += avg_steam * (interval_minutes / 60.0)

    # ─────────────────────────────────────────────────────────────────
    # 2. DYEING PROCESSES & HEATMAP
    # ─────────────────────────────────────────────────────────────────
    processes = DyeingProcess.objects.filter(
        start_time__gte=start_time,
        start_time__lt=end_time,
        is_valid_process=True
    ).exclude(
        machine__group__code='MC_BOILER'
    ).select_related('machine', 'machine__group', 'identity', 'identity__program')
    
    process_counts = {}
    history_table = {}
    
    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
    
    total_power_lwbp_kwh = 0.0
    total_power_wbp_kwh = 0.0
    total_power_kwh = 0.0
    total_fresh_yd = 0.0
    total_creaping_yd = 0.0
    total_other_yd = 0.0

    for p in processes:
        m_id = p.machine_id
        if m_id not in process_counts:
            process_counts[m_id] = 0
        process_counts[m_id] += 1
        
        group_name = p.machine.group.name if p.machine.group else "Lain-lain"
        if group_name not in history_table:
            history_table[group_name] = []
            
        identity = getattr(p, 'identity', None)
        nomor_order  = identity.nomor_order  if identity and identity.nomor_order  else "-"
        artikel_kain = identity.artikel_kain if identity and identity.artikel_kain else "-"
        batch_kain   = identity.batch        if identity and identity.batch        else "-"
        
        history_table[group_name].append({
            "id":           p.id,
            "machine_id":   p.machine.id,
            "machine_name": p.machine.name,
            "machine_code": p.machine.code,
            "batch_number": p.batch_number,
            "start_time":   timezone.localtime(p.start_time).strftime("%d %b %H:%M") if p.start_time else "-",
            "end_time":     timezone.localtime(p.end_time).strftime("%d %b %H:%M")   if p.end_time   else "-",
            "duration":     round(p.total_duration, 1) if p.total_duration else "-",
            "max_temp":     round(p.max_temp, 1)       if p.max_temp       else "-",
            "status":       "Selesai" if p.is_complete else "Berjalan",
            "nomor_order":  nomor_order,
            "artikel_kain": artikel_kain,
            "batch_kain":   batch_kain,
        })
        
    history_groups = []
    for gname, items in history_table.items():
        items.sort(key=lambda x: x["start_time"])
        sort_machines_custom(items, name_key="machine_name")
        history_groups.append({"group_name": gname, "items": items})
    history_groups.sort(key=lambda x: x["group_name"])

    groups = MachineGroup.objects.filter(machine__is_active=True).exclude(code='MC_BOILER').distinct().order_by('name')
    groups_data = []
    for group in groups:
        machines = Machine.objects.filter(group=group, is_active=True).order_by('name')
        if not machines.exists():
            continue
        group_processes = 0
        machines_data = []
        for m in machines:
            count = process_counts.get(m.id, 0)
            group_processes += count
            machines_data.append({"id": m.id, "name": m.name, "process_count": count})
            
        sort_machines_custom(machines_data, name_key="name")
        groups_data.append({
            "group_name":            group.name,
            "machine_count":         machines.count(),
            "total_group_processes": group_processes,
            "machines":              machines_data,
        })

    return {
        "date_range":         f"{dt_start.strftime('%d %b %Y')} - {dt_end.strftime('%d %b %Y')}",
        "total_steam_usage":  round(total_steam_usage, 1),
        "total_processes":    processes.count(),
        "steam_series":       steam_series,
        "heatmap_groups":     groups_data,
        "history_groups":     history_groups,
    }
@report_router.get("/machine/{machine_id}/daily-chart")
def get_report_machine_daily_chart(request, machine_id: int, date: str):
    _require_permission(request, "daily_report")
    machine = get_object_or_404(Machine, id=machine_id)
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}
    start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time   = start_time + timedelta(days=1)

    # Check whether this machine uses HTO instead of Steam
    uses_hto = (machine.average_steam_usage or 0) <= 0 and (machine.avg_hto_calories or 0) > 0
    secondary_code = 'Oil_Temp' if uses_hto else 'Steam_Pr'
    secondary_label = 'Temperatur HTO' if uses_hto else 'Tekanan Steam'
    secondary_unit = '°C' if uses_hto else 'bar'

    machine_logs = MachineMinuteLog.objects.filter(
        machine=machine, timestamp__gte=start_time, timestamp__lte=end_time
    ).order_by('timestamp')
    sec_logs = MachineMinuteLog.objects.filter(
        machine__code=secondary_code, timestamp__gte=start_time, timestamp__lte=end_time
    ).order_by('timestamp')

    timeline_dt = {}
    for log in machine_logs:
        t      = timezone.localtime(log.timestamp)
        dt_key = t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)
        timeline_dt[dt_key] = {"temp": log.temperature or 0, "pressure": 0, "secondary_val": 0}
    for log in sec_logs:
        t      = timezone.localtime(log.timestamp)
        dt_key = t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)
        if dt_key in timeline_dt:
            val = round(log.temperature or 0, 2 if not uses_hto else 1)
            timeline_dt[dt_key]["pressure"] = val
            timeline_dt[dt_key]["secondary_val"] = val
    sorted_keys = sorted(timeline_dt.keys())
    chart_data  = []
    for k in sorted_keys:
        val = timeline_dt[k]
        is_end = (k >= end_time)
        time_label = "06:00 " if is_end else k.strftime("%H:%M")
        chart_data.append({
            "time":          time_label,
            "full_time":     k.strftime("%d %b %H:%M"),
            "temp":          round(val["temp"], 1),
            "pressure":      round(val["pressure"], 2),
            "secondary_val": round(val["secondary_val"], 2 if not uses_hto else 1),
        })
    # Get DyeingProcess batches for this machine on this day
    batches = DyeingProcess.objects.filter(
        machine=machine,
        start_time__gte=start_time,
        start_time__lt=end_time
    ).select_related('identity', 'identity__program').order_by('start_time')
    
    from monitoring.models import GlobalSettings, CompanyProfile
    settings = GlobalSettings.load()
    lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8

    batches_data = []
    for b in batches:
        ident = getattr(b, 'identity', None)
        prog = ident.program if ident else None
        
        ideal = prog.durasi_ideal if prog else None
        dur_eff = b.duration_effective
        eff_total = None
        if ideal and dur_eff:
            eff_total = round((ideal / dur_eff) * 100, 1)
            
        steam_eff = None
        if b.predicted_steam_ideal_kg and b.predicted_steam_kg:
            steam_eff = round((b.predicted_steam_ideal_kg / b.predicted_steam_kg) * 100, 1)
            
        elec_m = _compute_batch_electricity_metrics(b, prog, lwbp_rate)
        power_eff = elec_m['power_eff']

        steam_loss_kg = None
        if b.predicted_steam_kg is not None and b.predicted_steam_ideal_kg is not None:
            steam_loss_kg = round(b.predicted_steam_kg - b.predicted_steam_ideal_kg, 1)

        power_loss_kwh = round(elec_m['pos_loss_kwh'], 1) if elec_m['raw_diff_kwh'] is not None else None

        ref_start = b.heating_start_time or b.start_time
        real_total_dur = None
        if b.end_time and ref_start:
            real_total_dur = round((b.end_time - ref_start).total_seconds() / 60, 1)

        late_stop_mins = None
        if b.reached_70c_time and b.end_time and b.end_time > b.reached_70c_time:
            late_stop_mins = round((b.end_time - b.reached_70c_time).total_seconds() / 60, 1)

        pre_heat_mins = None
        if b.start_time and b.heating_start_time and b.heating_start_time > b.start_time:
            pre_heat_mins = round((b.heating_start_time - b.start_time).total_seconds() / 60, 1)

        ideal_heating = round(prog.durasi_heating_ideal, 1) if (prog and prog.durasi_heating_ideal is not None) else None
        delta_heating = round(b.real_heating_duration - prog.durasi_heating_ideal, 1) if (b.real_heating_duration is not None and prog and prog.durasi_heating_ideal is not None) else None

        ideal_steady = round(prog.durasi_keeping_ideal, 1) if (prog and prog.durasi_keeping_ideal is not None) else None
        delta_steady = round(b.steady_duration - prog.durasi_keeping_ideal, 1) if (b.steady_duration is not None and prog and prog.durasi_keeping_ideal is not None) else None

        ideal_cooling = round(prog.durasi_cooling_ideal, 1) if (prog and prog.durasi_cooling_ideal is not None) else None
        delta_cooling = round(b.cooling_duration - prog.durasi_cooling_ideal, 1) if (b.cooling_duration is not None and prog and prog.durasi_cooling_ideal is not None) else None

        loss_time = round((dur_eff or real_total_dur) - ideal, 1) if ((dur_eff or real_total_dur) is not None and ideal is not None) else None
        grade = 'A' if (eff_total and eff_total >= 80) else ('B' if (eff_total and eff_total >= 60) else ('C' if eff_total else '-'))

        batches_data.append({
            "id": b.id,
            "batch_number": b.batch_number,
            "late_stop_mins": late_stop_mins,
            "pre_heat_mins": pre_heat_mins,
            "batch_kain": ident.batch if (ident and ident.batch) else "-",
            "jenis_proses": ident.get_jenis_proses_display() if (ident and ident.jenis_proses) else "-",
            "program": prog.nama if prog else "-",
            "output_yd": round(ident.output_yard, 1) if (ident and ident.output_yard) else "-",
            "nozzle_main_pump": ident.nozzle_main_pump if (ident and ident.nozzle_main_pump) else "-",
            "cycle_puncak": ident.cycle_puncak if (ident and ident.cycle_puncak) else "-",
            "cycle_60": ident.cycle_60 if (ident and ident.cycle_60) else "-",
            "artikel": ident.artikel_kain if (ident and ident.artikel_kain) else "-",
            "no_order": ident.nomor_order if (ident and ident.nomor_order) else "-",
            "kode_buyer": ident.kode_buyer if (ident and ident.kode_buyer) else "-",
            "nomor_warna": ident.nomor_warna if (ident and ident.nomor_warna) else "-",
            "nomor_desain": ident.nomor_desain if (ident and ident.nomor_desain) else "-",
            "warna_desain": f"{ident.nomor_warna} / {ident.nomor_desain}" if (ident and ident.nomor_warna and ident.nomor_desain) else (ident.nomor_warna if (ident and ident.nomor_warna) else (ident.nomor_desain if (ident and ident.nomor_desain) else "-")),
            "isi_per_tube": ident.isi_per_tube if (ident and ident.isi_per_tube) else "-",
            "operator": ident.operator if (ident and ident.operator) else "-",
            "handling_quality": ident.handling_quality if (ident and ident.handling_quality) else "-",
            "masalah": ident.masalah if (ident and ident.masalah) else None,
            "keterangan": ident.keterangan if (ident and ident.keterangan) else None,
            "jam_mulai": timezone.localtime(ref_start).strftime("%H:%M") if ref_start else "-",
            "jam_selesai": timezone.localtime(b.end_time).strftime("%H:%M") if b.end_time else "-",
            "total_durasi": real_total_dur if real_total_dur is not None else "-",
            "durasi_aktif": round(dur_eff, 1) if dur_eff is not None else real_total_dur,
            "durasi_ideal": ideal if ideal else "-",
            "loss_time": loss_time,
            "eff_total": eff_total,
            "grade": grade,
            "real_heating": round(b.real_heating_duration, 1) if b.real_heating_duration is not None else "-",
            "ideal_heating": ideal_heating,
            "delta_heating": delta_heating,
            "real_steady": round(b.steady_duration, 1) if b.steady_duration is not None else "-",
            "ideal_steady": ideal_steady,
            "delta_steady": delta_steady,
            "real_cooling": round(b.cooling_duration, 1) if b.cooling_duration is not None else "-",
            "ideal_cooling": ideal_cooling,
            "delta_cooling": delta_cooling,
            "start_temp": round(b.start_temp, 1) if b.start_temp is not None else "-",
            "max_temp": round(b.max_temp, 1) if b.max_temp is not None else "-",
            "suhu_prog": round(prog.suhu_max, 1) if (prog and prog.suhu_max is not None) else "-",
            "heating_gradient": round(b.heating_avg_gradient, 2) if b.heating_avg_gradient is not None else "-",
            "cooling_gradient": round(b.cooling_avg_gradient, 2) if b.cooling_avg_gradient is not None else "-",
            "avg_steam_pressure": round(b.avg_steam_pressure, 2) if b.avg_steam_pressure is not None else "-",
            "steam_usage": round(b.predicted_steam_kg, 1) if b.predicted_steam_kg is not None else "-",
            "steam_eff": steam_eff,
            "steam_loss_kg": steam_loss_kg,
            "power_usage": round(b.power_consumption_kwh, 1) if b.power_consumption_kwh is not None else "-",
            "power_eff": power_eff,
            "power_loss_kwh": power_loss_kwh,
        })

    # Fetch summary for this machine
    daily_summary = _compute_daily_summary_data(date)
    machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)

    cp = CompanyProfile.objects.first()
    company_info = {
        "name": cp.name if (cp and cp.name) else "Suritex Factory",
        "logo": cp.logo.url if (cp and cp.logo) else None,
    }

    return {
        "summary":         machine_stats,
        "machine_name":    machine.name,
        "machine_code":    getattr(machine, 'code', None) or machine.name,
        "machine_group":   getattr(machine.group, 'name', None) if getattr(machine, 'group', None) else "-",
        "energy_type":     "HTO" if uses_hto else "STEAM",
        "secondary_label": secondary_label,
        "secondary_unit":  secondary_unit,
        "date_range":      f"{start_time.strftime('%d %b %H:%M')} - {end_time.strftime('%d %b %H:%M')}",
        "chart_data":      chart_data,
        "batches":         batches_data,
        "company":         company_info,
    }

@report_router.get("/machine/{machine_id}/daily-chart-deep")
def get_report_machine_daily_chart_deep(request, machine_id: int, date: str):
    """
    Endpoint analitik mendalam mesin (60-batch historical scatter, evaluasi 3 fase,
    analisis jeda turnaround 24 jam, dan tiket pemeliharaan preskriptif mekanik).
    """
    _require_permission(request, "daily_report")
    machine = get_object_or_404(Machine, id=machine_id)
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}
    
    start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time   = start_time + timedelta(days=1)
    
    # 1. Base chart data (Suhu aktual vs Tekanan Uap 24 jam)
    machine_logs = MachineMinuteLog.objects.filter(
        machine=machine, timestamp__gte=start_time, timestamp__lt=end_time
    ).order_by('timestamp')
    steam_logs = MachineMinuteLog.objects.filter(
        machine__code='Steam_Pr', timestamp__gte=start_time, timestamp__lt=end_time
    ).order_by('timestamp')
    
    timeline_dt = {}
    for log in machine_logs:
        t = timezone.localtime(log.timestamp)
        dt_key = t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)
        timeline_dt[dt_key] = {"temp": log.temperature or 0, "pressure": 0}
    for log in steam_logs:
        t = timezone.localtime(log.timestamp)
        dt_key = t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)
        if dt_key in timeline_dt:
            timeline_dt[dt_key]["pressure"] = log.temperature or 0
    
    sorted_keys = sorted(timeline_dt.keys())
    chart_data = []
    for k in sorted_keys:
        val = timeline_dt[k]
        chart_data.append({
            "time": k.strftime("%H:%M"),
            "full_time": k.strftime("%d %b %H:%M"),
            "temp": round(val["temp"], 1),
            "pressure": round(val["pressure"], 2),
        })
        
    # 2. Batch yang berjalan hari ini pada mesin ini
    batches = DyeingProcess.objects.filter(
        machine=machine,
        start_time__gte=start_time,
        start_time__lt=end_time
    ).select_related('identity', 'identity__program').order_by('start_time')
    
    today_batch_ids = set(batches.values_list('id', flat=True))
    
    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8

    batches_data = []
    for b in batches:
        ident = getattr(b, 'identity', None)
        prog = ident.program if ident else None
        
        ideal = prog.durasi_ideal if prog else None
        dur_eff = b.duration_effective
        eff_total = None
        if ideal and dur_eff:
            eff_total = round((ideal / dur_eff) * 100, 1)
            
        steam_eff = None
        if b.predicted_steam_ideal_kg and b.predicted_steam_kg:
            steam_eff = round((b.predicted_steam_ideal_kg / b.predicted_steam_kg) * 100, 1)
            
        elec_m = _compute_batch_electricity_metrics(b, prog, lwbp_rate)
        power_eff = elec_m['power_eff']

        steam_loss_kg = None
        if b.predicted_steam_kg is not None and b.predicted_steam_ideal_kg is not None:
            steam_loss_kg = round(b.predicted_steam_kg - b.predicted_steam_ideal_kg, 1)

        power_loss_kwh = round(elec_m['pos_loss_kwh'], 1) if elec_m['raw_diff_kwh'] is not None else None

        ref_start = b.heating_start_time or b.start_time
        real_total_dur = None
        if b.end_time and ref_start:
            real_total_dur = round((b.end_time - ref_start).total_seconds() / 60, 1)

        ideal_heating = round(prog.durasi_heating_ideal, 1) if (prog and prog.durasi_heating_ideal is not None) else None
        delta_heating = round(b.real_heating_duration - prog.durasi_heating_ideal, 1) if (b.real_heating_duration is not None and prog and prog.durasi_heating_ideal is not None) else None

        ideal_steady = round(prog.durasi_keeping_ideal, 1) if (prog and prog.durasi_keeping_ideal is not None) else None
        delta_steady = round(b.steady_duration - prog.durasi_keeping_ideal, 1) if (b.steady_duration is not None and prog and prog.durasi_keeping_ideal is not None) else None

        ideal_cooling = round(prog.durasi_cooling_ideal, 1) if (prog and prog.durasi_cooling_ideal is not None) else None
        delta_cooling = round(b.cooling_duration - prog.durasi_cooling_ideal, 1) if (b.cooling_duration is not None and prog and prog.durasi_cooling_ideal is not None) else None

        late_stop_mins = None
        if b.reached_70c_time and b.end_time and b.end_time > b.reached_70c_time:
            late_stop_mins = round((b.end_time - b.reached_70c_time).total_seconds() / 60, 1)

        pre_heat_mins = None
        if b.start_time and b.heating_start_time and b.heating_start_time > b.start_time:
            pre_heat_mins = round((b.heating_start_time - b.start_time).total_seconds() / 60, 1)

        batches_data.append({
            "id": b.id,
            "batch_number": b.batch_number,
            "late_stop_mins": late_stop_mins,
            "pre_heat_mins": pre_heat_mins,
            "batch_kain": ident.batch if (ident and ident.batch) else "-",
            "jenis_proses": ident.get_jenis_proses_display() if (ident and ident.jenis_proses) else "-",
            "program": prog.nama if prog else "-",
            "output_yd": round(ident.output_yard, 1) if (ident and ident.output_yard) else "-",
            "nozzle_main_pump": ident.nozzle_main_pump if (ident and ident.nozzle_main_pump) else "-",
            "cycle_puncak": ident.cycle_puncak if (ident and ident.cycle_puncak) else "-",
            "cycle_60": ident.cycle_60 if (ident and ident.cycle_60) else "-",
            "artikel": ident.artikel_kain if (ident and ident.artikel_kain) else "-",
            "no_order": ident.nomor_order if (ident and ident.nomor_order) else "-",
            "jam_mulai": timezone.localtime(ref_start).strftime("%H:%M") if ref_start else "-",
            "jam_selesai": timezone.localtime(b.end_time).strftime("%H:%M") if b.end_time else "-",
            "total_durasi": real_total_dur if real_total_dur is not None else "-",
            "durasi_ideal": ideal if ideal else "-",
            "eff_total": eff_total,
            "steam_usage": round(b.predicted_steam_kg, 1) if b.predicted_steam_kg is not None else "-",
            "steam_eff": steam_eff,
            "steam_loss_kg": steam_loss_kg,
            "power_usage": round(b.power_consumption_kwh, 1) if b.power_consumption_kwh is not None else "-",
            "power_eff": power_eff,
            "power_loss_kwh": power_loss_kwh,
            "real_heating": round(b.real_heating_duration, 1) if b.real_heating_duration is not None else "-",
            "ideal_heating": ideal_heating,
            "delta_heating": delta_heating,
            "real_cooling": round(b.cooling_duration, 1) if b.cooling_duration is not None else "-",
            "ideal_cooling": ideal_cooling,
            "delta_cooling": delta_cooling,
            "real_steady": round(b.steady_duration, 1) if b.steady_duration is not None else "-",
            "ideal_steady": ideal_steady,
            "delta_steady": delta_steady,
            "avg_steam_pressure": round(b.avg_steam_pressure, 2) if b.avg_steam_pressure is not None else "-",
        })

    # 3. Ambil 60 Batch Historis Mesin Ini untuk Analisis Korelasi Durasi vs Tekanan
    hist_qs = DyeingProcess.objects.filter(
        machine=machine,
        is_valid_process=True
    ).select_related('identity', 'identity__program').order_by('-start_time')[:60]

    historical_scatter = []
    programs_map = defaultdict(lambda: {
        'count': 0, 'total_list': [], 'heat_list': [], 'cool_list': [], 'steady_list': [], 'pressure_list': [],
        'ideal_heat': None, 'ideal_cool': None, 'ideal_steady': None, 'ideal_total': None,
        'suhu_max': None
    })

    for hb in hist_qs:
        h_ident = getattr(hb, 'identity', None)
        h_prog = h_ident.program if h_ident else None
        
        prog_name = h_prog.nama if h_prog else "Tanpa Program"
        heat_ideal = h_prog.durasi_heating_ideal if h_prog else None
        cool_ideal = h_prog.durasi_cooling_ideal if h_prog else None
        steady_ideal = h_prog.durasi_keeping_ideal if h_prog else None
        total_ideal = h_prog.durasi_ideal if h_prog else None
        
        hb_start = hb.heating_start_time or hb.start_time
        real_total = None
        if hb.end_time and hb_start:
            real_total = round((hb.end_time - hb_start).total_seconds() / 60, 1)
        elif hb.duration_effective:
            real_total = round(hb.duration_effective, 1)

        real_heat = round(hb.real_heating_duration, 1) if hb.real_heating_duration is not None else None
        real_cool = round(hb.cooling_duration, 1) if hb.cooling_duration is not None else None
        real_steady = round(hb.steady_duration, 1) if hb.steady_duration is not None else None
        avg_pr = round(hb.avg_steam_pressure, 2) if hb.avg_steam_pressure is not None else None

        # Evaluasi Kuadran Diagnostik
        quadrant = "OPTIMAL"
        diag_label = "Optimal"
        if real_heat is not None and heat_ideal is not None and avg_pr is not None:
            if real_heat > heat_ideal + 15 and avg_pr >= 4.0:
                quadrant = "MECHANICAL_DEGRADATION"
                diag_label = "Degradasi Mekanik / Kerak HE"
            elif real_heat > heat_ideal + 10 and avg_pr < 3.8:
                quadrant = "BOILER_DROP"
                diag_label = "Pasokan Boiler Drop (<3.8 bar)"
            elif real_heat <= heat_ideal + 10 and avg_pr >= 3.8:
                quadrant = "OPTIMAL"
                diag_label = "Optimal & Sesuai Program"
            elif real_heat < heat_ideal - 20:
                quadrant = "ANOMALOUS_FAST"
                diag_label = "Pemanasan Cepat / Load Rendah"
            else:
                quadrant = "MODERATE_DELAY"
                diag_label = "Deviasi Wajar"

        # Laju kenaikan suhu & laju pendinginan
        ramp_rate = None
        if hb.max_temp and real_heat and real_heat > 0:
            ramp_rate = round((hb.max_temp - 40.0) / real_heat, 2)
        cooling_rate = None
        if hb.max_temp and real_cool and real_cool > 0:
            cooling_rate = round((hb.max_temp - 60.0) / real_cool, 2)

        start_dt = timezone.localtime(hb.start_time) if hb.start_time else None
        
        item = {
            "id": hb.id,
            "batch_number": hb.batch_number,
            "date": start_dt.strftime("%d/%m/%Y") if start_dt else "-",
            "jam": start_dt.strftime("%H:%M") if start_dt else "-",
            "is_today": (hb.id in today_batch_ids),
            "program_name": prog_name,
            "program_id": h_prog.id if h_prog else None,
            "suhu_max": h_prog.suhu_max if h_prog else None,
            "max_temp": round(hb.max_temp, 1) if hb.max_temp else None,
            "real_total": real_total,
            "ideal_total": total_ideal,
            "delta_total": round(real_total - total_ideal, 1) if (real_total is not None and total_ideal) else None,
            "real_heat": real_heat,
            "ideal_heat": heat_ideal,
            "delta_heat": round(real_heat - heat_ideal, 1) if (real_heat is not None and heat_ideal) else None,
            "real_cool": real_cool,
            "ideal_cool": cool_ideal,
            "delta_cool": round(real_cool - cool_ideal, 1) if (real_cool is not None and cool_ideal) else None,
            "real_steady": real_steady,
            "ideal_steady": steady_ideal,
            "delta_steady": round(real_steady - steady_ideal, 1) if (real_steady is not None and steady_ideal) else None,
            "avg_steam_pressure": avg_pr,
            "ramp_rate": ramp_rate,
            "cooling_rate": cooling_rate,
            "quadrant": quadrant,
            "diag_label": diag_label,
        }
        historical_scatter.append(item)

        # Akumulasi program benchmark
        p_stat = programs_map[prog_name]
        p_stat['count'] += 1
        if real_total is not None: p_stat['total_list'].append(real_total)
        if real_heat is not None: p_stat['heat_list'].append(real_heat)
        if real_cool is not None: p_stat['cool_list'].append(real_cool)
        if real_steady is not None: p_stat['steady_list'].append(real_steady)
        if avg_pr is not None: p_stat['pressure_list'].append(avg_pr)
        if p_stat['ideal_heat'] is None:
            p_stat['ideal_heat'] = heat_ideal
            p_stat['ideal_cool'] = cool_ideal
            p_stat['ideal_steady'] = steady_ideal
            p_stat['ideal_total'] = total_ideal
            p_stat['suhu_max'] = h_prog.suhu_max if h_prog else None

    # Benchmark summary per program
    program_benchmarks = []
    for pname, pinfo in programs_map.items():
        c = pinfo['count']
        avg_tot = round(sum(pinfo['total_list']) / len(pinfo['total_list']), 1) if pinfo['total_list'] else None
        avg_h = round(sum(pinfo['heat_list']) / len(pinfo['heat_list']), 1) if pinfo['heat_list'] else None
        avg_c = round(sum(pinfo['cool_list']) / len(pinfo['cool_list']), 1) if pinfo['cool_list'] else None
        avg_s = round(sum(pinfo['steady_list']) / len(pinfo['steady_list']), 1) if pinfo['steady_list'] else None
        avg_p = round(sum(pinfo['pressure_list']) / len(pinfo['pressure_list']), 2) if pinfo['pressure_list'] else None

        delta_tot_avg = round(avg_tot - pinfo['ideal_total'], 1) if (avg_tot is not None and pinfo['ideal_total']) else None
        delta_h_avg = round(avg_h - pinfo['ideal_heat'], 1) if (avg_h is not None and pinfo['ideal_heat']) else None
        delta_c_avg = round(avg_c - pinfo['ideal_cool'], 1) if (avg_c is not None and pinfo['ideal_cool']) else None

        program_benchmarks.append({
            "program_name": pname,
            "batch_count": c,
            "ideal_total": pinfo['ideal_total'],
            "avg_total": avg_tot,
            "delta_total_avg": delta_tot_avg,
            "ideal_heat": pinfo['ideal_heat'],
            "ideal_cool": pinfo['ideal_cool'],
            "ideal_steady": pinfo['ideal_steady'],
            "suhu_max": pinfo['suhu_max'],
            "avg_heat": avg_h,
            "avg_cool": avg_c,
            "avg_steady": avg_s,
            "avg_pressure": avg_p,
            "delta_heat_avg": delta_h_avg,
            "delta_cool_avg": delta_c_avg,
        })
    program_benchmarks.sort(key=lambda x: x['batch_count'], reverse=True)

    # 4. Turnaround & Changeover 24 Jam
    turnaround_events = []
    total_run_mins = 0
    total_changeover_mins = 0
    total_unexplained_idle_mins = 0

    sorted_today_batches = sorted(batches, key=lambda x: x.start_time or timezone.now())
    prev_end = start_time

    for b in sorted_today_batches:
        b_start = b.start_time or start_time
        b_end = b.end_time or b_start
        
        # Jeda sebelum batch ini
        gap_mins = max(0, int((b_start - prev_end).total_seconds() / 60))
        if gap_mins > 0:
            if gap_mins <= 35:
                # Normal changeover
                turnaround_events.append({
                    "type": "CHANGEOVER",
                    "label": f"Bongkar/Muat ke B#{b.batch_number}",
                    "start": timezone.localtime(prev_end).strftime("%H:%M"),
                    "end": timezone.localtime(b_start).strftime("%H:%M"),
                    "duration_mins": gap_mins,
                    "is_excess": False
                })
                total_changeover_mins += gap_mins
            else:
                # Normal portion + excess idle
                turnaround_events.append({
                    "type": "IDLE",
                    "label": f"Idle/Tunggu Kain ke B#{b.batch_number}",
                    "start": timezone.localtime(prev_end).strftime("%H:%M"),
                    "end": timezone.localtime(b_start).strftime("%H:%M"),
                    "duration_mins": gap_mins,
                    "is_excess": True
                })
                total_changeover_mins += 30
                total_unexplained_idle_mins += (gap_mins - 30)

        # Event proses batch itu sendiri
        run_dur = max(0, int((b_end - b_start).total_seconds() / 60))
        turnaround_events.append({
            "type": "PROCESS",
            "batch_number": b.batch_number,
            "label": f"Batch #{b.batch_number}",
            "start": timezone.localtime(b_start).strftime("%H:%M"),
            "end": timezone.localtime(b_end).strftime("%H:%M"),
            "duration_mins": run_dur,
        })
        total_run_mins += run_dur
        prev_end = b_end

    # Sisa waktu sampai 06:00 esok
    final_gap = max(0, int((end_time - prev_end).total_seconds() / 60))
    if final_gap > 0:
        turnaround_events.append({
            "type": "IDLE",
            "label": "Idle Akhir Siklus",
            "start": timezone.localtime(prev_end).strftime("%H:%M"),
            "end": timezone.localtime(end_time).strftime("%H:%M"),
            "duration_mins": final_gap,
            "is_excess": True
        })
        total_unexplained_idle_mins += final_gap

    IDLE_OVERHEAD_RATE = 65000  # Rp / jam
    idle_overhead_cost_rp = round((total_unexplained_idle_mins / 60.0) * IDLE_OVERHEAD_RATE)

    turnaround_summary = {
        "events": turnaround_events,
        "run_hours": round(total_run_mins / 60.0, 1),
        "changeover_hours": round(total_changeover_mins / 60.0, 1),
        "idle_hours": round(total_unexplained_idle_mins / 60.0, 1),
        "idle_cost_rp": idle_overhead_cost_rp,
        "uptime_percent": round((total_run_mins / (24 * 60)) * 100, 1)
    }

    # 5. Prescriptive Maintenance Ticket Generator
    tickets = []
    
    # Check Heat Exchanger Degradation
    mech_delay_batches = [h for h in historical_scatter if h['is_today'] and h['quadrant'] == 'MECHANICAL_DEGRADATION']
    if mech_delay_batches:
        b_names = ", ".join([f"B#{b['batch_number']}" for b in mech_delay_batches])
        tickets.append({
            "priority": "HIGH",
            "component": "PENUKAR PANAS (HEAT EXCHANGER)",
            "title": f"Laju Perpindahan Panas Menurun pada {b_names}",
            "description": f"Pemanasan molor >15 menit meskipun tekanan uap boiler normal (>=4.0 bar). Indikasi kuat kerak penukar panas atau steam trap tersumbat.",
            "action": "Jadwalkan chemical descaling pada tube bundle heat exchanger dan bersihkan saringan steam trap."
        })

    # Check Cooling Blockage
    cooling_delayed_batches = [h for h in historical_scatter if h['is_today'] and (h['delta_cool'] or 0) > 15]
    if cooling_delayed_batches:
        b_names = ", ".join([f"B#{b['batch_number']}" for b in cooling_delayed_batches])
        tickets.append({
            "priority": "HIGH",
            "component": "SIRKULASI AIR PENDINGIN (COOLING TOWER & VALVE)",
            "title": f"Fase Pendinginan Lambat pada {b_names}",
            "description": f"Durasi cooling molor >15 menit di atas standar program ideal. Pasokan air pendingin terhambat atau katup buang cooling tower tidak terbuka penuh.",
            "action": "Periksa strainer katup air pendingin dan cek debit pompa sirkulasi cooling tower."
        })

    # Check Boiler Pressure Starvation
    boiler_delayed_batches = [h for h in historical_scatter if h['is_today'] and h['quadrant'] == 'BOILER_DROP']
    if boiler_delayed_batches:
        b_names = ", ".join([f"B#{b['batch_number']}" for b in boiler_delayed_batches])
        tickets.append({
            "priority": "MEDIUM",
            "component": "PASOKAN UAP PUSAT (BOILER)",
            "title": f"Keterlambatan Pemanasan Akibat Suplai Boiler Drop pada {b_names}",
            "description": f"Mesin mengalami delay pemanasan saat tekanan uap turun di bawah 3.8 bar. Ini murni kendala pasokan uap pabrik, bukan kerusakan mesin ini.",
            "action": "Koordinasikan dengan bagian boiler untuk menjaga kestabilan tekanan steam minimal 4.0 bar saat jam sibuk."
        })

    # Check Long Turnaround
    if turnaround_summary['idle_hours'] > 4.0:
        tickets.append({
            "priority": "MEDIUM",
            "component": "OPERASIONAL & PERSIAPAN KAIN (PPIC/OPERATOR)",
            "title": f"Waktu Menganggur Mesin Terlalu Tinggi ({turnaround_summary['idle_hours']} Jam)",
            "description": f"Mesin menganggur tanpa kain selama {turnaround_summary['idle_hours']} jam, menimbulkan potensi kerugian overhead sebesar Rp {turnaround_summary['idle_cost_rp']:,}.",
            "action": "Evaluasi antrian kain greige/persiapan celup agar transisi antar-batch bisa ditekan di bawah 30 menit."
        })

    # Fetch summary for this machine
    daily_summary = _compute_daily_summary_data(date)
    machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)

    return {
        "summary": machine_stats,
        "machine_name": machine.name,
        "machine_code": machine.code,
        "machine_group": machine.group.name if machine.group else "-",
        "date_range": f"{start_time.strftime('%d %b %H:%M')} - {end_time.strftime('%d %b %H:%M')}",
        "chart_data": chart_data,
        "batches": batches_data,
        "historical_scatter": historical_scatter,
        "program_benchmarks": program_benchmarks,
        "turnaround_summary": turnaround_summary,
        "maintenance_tickets": tickets,
    }

@report_router.get("/process/{process_id}/analytics")
def get_process_analytics(request, process_id: str, machine: str = None, batch: str = None):
    from monitoring.models import (
        GlobalSettings, MachineStatusSnapshot, DataAnomaly, AnomalyThresholdMaster
    )
    from monitoring.utils.steam_active import is_steam_active_from_snapshot
    from monitoring.utils.cooling_active import is_cooling_active_from_snapshot
    from django.core.cache import cache
    from django.db.models import Q

    process = None
    if process_id and str(process_id).isdigit():
        pid = int(process_id)
        process = DyeingProcess.objects.select_related('machine', 'machine__group', 'identity', 'identity__program').filter(id=pid).first()
        if not process:
            from monitoring.models import DyeingIdentity
            ident = DyeingIdentity.objects.filter(id=pid).select_related('dyeing_process', 'dyeing_process__machine', 'dyeing_process__machine__group', 'dyeing_process__identity__program').first()
            if ident and ident.dyeing_process:
                process = ident.dyeing_process

    # Fallback 1: Cek query params machine & batch
    lookup_machine = machine or request.GET.get('machine')
    lookup_batch = batch or request.GET.get('batch')

    # Fallback 2: Cek cache metadata batch jika batch baru saja di-reprocess
    if not process and process_id and str(process_id).isdigit():
        try:
            cached_meta = cache.get(f"dyeing_process_meta_{process_id}")
            if cached_meta:
                lookup_machine = lookup_machine or cached_meta.get("machine")
                lookup_batch = lookup_batch or cached_meta.get("batch")
        except Exception:
            pass

    # Resolusi cerdas ke batch terbaru jika process_id berubah karena reprocessing
    if not process and (lookup_machine or lookup_batch):
        qs = DyeingProcess.objects.select_related('machine', 'machine__group', 'identity', 'identity__program')
        if lookup_machine:
            qs = qs.filter(Q(machine__code__iexact=lookup_machine) | Q(machine__name__iexact=lookup_machine))
        if lookup_batch:
            try:
                b_num = int(lookup_batch)
                qs = qs.filter(Q(batch_number=b_num) | Q(identity__batch__iexact=str(lookup_batch)))
            except ValueError:
                qs = qs.filter(identity__batch__iexact=str(lookup_batch))
        process = qs.order_by('-start_time', '-id').first()

    if not process:
        raise HttpError(404, f"Data laporan audit untuk Proses #{process_id} tidak ditemukan di sistem database.")

    # Simpan mapping ID ke cache agar link ini tetap valid selama 3 hari ke depan meskipun di-reprocess
    try:
        cache.set(f"dyeing_process_meta_{process.id}", {
            "machine": process.machine.code,
            "batch": process.batch_number,
        }, timeout=259200)
    except Exception:
        pass
    identity = getattr(process, 'identity', None)
    program = identity.program if identity else None
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)

    # 1. Basic KPI & Timing
    loss_time = None
    efficiency = None
    grade = "-"

    if program and program.durasi_ideal and process.duration_effective:
        loss_time = round(process.duration_effective - program.durasi_ideal, 1)
        efficiency = round((program.durasi_ideal / process.duration_effective) * 100, 1)
        if efficiency >= 80:
            grade = 'A'
        elif efficiency >= 60:
            grade = 'B'
        else:
            grade = 'C'

    heat_dur = process.real_heating_duration or process.heating_duration or 0
    hold_dur = process.steady_duration or 0
    cool_dur = process.cooling_duration or 0
    total_dur = heat_dur + hold_dur + cool_dur

    phase_pct = {}
    if total_dur > 0:
        phase_pct['heat'] = round(heat_dur / total_dur * 100, 1)
        phase_pct['cooling'] = round(cool_dur / total_dur * 100, 1)
        if hold_dur > 0:
            phase_pct['hold'] = round(hold_dur / total_dur * 100, 1)

    # 2. Time-series Chart Data + Plant Steam Demand + Boiler Coal Speed
    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()

    logs = list(
        MachineMinuteLog.objects.filter(
            machine=process.machine, timestamp__range=(start_dt, end_dt)
        ).order_by('timestamp').values_list('timestamp', 'temperature', 'thermal_state', 'gradient')
    )

    target_points = 90
    if len(logs) > target_points:
        step = max(1, len(logs) // target_points)
        downsampled = logs[::step]
        if logs[-1] != downsampled[-1]:
            downsampled.append(logs[-1])
    else:
        downsampled = logs

    # Steam_Pr & Speed_RB_Steam logs
    boiler_logs = MachineMinuteLog.objects.filter(
        machine__code__in=['Steam_Pr', 'Speed_RB_Steam'],
        timestamp__range=(start_dt - timedelta(minutes=2), end_dt + timedelta(minutes=2))
    ).values_list('machine__code', 'timestamp', 'temperature')

    steam_dict = {}
    coal_dict = {}
    for m_code, ts, val in boiler_logs:
        t_min = ts.replace(second=0, microsecond=0)
        if m_code == 'Steam_Pr':
            steam_dict[t_min] = val
        elif m_code == 'Speed_RB_Steam':
            coal_dict[t_min] = val

    # Plant-wide steam demand from MachineStatusSnapshot during batch window
    all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0)
    steam_machine_map = {m.code: m.average_steam_usage for m in all_steam_machines}

    snapshots = list(
        MachineStatusSnapshot.objects.filter(
            timestamp__range=(start_dt - timedelta(minutes=12), end_dt + timedelta(minutes=12))
        ).order_by('timestamp').values('timestamp', 'snapshot_data')
    )

    snap_series = []
    cool_snap_series = []
    for snap in snapshots:
        s_total = 0.0
        s_count = 0
        cool_count = 0
        cool_machines = []
        s_data = snap['snapshot_data'] or {}
        for m_code, m_state in s_data.items():
            avg_u = steam_machine_map.get(m_code)
            if avg_u and is_steam_active_from_snapshot(m_state):
                s_total += avg_u
                s_count += 1
            if is_cooling_active_from_snapshot(m_state, m_code):
                cool_count += 1
                cool_machines.append(m_code)
        snap_series.append((snap['timestamp'], round(s_total, 1), s_count))
        cool_snap_series.append((snap['timestamp'], cool_count, cool_machines))

    def _nearest_snapshot(ts):
        if not snap_series:
            return 0.0, 0
        best = min(snap_series, key=lambda x: abs((x[0] - ts).total_seconds()))
        if abs((best[0] - ts).total_seconds()) <= 900:
            return best[1], best[2]
        return 0.0, 0

    def _nearest_cooling_snapshot(ts):
        if not cool_snap_series:
            return 0, []
        best = min(cool_snap_series, key=lambda x: abs((x[0] - ts).total_seconds()))
        if abs((best[0] - ts).total_seconds()) <= 900:
            return best[1], best[2]
        return 0, []

    fuel_factor = getattr(settings, 'fuel_factor_steam_boiler', 0.0) or 0.0
    chart_data = []
    pressures_all = []
    demands_all = []
    coal_hz_all = []
    low_pr_points = []
    normal_pr_points = []

    for ts, temp, t_state, grad in downsampled:
        t_key = ts.replace(second=0, microsecond=0)
        steam_val = steam_dict.get(t_key)
        if steam_val is None:
            steam_val = steam_dict.get(t_key - timedelta(minutes=1)) or steam_dict.get(t_key + timedelta(minutes=1)) or 0
        coal_hz = coal_dict.get(t_key)
        if coal_hz is None:
            coal_hz = coal_dict.get(t_key - timedelta(minutes=1)) or coal_dict.get(t_key + timedelta(minutes=1))

        plant_demand, active_cnt = _nearest_snapshot(ts)
        cool_cnt, cool_list = _nearest_cooling_snapshot(ts)
        coal_kg_h = round(coal_hz * fuel_factor, 1) if (coal_hz is not None and fuel_factor > 0) else None
        time_str = timezone.localtime(ts).strftime('%H:%M')
        grad_val = grad if grad is not None else 0.0

        pt = {
            "time": time_str,
            "temp": round(temp, 1) if temp is not None else None,
            "pressure": round(steam_val, 2) if steam_val is not None else 0,
            "thermal_state": t_state or "-",
            "gradient": round(grad_val, 2),
            "cooling_rate": round(max(0.0, -grad_val), 2),
            "plant_steam_kg_h": plant_demand,
            "active_steam_machines": active_cnt,
            "active_cooling_machines": cool_cnt,
            "cooling_machines": ", ".join(cool_list) if cool_list else "-",
            "coal_speed_hz": round(coal_hz, 2) if coal_hz is not None else None,
            "coal_feed_kg_h": coal_kg_h,
        }
        chart_data.append(pt)

        if steam_val and steam_val > 0:
            pressures_all.append((steam_val, time_str))
            if steam_val < threshold:
                low_pr_points.append(pt)
            else:
                normal_pr_points.append(pt)
        if plant_demand > 0:
            demands_all.append((plant_demand, active_cnt, time_str))
        if coal_hz is not None:
            coal_hz_all.append(coal_hz)

    avg_steam = process.avg_steam_pressure
    if avg_steam is None and pressures_all:
        avg_steam = sum(p[0] for p in pressures_all) / len(pressures_all)

    # 3. Plant & Boiler Context Diagnosis (Penyebab Turunnya Pressure)
    min_pr_val, min_pr_time = (min(pressures_all, key=lambda x: x[0]) if pressures_all else (None, "-"))
    peak_demand_val, peak_active_cnt, peak_demand_time = (
        max(demands_all, key=lambda x: x[0]) if demands_all else (0.0, 0, "-")
    )
    avg_demand_val = round(sum(x[0] for x in demands_all) / len(demands_all), 1) if demands_all else 0.0
    avg_active_cnt = round(sum(x[1] for x in demands_all) / len(demands_all), 1) if demands_all else 0.0
    avg_coal_hz = round(sum(coal_hz_all) / len(coal_hz_all), 2) if coal_hz_all else None
    low_pr_pct = round((len(low_pr_points) / len(pressures_all)) * 100, 1) if pressures_all else 0.0
    steam_healthy_pct = round(100.0 - low_pr_pct, 1) if pressures_all else None

    demand_low_pr = (
        round(sum(x["plant_steam_kg_h"] for x in low_pr_points) / len(low_pr_points), 1)
        if low_pr_points else None
    )
    demand_norm_pr = (
        round(sum(x["plant_steam_kg_h"] for x in normal_pr_points) / len(normal_pr_points), 1)
        if normal_pr_points else None
    )
    coal_low_pr_vals = [x["coal_speed_hz"] for x in low_pr_points if x["coal_speed_hz"] is not None]
    coal_norm_pr_vals = [x["coal_speed_hz"] for x in normal_pr_points if x["coal_speed_hz"] is not None]
    coal_low_pr = round(sum(coal_low_pr_vals) / len(coal_low_pr_vals), 2) if coal_low_pr_vals else None
    coal_norm_pr = round(sum(coal_norm_pr_vals) / len(coal_norm_pr_vals), 2) if coal_norm_pr_vals else None

    if low_pr_pct > 15:
        is_peak_load_cause = (
            (demand_low_pr and demand_norm_pr and demand_low_pr > demand_norm_pr * 1.08)
            or (peak_active_cnt >= 7)
        )
        is_coal_lag_cause = (
            coal_low_pr is not None and (
                coal_low_pr <= 1.0 or (coal_norm_pr and coal_low_pr < coal_norm_pr * 0.9)
            )
        )
        if is_peak_load_cause and is_coal_lag_cause:
            pr_cause_title = "Kombinasi Beban Puncak Pabrik & Respons Stoker Boiler Terlambat"
            pr_cause_tone = "red"
            pr_cause_detail = (
                f"Tekanan uap turun di bawah {threshold} bar selama {low_pr_pct}% waktu proses (titik terendah {round(min_pr_val, 2)} bar pukul {min_pr_time}). "
                f"Saat pressure drop, beban tarikan uap pabrik mencapai {demand_low_pr or peak_demand_val} kg/jam (puncak {peak_active_cnt} mesin aktif bersamaan), "
                f"sementara speed batu bara boiler turun/rendah di {coal_low_pr} Hz."
            )
            pr_cause_action = (
                "1) Terapkan staggering jadwal Heating agar tidak >6 mesin besar naik suhu serentak; "
                "2) Evaluasi respons modulasi stoker batu bara boiler agar tidak terlambat menaikkan Hz saat beban naik."
            )
        elif is_peak_load_cause:
            pr_cause_title = "Tarikan Beban Puncak Pabrik (Concurrent Heating Demand)"
            pr_cause_tone = "amber"
            pr_cause_detail = (
                f"Tekanan uap drop hingga {round(min_pr_val, 2)} bar pukul {min_pr_time} ({low_pr_pct}% durasi di bawah {threshold} bar). "
                f"Boiler sudah memacu speed batu bara ({coal_low_pr or avg_coal_hz or '-'} Hz), namun beban pemakaian uap pabrik melonjak ke "
                f"{demand_low_pr or peak_demand_val} kg/jam ({peak_active_cnt} mesin aktif bersamaan pukul {peak_demand_time})."
            )
            pr_cause_action = (
                "Bukan kesalahan internal mesin ini. Atur penjadwalan jam mulai Heating (staggering 15–20 menit antar-mesin Jet) "
                "untuk meratakan kurva beban uap pabrik."
            )
        elif is_coal_lag_cause:
            pr_cause_title = "Penurunan Speed Umpan Batu Bara / Regulasi Boiler"
            pr_cause_tone = "red"
            pr_cause_detail = (
                f"Beban uap pabrik relatif normal (rata-rata {avg_demand_val} kg/jam), namun tekanan drop ke {round(min_pr_val, 2)} bar pukul {min_pr_time} "
                f"karena speed feeder batu bara boiler rendah ({coal_low_pr} Hz vs normal {coal_norm_pr or avg_coal_hz} Hz)."
            )
            pr_cause_action = (
                "Koordinasikan dengan tim Boiler untuk menjaga kestabilan umpan batu bara (Speed_RB_Steam), "
                "cek kualitas/kalori batu bara, dan hindari jeda pengisian hopper."
            )
        else:
            pr_cause_title = "Fluktuasi Suplai Tekanan Header Uap"
            pr_cause_tone = "amber"
            pr_cause_detail = (
                f"Terdapat {low_pr_pct}% waktu proses dengan tekanan uap < {threshold} bar (minimum {round(min_pr_val, 2)} bar pukul {min_pr_time}) "
                f"pada beban rata-rata pabrik {avg_demand_val} kg/jam."
            )
            pr_cause_action = "Periksa kestabilan tekanan header utama dan jalur distribusi pipa menuju grup mesin ini."
    else:
        pr_cause_title = "Suplai Tekanan Uap Boiler Stabil & Sehat"
        pr_cause_tone = "emerald"
        pr_cause_detail = (
            f"Tekanan uap terjaga sehat selama {steam_healthy_pct or 100}% waktu proses (rata-rata {round(avg_steam, 2) if avg_steam else '-'} bar) "
            f"meski beban pabrik rata-rata {avg_demand_val} kg/jam (puncak {peak_active_cnt} mesin aktif)."
        )
        pr_cause_action = "Suplai uap dari boiler mendukung penuh performa pemanasan mesin pada batch ini."

    plant_boiler_context = {
        "threshold_bar": threshold,
        "avg_pressure_bar": round(avg_steam, 2) if avg_steam is not None else None,
        "min_pressure_bar": round(min_pr_val, 2) if min_pr_val is not None else None,
        "min_pressure_time": min_pr_time,
        "steam_healthy_pct": steam_healthy_pct,
        "low_pressure_pct": low_pr_pct,
        "avg_plant_demand_kg_h": avg_demand_val,
        "peak_plant_demand_kg_h": peak_demand_val,
        "peak_demand_time": peak_demand_time,
        "avg_active_machines": avg_active_cnt,
        "peak_active_machines": peak_active_cnt,
        "avg_coal_speed_hz": avg_coal_hz,
        "demand_during_low_pr_kg_h": demand_low_pr,
        "demand_during_normal_pr_kg_h": demand_norm_pr,
        "coal_hz_during_low_pr": coal_low_pr,
        "coal_hz_during_normal_pr": coal_norm_pr,
        "diagnosis": {
            "title": pr_cause_title,
            "tone": pr_cause_tone,
            "detail": pr_cause_detail,
            "action": pr_cause_action,
        },
    }

    # 3.B Cooling Context & Concurrent Cooling Diagnosis
    cool_dur = process.cooling_duration or 0.0
    cool_ideal_ref = program.durasi_cooling_ideal if program else None
    overrun_cool_mins = max(0.0, cool_dur - cool_ideal_ref) if cool_ideal_ref else max(0.0, cool_dur - 30.0)

    # Identifikasi titik mulai cooling untuk chart khusus cooling s/d end_time (sesuai request user)
    cool_start_dt = process.cooling_start_time
    if not cool_start_dt:
        if logs:
            peak_log = max(logs, key=lambda x: x[1] if x[1] is not None else 0)
            cool_start_dt = peak_log[0]
        else:
            cool_start_dt = start_dt

    cool_end_dt = process.end_time or end_dt

    # Ambil logs fase cooling s/d end_time
    cool_logs = [l for l in logs if l[0] >= cool_start_dt and l[0] <= cool_end_dt]
    if len(cool_logs) > 60:
        c_step = max(1, len(cool_logs) // 60)
        c_downsampled = cool_logs[::c_step]
        if cool_logs[-1] != c_downsampled[-1]:
            c_downsampled.append(cool_logs[-1])
    else:
        c_downsampled = cool_logs

    cooling_chart_data = []
    concurrent_counts_in_cooling = []
    concurrent_all_machines_set = set()
    peak_cool_machines = 0
    peak_cool_time = "-"

    for c_ts, c_temp, c_state, c_grad in c_downsampled:
        c_time_str = timezone.localtime(c_ts).strftime('%H:%M')
        c_cnt, c_list = _nearest_cooling_snapshot(c_ts)
        concurrent_counts_in_cooling.append(c_cnt)
        if c_cnt > peak_cool_machines:
            peak_cool_machines = c_cnt
            peak_cool_time = c_time_str
        for m in c_list:
            if m != process.machine.code:
                concurrent_all_machines_set.add(m)
        g_val = c_grad if c_grad is not None else 0.0
        cooling_chart_data.append({
            "time": c_time_str,
            "temp": round(c_temp, 1) if c_temp is not None else None,
            "gradient": round(g_val, 2),
            "cooling_rate": round(max(0.0, -g_val), 2),
            "active_cooling_machines": c_cnt,
            "cooling_machines": ", ".join(c_list) if c_list else "-",
        })

    avg_cool_cnt = round(sum(concurrent_counts_in_cooling) / len(concurrent_counts_in_cooling), 1) if concurrent_counts_in_cooling else 0.0
    avg_cool_grad = process.cooling_avg_gradient
    if (avg_cool_grad is None or avg_cool_grad == 0) and cooling_chart_data:
        rates = [pt['cooling_rate'] for pt in cooling_chart_data if pt['cooling_rate'] > 0]
        avg_cool_grad = round(sum(rates) / len(rates), 2) if rates else None
    else:
        avg_cool_grad = round(abs(avg_cool_grad), 2) if avg_cool_grad else None

    ideal_cool_grad = None
    if cool_ideal_ref and cool_ideal_ref > 0 and process.max_temp:
        ideal_cool_grad = round(max(0.0, (process.max_temp - 70.0) / cool_ideal_ref), 2)

    is_cool_delayed = (cool_ideal_ref and cool_dur > cool_ideal_ref * 1.2 and overrun_cool_mins >= 8) or (not cool_ideal_ref and cool_dur > 45)

    if not is_cool_delayed:
        cool_cause_title = "Performa Pendinginan Mesin Prima & Suplai Air Pendingin Cukup"
        cool_cause_tone = "emerald"
        cool_cause_detail = (
            f"Fase cooling berjalan efisien selama {round(cool_dur)} menit (laju rata-rata {avg_cool_grad or '-'} °C/menit) "
            f"hingga suhu akhir {round(process.end_temp or 0, 1)}°C. Proses tetap lancar meskipun terdapat {peak_cool_machines} mesin "
            f"lain yang juga cooling bersamaan di pabrik (rata-rata {avg_cool_cnt} mesin)."
        )
        cool_cause_action = "Performa penukar panas (Heat Exchanger) dan suplai air pendingin bekerja prima mendukung siklus waktu batch ini."
    else:
        peer_list_sample = list(concurrent_all_machines_set)[:5]
        peer_str = ", ".join(peer_list_sample) + ("..." if len(concurrent_all_machines_set) > 5 else "")
        if peak_cool_machines >= 4 or avg_cool_cnt >= 2.5:
            cool_cause_title = "Indikasi Perebutan Air Pendingin (Beban Puncak Mesin Cooling Bersamaan)"
            cool_cause_tone = "amber"
            cool_cause_detail = (
                f"Fase cooling berlangsung lambat selama {round(cool_dur)} menit (lebih lama +{round(overrun_cool_mins)} menit dari target "
                f"{round(cool_ideal_ref or 30)} menit, laju rata-rata {avg_cool_grad or '-'} °C/menit). Selama fase ini, terpantau puncak "
                f"lonjakan beban di mana {peak_cool_machines} mesin melakukan cooling serentak pukul {peak_cool_time} "
                f"(rata-rata {avg_cool_cnt} mesin: {peer_str or '-'}). Lonjakan mesin serentak membagi suplai debit/tekanan cooling water pabrik, "
                f"menurunkan efisiensi perpindahan panas Heat Exchanger."
            )
            cool_cause_action = (
                "Bukan murni kerusakan mesin ini. Terapkan jeda bertahap (staggering 10–15 menit) pelepasan proses cooling antar-mesin Jet, "
                "atau evaluasi kestabilan tekanan pompa booster sirkulasi cooling tower saat jam sibuk pabrik."
            )
        else:
            cool_cause_title = "Terindikasi Kendala Internal Mesin: Penukar Panas (HE) / Katup Pendingin"
            cool_cause_tone = "red"
            cool_cause_detail = (
                f"Proses cooling molor mencapai {round(cool_dur)} menit (lebih lama +{round(overrun_cool_mins)} menit dari target "
                f"{round(cool_ideal_ref or 30)} menit) dengan laju lambat ({avg_cool_grad or '-'} °C/menit), padahal beban pabrik tergolong "
                f"sepi (hanya puncak {peak_cool_machines} mesin, rata-rata {avg_cool_cnt} mesin cooling). Suplai air pendingin pabrik longgar, "
                f"namun serapan pendinginan internal mesin tetap rendah."
            )
            cool_cause_action = (
                "Lakukan pengecekan pemeliharaan (PM) pada mesin ini: 1) Cek bukaan pneumatic cooling valve & aktuator; "
                "2) Bersihkan filter strainer inlet air pendingin; 3) Jadwalkan descaling / flushing pipa Heat Exchanger dari kerak kapur/kotoran."
            )

    cooling_context = {
        "cooling_start_time": timezone.localtime(cool_start_dt).strftime('%H:%M') if cool_start_dt else "-",
        "reached_70c_time": timezone.localtime(process.reached_70c_time).strftime('%H:%M') if process.reached_70c_time else "-",
        "end_time": timezone.localtime(cool_end_dt).strftime('%H:%M') if cool_end_dt else "-",
        "cooling_duration_mins": round(cool_dur, 1),
        "cooling_ideal_mins": round(cool_ideal_ref, 1) if cool_ideal_ref else None,
        "overrun_mins": round(overrun_cool_mins, 1),
        "avg_cooling_gradient": avg_cool_grad,
        "ideal_cooling_gradient": ideal_cool_grad,
        "peak_concurrent_machines": peak_cool_machines,
        "peak_concurrent_time": peak_cool_time,
        "avg_concurrent_machines": avg_cool_cnt,
        "concurrent_machines_list": list(concurrent_all_machines_set),
        "cooling_chart_data": cooling_chart_data,
        "diagnosis": {
            "title": cool_cause_title,
            "tone": cool_cause_tone,
            "detail": cool_cause_detail,
            "action": cool_cause_action,
        },
    }

    # 4. Energy & Financial Audit (Harga Listrik, Harga Steam, Losses & Potensi Keuntungan)
    steam_rate = getattr(settings, 'steam_cost_per_kg', 350.0) or 350.0
    lwbp_rate = getattr(settings, 'electricity_base_rate', 1035.8) or 1035.8
    wbp_mult = getattr(settings, 'wbp_multiplier', 1.4) or 1.4
    wbp_rate = round(lwbp_rate * wbp_mult, 2)
    nom_kw = process.machine_nominal_power or getattr(process.machine, 'nominal_power', 0) or 0

    # Deteksi Multi-Heating / Re-Heating (>= 2x naik suhu dalam 1 proses sebelum <70°C)
    from monitoring.utils.batch_analyzer import detect_multi_heating_cycles
    multi_heat = detect_multi_heating_cycles(
        logs,
        start_bound=process.heating_start_time or process.start_time,
        end_bound=process.reached_70c_time or end_dt,
    )
    is_multi_heating = multi_heat['is_multi_heating']
    reheat_extra_mins = multi_heat['reheat_extra_mins'] if is_multi_heating else 0.0

    l1_steam = process.predicted_steam_kg or 0.0
    l2_steam = process.predicted_steam_best_kg or l1_steam
    l3_steam = process.predicted_steam_ideal_kg or l2_steam

    # Jika terjadi Re-Heating (>= 2x siklus naik suhu), pisahkan porsi uap ekstra
    # dari siklus ke-2 dst agar tidak salah diatribusikan ke Faktor Suplai Boiler.
    reheat_steam_loss_kg = 0.0
    if is_multi_heating and l1_steam > l3_steam:
        try:
            from monitoring.models import MachinePhysicsProfile
            from monitoring.services.pinn_engine import PINNSteamPredictor
            prof = (
                MachinePhysicsProfile.objects.filter(machine=process.machine, is_active=True).first()
                or MachinePhysicsProfile.get_best_for_machine(process.machine)
            )
            if prof:
                l1_single_cycle = round(
                    PINNSteamPredictor().predict(
                        process, prof.to_physics_dict(), weights=None, force_ideal=False, single_cycle_only=True
                    ),
                    1,
                )
                reheat_steam_loss_kg = max(0.0, round(l1_steam - l1_single_cycle, 1))
        except Exception:
            pass
        if reheat_steam_loss_kg == 0.0 and multi_heat['cycles']:
            c1_m = multi_heat['cycles'][0]['total_mins']
            all_m = sum(c['total_mins'] for c in multi_heat['cycles'])
            if all_m > c1_m > 0:
                reheat_steam_loss_kg = round(l1_steam * ((all_m - c1_m) / all_m), 1)
        reheat_steam_loss_kg = min(reheat_steam_loss_kg, max(0.0, l1_steam - l3_steam))

    steam_loss_total_kg = max(0.0, l1_steam - l3_steam)
    steam_loss_machine_kg = max(0.0, l1_steam - l2_steam)
    steam_loss_supply_kg = max(0.0, min(l1_steam, l2_steam) - l3_steam - reheat_steam_loss_kg)
    reheat_steam_loss_rp = round(reheat_steam_loss_kg * steam_rate)

    steam_cost_actual_rp = round(l1_steam * steam_rate)
    steam_cost_ideal_rp = round(l3_steam * steam_rate)
    steam_loss_total_rp = round(steam_loss_total_kg * steam_rate)
    steam_loss_machine_rp = round(steam_loss_machine_kg * steam_rate)
    steam_loss_supply_rp = round(steam_loss_supply_kg * steam_rate)
    steam_eff_pct = round((l3_steam / l1_steam) * 100, 1) if l1_steam > 0 else None

    # Operator delay minutes & fabric handling allowance (<70C to OFF up to 45 mins)
    keep_ideal_m = (program.durasi_keeping_ideal or 0) if program else 0
    over_hold_mins = max(0.0, hold_dur - keep_ideal_m) if keep_ideal_m > 0 else 0.0
    late_stop_mins = 0.0
    if process.reached_70c_time and process.end_time and process.end_time > process.reached_70c_time:
        late_stop_mins = max(0.0, (process.end_time - process.reached_70c_time).total_seconds() / 60.0)
    pre_heat_idle_mins = 0.0
    if process.heating_start_time and process.start_time and process.heating_start_time > process.start_time:
        pre_heat_idle_mins = max(0.0, (process.heating_start_time - process.start_time).total_seconds() / 60.0)

    # Deteksi Anomali & Stagnasi Fase Cooling (suhu tertahan >= 70°C atau cooling molor drastis)
    # Catatan: jika is_multi_heating=True, rentang cooling_start_time -> reached_70c_time
    # berisi siklus Re-Heating ke-2 dst, sehingga tidak diklasifikasikan sebagai stagnasi cooling biasa.
    cool_ideal_m = (program.durasi_cooling_ideal or 0.0) if program else 0.0
    cool_overrun_mins = max(0.0, cool_dur - cool_ideal_m) if cool_ideal_m > 0 else 0.0
    cooling_stagnant_mins = 0.0
    stag_start_str = None
    stag_end_str = None
    stag_avg_temp = None

    if process.cooling_start_time and logs and not is_multi_heating:
        c_end_bound = process.reached_70c_time or end_dt
        cool_logs = [
            (ts, temp) for ts, temp, *rest in logs
            if ts >= process.cooling_start_time
            and ts <= c_end_bound
            and temp is not None
            and temp >= 70.0
        ]
        if len(cool_logs) >= 10:
            # Periksa jendela 5 menit (5 log @1 menit): jika suhu tidak turun (< 0.4°C per 5 menit),
            # berarti proses pendinginan tertahan/stagnan di tengah jalan sebelum mencapai 70°C.
            stag_indices = []
            win = 5
            for idx in range(win, len(cool_logs)):
                t_prev = cool_logs[idx - win][1]
                t_curr = cool_logs[idx][1]
                dt_m = max(1.0, (cool_logs[idx][0] - cool_logs[idx - win][0]).total_seconds() / 60.0)
                drop_rate = (t_prev - t_curr) / dt_m  # °C per menit
                if drop_rate < 0.08:  # < 0.4°C dalam 5 menit (stagnan / plateau)
                    stag_indices.append(idx)
            if stag_indices:
                cooling_stagnant_mins = float(len(stag_indices))
                first_idx = max(0, stag_indices[0] - win)
                last_idx = stag_indices[-1]
                stag_start_str = timezone.localtime(cool_logs[first_idx][0]).strftime('%H:%M')
                stag_end_str = timezone.localtime(cool_logs[last_idx][0]).strftime('%H:%M')
                stag_temps = [cool_logs[i][1] for i in stag_indices]
                stag_avg_temp = round(sum(stag_temps) / len(stag_temps), 1)

    # Durasi keluar-masuk kain (pasca-cooling <70°C s/d OFF) maksimal 45 menit
    # dimasukkan sebagai tambahan pada Durasi Ideal Listrik (bukan dihitung sebagai Loss Listrik)
    FABRIC_HANDLING_MAX_MINS = 45.0
    fabric_handling_allowance_mins = min(late_stop_mins, FABRIC_HANDLING_MAX_MINS)
    excess_late_stop_mins = max(0.0, late_stop_mins - FABRIC_HANDLING_MAX_MINS)

    recipe_ideal_mins = (program.durasi_ideal or 0.0) if program else (process.program_ideal_duration_mins or 0.0)
    elec_ideal_duration_mins = (recipe_ideal_mins + fabric_handling_allowance_mins) if recipe_ideal_mins > 0 else 0.0

    pwr_actual_kwh = process.power_consumption_kwh or 0.0
    if elec_ideal_duration_mins > 0 and nom_kw > 0:
        pwr_ideal_kwh = round((elec_ideal_duration_mins / 60.0) * nom_kw, 2)
    elif process.ideal_power_consumption_kwh:
        pwr_ideal_kwh = round(process.ideal_power_consumption_kwh + (fabric_handling_allowance_mins / 60.0) * nom_kw, 2)
    else:
        pwr_ideal_kwh = pwr_actual_kwh

    pwr_lwbp_kwh = process.power_consumption_lwbp_kwh or 0.0
    pwr_wbp_kwh = process.power_consumption_wbp_kwh or 0.0
    pwr_loss_kwh = max(0.0, pwr_actual_kwh - pwr_ideal_kwh)

    pwr_cost_lwbp_rp = round(process.power_cost_lwbp or (pwr_lwbp_kwh * lwbp_rate))
    pwr_cost_wbp_rp = round(process.power_cost_wbp or (pwr_wbp_kwh * wbp_rate))
    pwr_cost_actual_rp = round(process.power_cost_total or (pwr_cost_lwbp_rp + pwr_cost_wbp_rp))
    pwr_cost_ideal_rp = round(pwr_ideal_kwh * lwbp_rate)
    pwr_loss_overrun_rp = round(pwr_loss_kwh * lwbp_rate)
    pwr_loss_wbp_surcharge_rp = round(pwr_wbp_kwh * (wbp_rate - lwbp_rate))
    pwr_loss_total_rp = max(0, pwr_cost_actual_rp - pwr_cost_ideal_rp)
    pwr_eff_pct = round(min(100.0, (pwr_ideal_kwh / pwr_actual_kwh) * 100), 1) if pwr_actual_kwh > 0 else None

    out_yd = identity.output_yard if (identity and identity.output_yard) else None
    total_actual_rp = steam_cost_actual_rp + pwr_cost_actual_rp
    total_ideal_rp = steam_cost_ideal_rp + pwr_cost_ideal_rp
    total_loss_rp = steam_loss_total_rp + pwr_loss_total_rp

    cost_per_yd_actual = round(total_actual_rp / out_yd) if (out_yd and out_yd > 0) else None
    cost_per_yd_ideal = round(total_ideal_rp / out_yd) if (out_yd and out_yd > 0) else None
    loss_per_yd = round(total_loss_rp / out_yd) if (out_yd and out_yd > 0) else None

    cool_stag_waste_mins = cooling_stagnant_mins if cooling_stagnant_mins >= 15 else 0.0
    operator_waste_mins = over_hold_mins + excess_late_stop_mins + cool_stag_waste_mins + reheat_extra_mins
    operator_loss_kwh = (operator_waste_mins / 60.0) * nom_kw
    operator_loss_rp = min(pwr_loss_overrun_rp, round(operator_loss_kwh * lwbp_rate))
    remaining_overrun_rp = max(0, pwr_loss_overrun_rp - operator_loss_rp)

    if low_pr_pct > 15:
        supply_pwr_share_rp = round(remaining_overrun_rp * 0.65)
        machine_pwr_share_rp = remaining_overrun_rp - supply_pwr_share_rp
    else:
        supply_pwr_share_rp = 0
        machine_pwr_share_rp = remaining_overrun_rp

    bucket_supply_rp = steam_loss_supply_rp + supply_pwr_share_rp
    bucket_machine_rp = steam_loss_machine_rp + machine_pwr_share_rp
    bucket_operator_rp = operator_loss_rp + reheat_steam_loss_rp
    bucket_wbp_rp = pwr_loss_wbp_surcharge_rp
    bucket_sum = max(1, bucket_supply_rp + bucket_machine_rp + bucket_operator_rp + bucket_wbp_rp)

    op_parts = []
    if is_multi_heating:
        op_parts.append(
            f"re-heating / {multi_heat['cycle_count']}x naik suhu (+{round(reheat_extra_mins)}m waktu & +{round(reheat_steam_loss_kg, 1)} kg uap)"
        )
    if over_hold_mins > 0:
        op_parts.append(f"over-holding (+{round(over_hold_mins)}m)")
    if cool_stag_waste_mins > 0:
        op_parts.append(f"stagnasi fase cooling di ~{stag_avg_temp}°C (+{round(cool_stag_waste_mins)}m)")
    if excess_late_stop_mins > 0:
        op_parts.append(f"durasi pasca-cooling >45m (+{round(excess_late_stop_mins)}m)")

    if op_parts:
        op_desc = f"Kerugian akibat {' & '.join(op_parts)}."
    else:
        op_desc = "Tidak ada keterlambatan operasional (holding & cooling sesuai target, waktu keluar-masuk kain ≤45 menit)."

    loss_attribution = [
        {
            "key": "steam_supply",
            "label": "Faktor Suplai Uap / Tekanan Boiler",
            "amount_rp": bucket_supply_rp,
            "share_pct": round((bucket_supply_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
            "desc": "Kerugian akibat tekanan uap drop / fraksi uap basah (Lapis 2 vs Lapis 3) & waktu tunggu pemanasan.",
        },
        {
            "key": "machine_condition",
            "label": "Faktor Fisik & Komponen Mesin",
            "amount_rp": bucket_machine_rp,
            "share_pct": round((bucket_machine_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
            "desc": "Kerugian akibat performa termal mesin (steam trap/insulasi/HE Lapis 1 vs Lapis 2) & laju cooling.",
        },
        {
            "key": "operator_delay",
            "label": "Faktor Operasional & Keterlambatan Operator",
            "amount_rp": bucket_operator_rp,
            "share_pct": round((bucket_operator_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
            "desc": op_desc,
        },
        {
            "key": "wbp_tariff",
            "label": "Faktor Penjadwalan Jam Puncak (Tarif WBP)",
            "amount_rp": bucket_wbp_rp,
            "share_pct": round((bucket_wbp_rp / bucket_sum) * 100, 1) if total_loss_rp > 0 else 0,
            "desc": f"Selisih tarif mahal WBP (17:00–22:00) sebesar {round(pwr_wbp_kwh, 1)} kWh × Rp {round(wbp_rate - lwbp_rate)}/kWh.",
        },
    ]
    loss_attribution.sort(key=lambda x: x["amount_rp"], reverse=True)

    # Monthly batch frequency on this machine (last 30 days before/around batch)
    ref_end = process.start_time + timedelta(days=1)
    ref_start_30d = ref_end - timedelta(days=30)
    recent_30d_count = DyeingProcess.objects.filter(
        machine=process.machine,
        is_valid_process=True,
        start_time__gte=ref_start_30d,
        start_time__lte=ref_end,
    ).count()
    monthly_freq = max(recent_30d_count, 45)

    energy_financials = {
        "tariffs": {
            "steam_rp_per_kg": steam_rate,
            "lwbp_rp_per_kwh": round(lwbp_rate, 1),
            "wbp_rp_per_kwh": wbp_rate,
            "wbp_window": "17:00 - 22:00",
            "nominal_power_kw": nom_kw,
        },
        "steam": {
            "actual_kg": round(l1_steam, 1),
            "best_machine_kg": round(l2_steam, 1),
            "ideal_kg": round(l3_steam, 1),
            "loss_total_kg": round(steam_loss_total_kg, 1),
            "loss_machine_cond_kg": round(steam_loss_machine_kg, 1),
            "loss_supply_press_kg": round(steam_loss_supply_kg, 1),
            "cost_actual_rp": steam_cost_actual_rp,
            "cost_ideal_rp": steam_cost_ideal_rp,
            "loss_total_rp": steam_loss_total_rp,
            "loss_machine_cond_rp": steam_loss_machine_rp,
            "loss_supply_press_rp": steam_loss_supply_rp,
            "eff_pct": steam_eff_pct,
        },
        "power": {
            "actual_kwh": round(pwr_actual_kwh, 2),
            "ideal_kwh": round(pwr_ideal_kwh, 2),
            "recipe_ideal_mins": round(recipe_ideal_mins, 1),
            "fabric_allowance_mins": round(fabric_handling_allowance_mins, 1),
            "elec_ideal_duration_mins": round(elec_ideal_duration_mins, 1),
            "lwbp_kwh": round(pwr_lwbp_kwh, 2),
            "wbp_kwh": round(pwr_wbp_kwh, 2),
            "loss_kwh": round(pwr_loss_kwh, 2),
            "cost_lwbp_rp": pwr_cost_lwbp_rp,
            "cost_wbp_rp": pwr_cost_wbp_rp,
            "cost_actual_rp": pwr_cost_actual_rp,
            "cost_ideal_rp": pwr_cost_ideal_rp,
            "loss_total_rp": pwr_loss_total_rp,
            "loss_overrun_rp": pwr_loss_overrun_rp,
            "loss_wbp_surcharge_rp": pwr_loss_wbp_surcharge_rp,
            "eff_pct": pwr_eff_pct,
        },
        "totals": {
            "output_yard": round(out_yd, 1) if out_yd else None,
            "total_actual_rp": total_actual_rp,
            "total_ideal_rp": total_ideal_rp,
            "total_loss_rp": total_loss_rp,
            "cost_per_yard_actual_rp": cost_per_yd_actual,
            "cost_per_yard_ideal_rp": cost_per_yd_ideal,
            "loss_per_yard_rp": loss_per_yd,
            "monthly_batch_freq": monthly_freq,
            "projected_monthly_saving_rp": round(total_loss_rp * monthly_freq),
            "projected_annual_saving_rp": round(total_loss_rp * monthly_freq * 12),
        },
        "loss_attribution": loss_attribution,
    }

    # 5. Historical Program Benchmark (Apakah Mesin Normal atau Tidak? — Khusus Mesin Ini & Program yang Sama)
    program_benchmark = None
    if program:
        same_machine_qs = list(
            DyeingProcess.objects.filter(
                machine=process.machine,
                identity__program=program,
                is_complete=True,
                is_valid_process=True,
                duration_effective__gt=0,
            )
            .select_related('machine', 'identity')
            .order_by('-start_time')[:40]
        )
        if process not in same_machine_qs:
            same_machine_qs.insert(0, process)

        same_m_list = [b for b in same_machine_qs if b.id != process.id][:20]
        ref_pool = same_m_list if same_m_list else [process]
        peer_qs = same_machine_qs

        def _stat_avg(items, getter):
            vals = [getter(x) for x in items if getter(x) is not None and getter(x) > 0]
            return round(sum(vals) / len(vals), 1) if vals else None

        avg_heat_hist = _stat_avg(ref_pool, lambda b: b.real_heating_duration or b.heating_duration)
        avg_hold_hist = _stat_avg(ref_pool, lambda b: b.steady_duration)
        avg_cool_hist = _stat_avg(ref_pool, lambda b: b.cooling_duration)
        avg_tot_hist = _stat_avg(ref_pool, lambda b: b.duration_effective)
        avg_pr_hist = _stat_avg(ref_pool, lambda b: b.avg_steam_pressure)
        avg_steam_hist = _stat_avg(ref_pool, lambda b: b.predicted_steam_kg)

        # Chart series: maksimal 20 batch dari MESIN YANG SAMA & PROGRAM YANG SAMA diurutkan kronologis
        chart_pool = same_m_list[:19] + [process]
        chart_pool = sorted({b.id: b for b in chart_pool}.values(), key=lambda x: x.start_time)

        history_series = []
        for b in chart_pool:
            b_heat = round(b.real_heating_duration or b.heating_duration or 0, 1)
            b_hold = round(b.steady_duration or 0, 1)
            b_cool = round(b.cooling_duration or 0, 1)
            b_pr = round(b.avg_steam_pressure, 2) if b.avg_steam_pressure is not None else None
            history_series.append({
                "id": b.id,
                "label": f"#{b.batch_number}" if b.machine_id == process.machine_id else f"{b.machine.name} #{b.batch_number}",
                "machine_name": b.machine.name,
                "date": timezone.localtime(b.start_time).strftime('%d/%m'),
                "heat_mins": b_heat,
                "hold_mins": b_hold,
                "cool_mins": b_cool,
                "total_mins": round(b.duration_effective or (b_heat + b_hold + b_cool), 1),
                "avg_pressure": b_pr,
                "steam_kg": round(b.predicted_steam_kg or 0, 1),
                "is_current": b.id == process.id,
                "is_same_machine": b.machine_id == process.machine_id,
            })

        # Machine Health Evaluation (Normal vs Tidak Normal)
        heat_ideal_ref = program.durasi_heating_ideal or avg_heat_hist or 0
        cool_ideal_ref = program.durasi_cooling_ideal or avg_cool_hist or 0

        heat_diff_vs_hist = (heat_dur - avg_heat_hist) if (avg_heat_hist and heat_dur) else 0
        cool_diff_vs_hist = (cool_dur - avg_cool_hist) if (avg_cool_hist and cool_dur) else 0

        # Heating verdict
        if heat_dur and heat_ideal_ref and heat_dur > heat_ideal_ref * 1.2:
            if avg_steam and avg_steam < threshold:
                heat_status = "TERHAMBAT SUPLAI UAP"
                heat_tone = "amber"
                heat_eval = (
                    f"Durasi Heating ({round(heat_dur)} mnt) lebih lambat dari histori ({avg_heat_hist or '-'} mnt) & resep ({round(heat_ideal_ref)} mnt), "
                    f"namun disebabkan oleh tekanan uap rata-rata yang rendah ({round(avg_steam, 2)} bar < {threshold} bar). "
                    f"Secara mekanis sistem pemanas mesin masih merespons sesuai tekanan yang tersedia."
                )
            else:
                heat_status = "TIDAK NORMAL (LAMBAT PADA TEKANAN CUKUP)"
                heat_tone = "red"
                heat_eval = (
                    f"PERHATIAN: Tekanan uap rata-rata sudah memadai ({round(avg_steam, 2) if avg_steam else '-'} bar), namun durasi Heating mencapai "
                    f"{round(heat_dur)} mnt (histori rata-rata: {avg_heat_hist or '-'} mnt, ideal: {round(heat_ideal_ref)} mnt). "
                    f"Indikasi kuat kendala internal mesin: bukaan control valve uap tidak 100%, strainer uap mampet, atau steam trap tertahan."
                )
        else:
            heat_status = "NORMAL"
            heat_tone = "emerald"
            heat_eval = (
                f"Performa pemanasan mesin NORMAL ({round(heat_dur)} mnt vs rata-rata histori {avg_heat_hist or '-'} mnt "
                f"pada tekanan {round(avg_steam, 2) if avg_steam else '-'} bar, gradien +{round(process.heating_avg_gradient or 0, 2)} °C/mnt)."
            )

        # Cooling verdict
        if is_multi_heating:
            v0 = multi_heat['valleys'][0]
            c_last = multi_heat['cycles'][-1]
            final_cm = multi_heat['final_cooling_mins']
            cool_status = f"TERINTERUPSI RE-HEATING ({multi_heat['cycle_count']}x NAIK SUHU)"
            cool_tone = "red"
            cool_eval = (
                f"Rentang pasca-cooling pertama mencapai {round(cool_dur)} mnt karena pada pukul {v0['cool_start_str']}–{v0['valley_str']} "
                f"suhu turun parsial ke {v0['valley_temp']}°C lalu dipanaskan ulang (Re-Heating) ke {c_last['peak_temp']}°C hingga {c_last['hold_end_str']} "
                f"(+{round(reheat_extra_mins)} mnt siklus tambahan). "
                f"Pendinginan akhir sebenarnya hanya memakan {round(final_cm)} mnt (histori: {avg_cool_hist or '-'} mnt) — Heat Exchanger mesin normal."
            )
        elif cool_dur and cool_ideal_ref and cool_dur > max(cool_ideal_ref * 1.25, (avg_cool_hist or cool_ideal_ref) + 8):
            if cooling_stagnant_mins >= 15:
                cool_status = "TIDAK NORMAL (STAGNASI / JEDA COOLING)"
                cool_tone = "red"
                cool_eval = (
                    f"Durasi Cooling ({round(cool_dur)} mnt vs ideal {round(cool_ideal_ref)} mnt) molor ekstrem karena suhu tertahan/stagnan "
                    f"di ~{stag_avg_temp}°C selama {round(cooling_stagnant_mins)} mnt ({stag_start_str}–{stag_end_str}) sebelum turun ke <70°C. "
                    f"Indikasi proses pendinginan/pembuangan air panas terhenti atau katup cooling tidak dibuka penuh oleh operator."
                )
            else:
                cool_status = "TIDAK NORMAL (COOLING LAMBAT)"
                cool_tone = "red"
                cool_eval = (
                    f"Durasi Cooling ({round(cool_dur)} mnt) lebih lambat +{round(cool_dur - (avg_cool_hist or cool_ideal_ref))} mnt dibanding histori program yang sama "
                    f"({avg_cool_hist or '-'} mnt) dan target ideal ({round(cool_ideal_ref)} mnt). "
                    f"Indikasi Heat Exchanger (HE) mulai berkerak (scaling), katup air pendingin kurang membuka, atau suhu cooling water naik."
                )
        else:
            cool_status = "NORMAL"
            cool_tone = "emerald"
            cool_eval = (
                f"Performa pendinginan mesin NORMAL ({round(cool_dur)} mnt vs histori {avg_cool_hist or '-'} mnt, "
                f"gradien {round(process.cooling_avg_gradient or 0, 2)} °C/mnt)."
            )

        overall_normal = (heat_tone == "emerald" and cool_tone == "emerald")
        program_benchmark = {
            "program_name": program.nama,
            "sample_count_same_machine": len(same_m_list),
            "sample_count_total": len(peer_qs),
            "overall_machine_status": "KONDISI MESIN NORMAL" if overall_normal else (
                "MESIN NORMAL (TERKENDALA SUPLAI UAP)" if (heat_tone == "amber" and cool_tone == "emerald")
                else "TERDETEKSI GEJALA TIDAK NORMAL PADA MESIN"
            ),
            "overall_tone": "emerald" if overall_normal else ("amber" if (heat_tone == "amber" and cool_tone == "emerald") else "red"),
            "comparison": {
                "current": {
                    "heat_mins": round(heat_dur, 1),
                    "hold_mins": round(hold_dur, 1),
                    "cool_mins": round(cool_dur, 1),
                    "total_mins": round(process.duration_effective or total_dur, 1),
                    "avg_pressure": round(avg_steam, 2) if avg_steam else None,
                    "steam_kg": round(l1_steam, 1),
                },
                "historical_avg": {
                    "heat_mins": avg_heat_hist,
                    "hold_mins": avg_hold_hist,
                    "cool_mins": avg_cool_hist,
                    "total_mins": avg_tot_hist,
                    "avg_pressure": avg_pr_hist,
                    "steam_kg": avg_steam_hist,
                },
                "recipe_ideal": {
                    "heat_mins": round(program.durasi_heating_ideal, 1) if program.durasi_heating_ideal else None,
                    "hold_mins": round(program.durasi_keeping_ideal, 1) if program.durasi_keeping_ideal else None,
                    "cool_mins": round(program.durasi_cooling_ideal, 1) if program.durasi_cooling_ideal else None,
                    "total_mins": round(program.durasi_ideal, 1) if program.durasi_ideal else None,
                    "avg_pressure": threshold,
                    "steam_kg": round(l3_steam, 1),
                },
            },
            "heating_diagnosis": {
                "status": heat_status,
                "tone": heat_tone,
                "detail": heat_eval,
                "diff_vs_hist_mins": round(heat_diff_vs_hist, 1),
            },
            "cooling_diagnosis": {
                "status": cool_status,
                "tone": cool_tone,
                "detail": cool_eval,
                "diff_vs_hist_mins": round(cool_diff_vs_hist, 1),
            },
            "history_series": history_series,
        }

    # 6. Operator & Process Anomaly Forensics
    forensic_findings = []

    # Finding 0: Multiple Heating Cycles / Re-Heating (>= 2x naik suhu dalam 1 proses sebelum <70°C)
    if is_multi_heating:
        cyc_parts = []
        for c in multi_heat['cycles']:
            cyc_parts.append(
                f"Siklus #{c['cycle_no']}: naik {c['start_str']}–{c['hold_start_str']} ({c['start_temp']}°C → {c['peak_temp']}°C, {round(c['heat_mins'])}m) "
                f"& holding s/d {c['hold_end_str']} ({round(c['hold_mins'])}m)"
            )
        val_parts = []
        for v in multi_heat['valleys']:
            val_parts.append(
                f"Cooling parsial #{v['valley_no']} ({v['cool_start_str']}–{v['valley_str']}): turun dari {v['from_peak_temp']}°C ke {v['valley_temp']}°C "
                f"(-{v['drop_delta_c']}°C selama {round(v['cool_mins'])}m, belum mencapai <70°C) lalu dipanaskan ulang ke {v['to_peak_temp']}°C (+{v['rise_delta_c']}°C)"
            )
        rh_kwh = round((reheat_extra_mins / 60.0) * nom_kw, 1)
        rh_pwr_rp = round(rh_kwh * lwbp_rate)
        rh_tot_rp = rh_pwr_rp + reheat_steam_loss_rp
        masalah_note = f" Catatan operator: \"{identity.masalah}\"." if (identity and identity.masalah) else ""
        v_first = multi_heat['valleys'][0]
        forensic_findings.append({
            "code": "MULTIPLE_HEATING_CYCLES",
            "severity": "CRITICAL",
            "title": (
                f"Terdeteksi {multi_heat['cycle_count']}x Siklus Pemanasan (Re-Heating) dalam 1 Batch "
                f"(Turun ke {v_first['valley_temp']}°C Lalu Naik Kembali ke {v_first['to_peak_temp']}°C, +{round(reheat_extra_mins)} Menit)"
            ),
            "category": "Anomali Pemanasan Berulang (Re-Heating / Interupsi Proses)",
            "detail": (
                f"Dalam satu batch terdeteksi {multi_heat['cycle_count']} kali proses kenaikan suhu karena pendinginan pertama berhenti di {v_first['valley_temp']}°C "
                f"(di atas ambang 70°C) lalu dipanaskan ulang kembali. "
                f"Rincian: {'; '.join(cyc_parts)}. Interupsi: {'; '.join(val_parts)}.{masalah_note}"
            ),
            "impact": (
                f"Penambahan waktu siklus +{round(reheat_extra_mins)} menit, pemborosan uap ekstra siklus ulang +{round(reheat_steam_loss_kg, 1)} kg "
                f"(Rp {reheat_steam_loss_rp:,}), serta listrik sirkulasi +{rh_kwh} kWh (Rp {rh_pwr_rp:,}) — total kerugian re-heating Rp {rh_tot_rp:,}."
            ),
            "recommendation": (
                "Evaluasi penyebab pengulangan proses pada tengah jalan (seperti kain macet pada nozzle/reel, koreksi warna/shading ulang, "
                "atau gangguan sirkulasi) agar tidak terjadi pemanasan uap ganda dalam satu batch."
            ),
        })

    # Finding 1: Over-holding at Peak Temp
    if keep_ideal_m > 0 and over_hold_mins > 8:
        oh_kwh = round((over_hold_mins / 60.0) * nom_kw, 1)
        oh_rp = round(oh_kwh * lwbp_rate)
        forensic_findings.append({
            "code": "OVER_HOLDING",
            "severity": "CRITICAL" if over_hold_mins > 25 else "WARNING",
            "title": f"Over-Holding pada Suhu Puncak (+{round(over_hold_mins)} Menit di Atas Ideal)",
            "category": "Indikasi Operasional / Tunggu Sampel",
            "detail": (
                f"Fase Holding/Keeping berlangsung selama {round(hold_dur)} menit, padahal standar program hanya {round(keep_ideal_m)} menit. "
                f"Indikasi operator menunggu konfirmasi matching warna (lab), penambahan obat (shading), atau terlambat memindahkan tahapan."
            ),
            "impact": f"Pemborosan +{round(over_hold_mins)} menit waktu mesin, +{oh_kwh} kWh listrik (Rp {oh_rp:,}), serta radiasi uap terus-menerus pada suhu {round(process.max_temp or 130)}°C.",
            "recommendation": "Tetapkan batas waktu tunggu sampel warna maksimal 10 menit dan siapkan dyestuff koreksi lebih cepat.",
        })

    # Finding 2: Post-cooling idle (Hanya dievaluasi jika > 45 menit setelah <70°C)
    if late_stop_mins > 45:
        ls_kwh = round((excess_late_stop_mins / 60.0) * nom_kw, 1)
        ls_rp = round(ls_kwh * lwbp_rate)
        r70_str = timezone.localtime(process.reached_70c_time).strftime('%H:%M') if process.reached_70c_time else "-"
        end_str = timezone.localtime(process.end_time).strftime('%H:%M') if process.end_time else "-"
        forensic_findings.append({
            "code": "LATE_STOP_AFTER_COOLING",
            "severity": "WARNING" if late_stop_mins <= 60 else "CRITICAL",
            "title": f"Durasi Pasca-Cooling Melebihi Batas 45 Menit ({round(late_stop_mins)} Menit Setelah <70°C, Molor +{round(excess_late_stop_mins)} Menit)",
            "category": "Evaluasi Waktu Bongkar-Muat Kain",
            "detail": (
                f"Suhu mesin sudah turun mencapai 70°C pada pukul {r70_str}, dan mesin baru berhenti (OFF) pada pukul {end_str} "
                f"({round(late_stop_mins)} menit kemudian). Setelah dikurangi toleransi wajar keluar-masuk kain (45 menit), "
                f"terdapat kelebihan waktu +{round(excess_late_stop_mins)} menit."
            ),
            "impact": f"Kelebihan durasi sirkulasi listrik di atas batas toleransi 45 menit selama +{round(excess_late_stop_mins)} menit (+{ls_kwh} kWh / Rp {ls_rp:,}).",
            "recommendation": "Evaluasi apakah terjadi kendala saat keluar-masuk kain (unloading/loading) atau keterlambatan mematikan mesin setelah proses selesai.",
        })

    # Finding 2b: Cooling Phase Anomaly (Stagnasi Suhu di Tengah Cooling >=70°C atau Durasi Cooling Molor)
    cool_start_str = timezone.localtime(process.cooling_start_time).strftime('%H:%M') if process.cooling_start_time else "-"
    r70_or_end_str = (
        timezone.localtime(process.reached_70c_time).strftime('%H:%M')
        if process.reached_70c_time
        else (timezone.localtime(process.end_time).strftime('%H:%M') if process.end_time else "-")
    )
    if cooling_stagnant_mins >= 15 and (cool_overrun_mins > 10 or cool_dur > 35):
        cs_waste_m = max(cooling_stagnant_mins, cool_overrun_mins) if cool_ideal_m > 0 else cooling_stagnant_mins
        cs_kwh = round((cooling_stagnant_mins / 60.0) * nom_kw, 1)
        cs_rp = round(cs_kwh * lwbp_rate)
        ideal_info = f"; target ideal resep: {round(cool_ideal_m)} menit, molor +{round(cool_overrun_mins)} menit" if cool_ideal_m > 0 else ""
        forensic_findings.append({
            "code": "COOLING_STAGNATION_ANOMALY",
            "severity": "CRITICAL" if (cooling_stagnant_mins >= 30 or cool_overrun_mins >= 45) else "WARNING",
            "title": (
                f"Stagnasi / Jeda pada Fase Cooling selama {round(cooling_stagnant_mins)} Menit di Suhu ~{stag_avg_temp}°C "
                f"(Total Cooling {round(cool_dur)} Menit{f', +{round(cool_overrun_mins)}m di Atas Ideal' if cool_ideal_m > 0 else ''})"
            ),
            "category": "Anomali Fase Cooling & Kedisiplinan Operasional",
            "detail": (
                f"Fase Cooling dimulai pukul {cool_start_str} dan baru mencapai <70°C pukul {r70_or_end_str} "
                f"(total {round(cool_dur)} menit{ideal_info}). Pada rentang pukul {stag_start_str} s/d {stag_end_str} "
                f"({round(cooling_stagnant_mins)} menit), penurunan suhu berhenti/tertahan di sekitar {stag_avg_temp}°C (di atas ambang 70°C) "
                f"sebelum akhirnya didinginkan kembali."
            ),
            "impact": (
                f"Mesin bersirkulasi tanpa progres pendinginan selama {round(cooling_stagnant_mins)} menit "
                f"(pemborosan listrik +{cs_kwh} kWh / Rp {cs_rp:,} dan kehilangan kapasitas waktu mesin +{round(cs_waste_m)} menit)."
            ),
            "recommendation": (
                "Evaluasi aktivitas operator pada jam stagnasi tersebut: pastikan katup cooling water / proses drain-fill "
                "tidak ditinggalkan atau tertahan di tengah jalan sebelum suhu turun di bawah 70°C."
            ),
        })
    elif not is_multi_heating and cool_dur > 0 and (
        (cool_ideal_m > 0 and cool_overrun_mins > 15 and cool_dur > cool_ideal_m * 1.4)
        or (cool_ideal_m == 0 and cool_dur > 45)
    ):
        co_m = cool_overrun_mins if cool_ideal_m > 0 else (cool_dur - 30.0)
        co_kwh = round((co_m / 60.0) * nom_kw, 1)
        co_rp = round(co_kwh * lwbp_rate)
        forensic_findings.append({
            "code": "SLOW_COOLING_ANOMALY",
            "severity": "CRITICAL" if co_m >= 40 else "WARNING",
            "title": (
                f"Durasi Cooling Molor Signifikan ({round(cool_dur)} Menit"
                f"{f' vs Ideal {round(cool_ideal_m)} Menit, +{round(cool_overrun_mins)} Menit' if cool_ideal_m > 0 else ''})"
            ),
            "category": "Anomali Fase Cooling / Performa Pendinginan",
            "detail": (
                f"Penurunan suhu dari puncak ke <70°C ({cool_start_str} s/d {r70_or_end_str}) memakan waktu {round(cool_dur)} menit "
                f"dengan laju rata-rata {round(process.cooling_avg_gradient or 0, 2)} °C/menit"
                f"{f', melampaui target ideal program ({round(cool_ideal_m)} menit) sebesar +{round(cool_overrun_mins)} menit' if cool_ideal_m > 0 else ''}."
            ),
            "impact": f"Memperpanjang waktu siklus mesin +{round(co_m)} menit dan menambah konsumsi listrik sirkulasi +{co_kwh} kWh (Rp {co_rp:,}).",
            "recommendation": "Periksa bukaan katup air pendingin (cooling valve), tekanan suplai cooling water, serta kebersihan pipa Heat Exchanger (scaling).",
        })

    # Finding 3: Mid-heating pause / stagnation
    heat_span = process.heating_span or 0
    if heat_span > 0 and heat_dur > 0 and (heat_span - heat_dur) > 10:
        pause_m = round(heat_span - heat_dur, 1)
        forensic_findings.append({
            "code": "MID_HEATING_PAUSE",
            "severity": "WARNING",
            "title": f"Jeda / Stagnasi di Tengah Fase Heating ({pause_m} Menit)",
            "category": "Anomali Kurva Pemanasan",
            "detail": (
                f"Rentang waktu dari awal hingga akhir Heating memakan {round(heat_span)} menit, tetapi kenaikan suhu aktif hanya {round(heat_dur)} menit. "
                f"Terdapat {pause_m} menit di mana suhu tertahan di tengah jalan (dosing obat bertahap atau interupsi pemanasan)."
            ),
            "impact": f"Memperpanjang waktu siklus dan meningkatkan kehilangan panas radiasi dinding mesin.",
            "recommendation": "Periksa apakah jeda tersebut merupakan step dosing standar resep atau interupsi tidak terencana oleh operator.",
        })

    # Finding 4: Pre-heating idle
    if pre_heat_idle_mins > 20:
        forensic_findings.append({
            "code": "PRE_HEAT_IDLE",
            "severity": "INFO",
            "title": f"Persiapan Awal Sebelum Heating Cukup Lama ({round(pre_heat_idle_mins)} Menit)",
            "category": "Persiapan & Loading",
            "detail": (
                f"Mesin terdeteksi mulai aktif pukul {timezone.localtime(process.start_time).strftime('%H:%M')}, "
                f"namun pemanasan efektif (Real Heat) baru dimulai pukul {timezone.localtime(process.heating_start_time).strftime('%H:%M')}."
            ),
            "impact": f"Waktu sirkulasi dingin awal selama {round(pre_heat_idle_mins)} menit sebelum katup uap dibuka.",
            "recommendation": "Pastikan kain dan larutan obat sudah siap sebelum pompa sirkulasi utama dinyalakan.",
        })

    # Finding 5: Start Temp High
    if process.start_temp and process.start_temp > 60:
        forensic_findings.append({
            "code": "START_TEMP_HIGH",
            "severity": "WARNING",
            "title": f"Suhu Awal Pengisian Terlalu Tinggi ({round(process.start_temp, 1)}°C > 60°C)",
            "category": "Prosedur Awal Proses",
            "detail": "Proses dimulai pada suhu di atas 60°C yang berisiko menyebabkan belang warna (uneven dyeing) atau menandakan sisa air panas belum terkuras.",
            "impact": "Risiko cacat kualitas pencelupan (re-process / cuci ulang).",
            "recommendation": "Pastikan pembilasan dan pendinginan selesai sebelum memulai obat batch baru.",
        })

    # Finding 6: Database DataAnomaly records
    db_anomalies = DataAnomaly.objects.filter(process_record=process)
    for anom in db_anomalies:
        flags_list = anom.details.get("flags", []) if isinstance(anom.details, dict) else []
        stat_flags = [f for f in flags_list if f in ('SUHU', 'SUHU_HARD', 'HEAT', 'KEEP', 'COOL')]
        
        if anom.is_resolved:
            forensic_findings.append({
                "code": anom.anomaly_type,
                "severity": "INFO",
                "title": f"Status Resolusi Anomali: Selesai ({anom.resolved_action or 'SOLVED'})",
                "category": "Tindak Lanjut Engineering",
                "detail": f"Anomali ini telah diverifikasi dan diselesaikan ({anom.resolved_action}). Catatan: {anom.resolution_notes or '-'}",
                "impact": "Data anomali telah diarsip / diselesaikan.",
                "recommendation": "Tidak diperlukan tindakan lanjutan.",
            })
        elif stat_flags:
            # Hanya tampilkan jika ada deviasi statistik yang belum tercakup oleh kartu fisik di atas
            forensic_findings.append({
                "code": anom.anomaly_type,
                "severity": anom.severity,
                "title": f"Deviasi Statistik Master Program: {anom.anomaly_type} ({', '.join(stat_flags)})",
                "category": "Sistem Deteksi Statistik Mesin-Program",
                "detail": f"Terdeteksi deviasi di luar batas normal kalibrasi mesin untuk parameter: {', '.join(stat_flags)}.",
                "impact": "Menunjukkan profil waktu/suhu batch ini menyimpang dari histori normal mesin dan program terkait.",
                "recommendation": "Verifikasi kesesuaian input resep/program dan parameter kontrol mesin.",
            })

    # Jika tidak ada anomali yang melebihi ambang batas evaluasi, biarkan kosong agar tidak ditampilkan

    return {
        "id": process.id,
        "identity_id": identity.id if identity else None,
        "machine_id": process.machine.id,
        "machine_name": process.machine.name,
        "machine_group": process.machine.group.name if process.machine.group else "-",
        "batch_number": process.batch_number,
        "start_time_iso": process.start_time.isoformat() if process.start_time else None,
        "report_date": timezone.localtime(process.start_time - timedelta(hours=6)).strftime('%Y-%m-%d'),
        "is_complete": process.is_complete,
        "thermal_status": process.machine.last_thermal_status if not process.is_complete else None,
        "identity": {
            "nomor_order": identity.nomor_order if identity and identity.nomor_order else "-",
            "artikel_kain": identity.artikel_kain if identity and identity.artikel_kain else "-",
            "batch": identity.batch if identity and identity.batch else "-",
            "kode_buyer": identity.kode_buyer if identity and identity.kode_buyer else "-",
            "operator": identity.operator if identity and identity.operator else "-",
            "program": program.nama if program else "-",
            "jenis_proses": identity.get_jenis_proses_display() if identity else "-",
            "nomor_warna": identity.nomor_warna if identity and identity.nomor_warna else "-",
            "nomor_desain": identity.nomor_desain if identity and identity.nomor_desain else "-",
            "isi_per_tube": identity.isi_per_tube if identity and identity.isi_per_tube else "-",
            "output_yard": round(out_yd, 1) if out_yd else "-",
            "nozzle_main_pump": identity.nozzle_main_pump if identity and identity.nozzle_main_pump else "-",
            "cycle_puncak": identity.cycle_puncak if identity and identity.cycle_puncak else "-",
            "cycle_60": identity.cycle_60 if identity and identity.cycle_60 else "-",
            "start_time": timezone.localtime(process.start_time).strftime('%d %b %Y, %H:%M') if process.start_time else "-",
            "heat_start_time": timezone.localtime(process.heating_start_time).strftime('%d %b %Y, %H:%M') if process.heating_start_time else "-",
            "reached_70c_time": timezone.localtime(process.reached_70c_time).strftime('%d %b %Y, %H:%M') if process.reached_70c_time else "-",
            "end_time": timezone.localtime(process.end_time).strftime('%d %b %Y, %H:%M') if process.end_time else "In Progress",
            "masalah": identity.masalah if identity and identity.masalah else "",
            "keterangan": identity.keterangan if identity and identity.keterangan else "",
        },
        "kpi": {
            "duration_effective": round(process.duration_effective, 1) if process.duration_effective else None,
            "loss_time": loss_time,
            "efficiency": efficiency,
            "grade": grade,
        },
        "timing": {
            "heat_ideal": round(program.durasi_heating_ideal, 1) if program and program.durasi_heating_ideal else None,
            "keep_ideal": round(program.durasi_keeping_ideal, 1) if program and program.durasi_keeping_ideal else None,
            "cool_ideal": round(program.durasi_cooling_ideal, 1) if program and program.durasi_cooling_ideal else None,
            "total_ideal": round(program.durasi_ideal, 1) if program and program.durasi_ideal else None,
            "heat_actual": round(heat_dur, 0) if heat_dur else None,
            "hold_actual": round(hold_dur, 0) if hold_dur else None,
            "cool_actual": round(cool_dur, 0) if cool_dur else None,
            "total_actual": round(total_dur, 0) if total_dur else None,
            "peak_temp": round(process.max_temp, 1) if process.max_temp else None,
            "start_temp": round(process.start_temp, 1) if process.start_temp else None,
            "end_temp": round(process.end_temp, 1) if process.end_temp else None,
            "heat_gradient": round(process.heating_avg_gradient, 2) if process.heating_avg_gradient else None,
            "cool_gradient": round(process.cooling_avg_gradient, 2) if process.cooling_avg_gradient else None,
            "max_temp_prg": program.suhu_max if program else None,
            "ideal_heat": round(process.ideal_heating_time, 1) if process.ideal_heating_time else None,
            "avg_steam": round(avg_steam, 2) if avg_steam else None,
            "over_hold_mins": round(over_hold_mins, 1),
            "late_stop_mins": round(late_stop_mins, 1),
            "pre_heat_idle_mins": round(pre_heat_idle_mins, 1),
        },
        "phase_breakdown": phase_pct,
        "chart_data": chart_data,
        "avg_steam": round(avg_steam, 2) if avg_steam else None,
        "energy_financials": energy_financials,
        "program_benchmark": program_benchmark,
        "operator_forensics": forensic_findings,
        "plant_boiler_context": plant_boiler_context,
        "cooling_context": cooling_context,
    }

@report_router.get("/machine/{machine_id}/process-history")
def get_machine_process_history(request, machine_id: int, start_date: str, end_date: str):
    _require_permission(request, "monthly_report")
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}
        
    machine = get_object_or_404(Machine, id=machine_id)
    
    start_time = timezone.make_aware(dt_start.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time = timezone.make_aware(dt_end.replace(hour=6, minute=0, second=0, microsecond=0)) + timedelta(days=1)
    days_count = (end_time - start_time).days
    
    processes = DyeingProcess.objects.filter(
        machine_id=machine_id,
        start_time__gte=start_time,
        start_time__lt=end_time,
        is_valid_process=True
    )
    
    daily_stats = {i: {'count': 0, 'duration': 0.0, 'steam': 0.0} for i in range(days_count)}
    
    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)
    for p in processes:
        if not p.start_time: continue
        local_time = timezone.localtime(p.start_time)
        shifted_time = local_time - timedelta(hours=6)
        day_diff = (shifted_time.date() - dt_start.date()).days
        
        if 0 <= day_diff < days_count:
            daily_stats[day_diff]['count'] += 1
            if p.total_duration:
                daily_stats[day_diff]['duration'] += p.total_duration
            
            # Hitung uap
            if machine.batch_steam:
                daily_stats[day_diff]['steam'] += float(machine.batch_steam)
            elif machine.average_steam_usage and p.total_duration:
                daily_stats[day_diff]['steam'] += float(machine.average_steam_usage) * (p.total_duration / 60.0)
                
    chart_data = []
    counts = []
    for i in range(days_count):
        current_date = dt_start.date() + timedelta(days=i)
        count = daily_stats[i]['count']
        chart_data.append({
            "date": current_date.strftime("%d %b"),
            "count": count,
            "duration": round(daily_stats[i]['duration'], 1),
            "steam": round(daily_stats[i]['steam'], 1)
        })
        counts.append(count)
        
    avg = sum(counts) / len(counts) if counts else 0
    max_val = max(counts) if counts else 0
    min_val = min(counts) if counts else 0
    
    # Fetch summary for this machine
    daily_summary = _compute_daily_summary_data(date)
    machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)

    return {
        "summary": machine_stats,
        "machine_name": machine.name,
        "chart_data": chart_data,
        "avg": round(avg, 1),
        "max": max_val,
        "min": min_val
    }


BOILER_MACHINES = ["Steam_Pr", "Speed_RB_Steam", "Temp_RB_Steam", "Oil_Temp", "Temp_R_Bakar", "Speed_R_Bakar"]
BOILER_INTERVAL_MINUTES = 10
BOILER_TARGET_POINTS = 144


def _compute_boiler_chart_data(start_time, end_time, settings):
    """Build chart_data and pressure_dist for one boiler day window (06:00–06:00)."""
    from monitoring.models import MachineStatusSnapshot

    interval_minutes = BOILER_INTERVAL_MINUTES
    target_points = BOILER_TARGET_POINTS

    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp')

    all_machines = Machine.objects.filter(is_active=True).select_related('group')
    machines_dict = {m.code: m for m in all_machines}

    interval_data = defaultdict(lambda: {'steam_total': 0.0, 'hto_total': 0.0, 'power_total': 0.0, 'active_count': 0, 'count': 0})
    for snapshot in snapshots:
        time_diff = (snapshot.timestamp - start_time).total_seconds() / 60
        bucket_index = int(time_diff / interval_minutes)
        if bucket_index >= target_points:
            bucket_index = target_points - 1
        if bucket_index < 0:
            bucket_index = 0

        steam_total = 0.0
        steam_total_jet = 0.0
        steam_total_non_jet = 0.0
        hto_total = 0.0
        power_total = 0.0
        active_count = 0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = machines_dict.get(machine_code)
            if machine:
                # Steam
                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                is_steam_active = is_steam_active_from_snapshot(snap_data)
                if is_steam_active:
                    steam_total += (machine.average_steam_usage or 0)
                    if machine.group and machine.group.process_type == 'JET':
                        steam_total_jet += (machine.average_steam_usage or 0)
                    else:
                        steam_total_non_jet += (machine.average_steam_usage or 0)

                # HTO & Power
                status = snap_data.get('status')
                detail = snap_data.get('detail')
                is_machine_active = (status in ["HEAT", "STEADY", "Running", "COOL"]) or (detail in ["HEAT", "STEADY", "Running", "COOL"])
                
                if is_machine_active:
                    is_boiler = bool(machine.group and machine.group.code == "MC_BOILER")
                    if not is_boiler:
                        power_total += (machine.nominal_power or 0.0)
                        active_count += 1
                        if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                            hto_total += machine.avg_hto_calories

        interval_data[bucket_index]['steam_total'] += steam_total
        interval_data[bucket_index]['hto_total'] += hto_total
        interval_data[bucket_index]['power_total'] += power_total
        interval_data[bucket_index]['active_count'] += active_count
        if 'steam_total_jet' not in interval_data[bucket_index]:
            interval_data[bucket_index]['steam_total_jet'] = 0.0
            interval_data[bucket_index]['steam_total_non_jet'] = 0.0
        interval_data[bucket_index]['steam_total_jet'] += steam_total_jet
        interval_data[bucket_index]['steam_total_non_jet'] += steam_total_non_jet
        interval_data[bucket_index]['count'] += 1

    logs = MachineMinuteLog.objects.filter(
        machine__code__in=BOILER_MACHINES,
        timestamp__gte=start_time,
        timestamp__lt=end_time
    ).order_by('timestamp').values('machine__code', 'timestamp', 'temperature')

    boiler_data = defaultdict(lambda: {m: {'total': 0.0, 'count': 0} for m in BOILER_MACHINES})
    minute_raw = defaultdict(lambda: {m: {'total': 0.0, 'count': 0} for m in BOILER_MACHINES})

    for log in logs:
        if log['temperature'] is not None:
            time_diff = (log['timestamp'] - start_time).total_seconds() / 60
            bucket_index = int(time_diff / interval_minutes)
            minute_index = int(time_diff)
            code = log['machine__code']
            
            if 0 <= bucket_index < target_points:
                boiler_data[bucket_index][code]['total'] += log['temperature']
                boiler_data[bucket_index][code]['count'] += 1
            if 0 <= minute_index < 1440:
                minute_raw[minute_index][code]['total'] += log['temperature']
                minute_raw[minute_index][code]['count'] += 1
                
    minute_data = []
    for i in range(1440):
        m_time = timezone.localtime(start_time + timedelta(minutes=i)).strftime('%H:%M')
        row = {'time': m_time}
        for code in BOILER_MACHINES:
            m_data = minute_raw[i][code]
            row[code] = round(m_data['total'] / m_data['count'], 2) if m_data['count'] > 0 else None
        minute_data.append(row)

    chart_data = []
    pressure_dist = {'ideal': 0, 'under': 0, 'over': 0}
    bucket_hours = interval_minutes / 60

    for i in range(target_points):
        bucket_start = start_time + timedelta(minutes=i * interval_minutes)

        avg_steam_usage = 0.0
        avg_steam_usage_jet = 0.0
        avg_steam_usage_non_jet = 0.0
        avg_hto_usage = 0.0
        avg_power_kw = 0.0
        avg_active_machines = 0
        if interval_data[i]['count'] > 0:
            c = interval_data[i]['count']
            avg_steam_usage = interval_data[i]['steam_total'] / c
            avg_steam_usage_jet = interval_data[i].get('steam_total_jet', 0.0) / c
            avg_steam_usage_non_jet = interval_data[i].get('steam_total_non_jet', 0.0) / c
            avg_hto_usage = interval_data[i]['hto_total'] / c
            avg_power_kw = interval_data[i]['power_total'] / c
            avg_active_machines = round(interval_data[i]['active_count'] / c)

        data_point = {
            "time": timezone.localtime(bucket_start).strftime("%H:%M"),
            "steam_usage": round(avg_steam_usage, 1),
            "usage_jet": round(avg_steam_usage_jet, 1),
            "usage_non_jet": round(avg_steam_usage_non_jet, 1),
            "hto_usage": round(avg_hto_usage, 1),
            "power_kw": round(avg_power_kw, 1),
            "active_machines": avg_active_machines
        }

        for code in BOILER_MACHINES:
            b_data = boiler_data[i][code]
            if b_data['count'] > 0:
                val = b_data['total'] / b_data['count']
                data_point[code] = round(val, 2)
            else:
                data_point[code] = None

        speed_rb = data_point.get('Speed_RB_Steam')
        speed_r_bakar = data_point.get('Speed_R_Bakar')

        data_point['fuel_kg_steam'] = (
            round(speed_rb * settings.fuel_factor_steam_boiler * bucket_hours, 2)
            if speed_rb is not None and settings.fuel_factor_steam_boiler > 0 else None
        )
        data_point['fuel_kg_hto'] = (
            round(speed_r_bakar * settings.fuel_factor_hto_boiler * bucket_hours, 2)
            if speed_r_bakar is not None and settings.fuel_factor_hto_boiler > 0 else None
        )

        pr = data_point.get('Steam_Pr')
        if pr is not None and pr > 0:
            if pr < 3.5:
                pressure_dist['under'] += 1
            elif pr > 5.5:
                pressure_dist['over'] += 1
            else:
                pressure_dist['ideal'] += 1

        chart_data.append(data_point)

    return minute_data, chart_data, pressure_dist


def _compute_boiler_kpi_summary(chart_data, pressure_dist, settings):
    """Aggregate daily KPIs from chart_data buckets."""
    bucket_hours = BOILER_INTERVAL_MINUTES / 60

    total_steam_usage_kg = 0.0
    pressure_values = []
    oil_temp_values = []
    total_fuel_steam = 0.0
    total_fuel_hto = 0.0
    has_fuel_steam = settings.fuel_factor_steam_boiler > 0
    has_fuel_hto = settings.fuel_factor_hto_boiler > 0

    total_steam_usage_jet_kg = 0.0
    total_steam_usage_non_jet_kg = 0.0
    for point in chart_data:
        steam_rate = point.get('steam_usage') or 0
        total_steam_usage_kg += steam_rate * bucket_hours
        total_steam_usage_jet_kg += (point.get('usage_jet') or 0) * bucket_hours
        total_steam_usage_non_jet_kg += (point.get('usage_non_jet') or 0) * bucket_hours

        pr = point.get('Steam_Pr')
        if pr is not None and pr > 0:
            pressure_values.append(pr)

        oil_temp = point.get('Oil_Temp')
        if oil_temp is not None and oil_temp > 0:
            oil_temp_values.append(oil_temp)

        fuel_steam = point.get('fuel_kg_steam')
        if fuel_steam is not None:
            total_fuel_steam += fuel_steam

        fuel_hto = point.get('fuel_kg_hto')
        if fuel_hto is not None:
            total_fuel_hto += fuel_hto

    total_fuel_kg = None
    if has_fuel_steam or has_fuel_hto:
        total_fuel_kg = round(total_fuel_steam + total_fuel_hto, 1)

    specific_fuel_consumption = None
    if total_fuel_steam and total_fuel_steam > 0:
        specific_fuel_consumption = round(total_steam_usage_kg / total_fuel_steam, 2)

    total_pressure_buckets = pressure_dist['ideal'] + pressure_dist['under'] + pressure_dist['over']
    pressure_ideal_percent = (
        round((pressure_dist['ideal'] / total_pressure_buckets) * 100, 1)
        if total_pressure_buckets > 0 else None
    )

    return {
        "total_steam_usage_kg": round(total_steam_usage_kg, 1),
        "total_steam_usage_jet_kg": round(total_steam_usage_jet_kg, 1),
        "total_steam_usage_non_jet_kg": round(total_steam_usage_non_jet_kg, 1),
        "avg_pressure": round(sum(pressure_values) / len(pressure_values), 2) if pressure_values else None,
        "avg_oil_temp": round(sum(oil_temp_values) / len(oil_temp_values), 1) if oil_temp_values else None,
        "total_fuel_kg": total_fuel_kg,
        "total_fuel_steam_kg": round(total_fuel_steam, 1) if has_fuel_steam else None,
        "total_fuel_hto_kg": round(total_fuel_hto, 1) if has_fuel_hto else None,
        "specific_fuel_consumption": specific_fuel_consumption,
        "pressure_ideal_percent": pressure_ideal_percent,
    }


def _bucket_boiler_month_data(month_start, days_in_month):
    """
    Bulk-query one month of boiler data (1 snapshot query + 1 minute-log query)
    and bucket it into per-day chart_data / pressure_dist pairs, reusing the same
    10-minute bucket shape as `_compute_boiler_chart_data` but without re-querying
    the DB for each day. Returns a list of (chart_data, pressure_dist) tuples,
    one per day, ready to be fed into `_compute_boiler_kpi_summary`.
    """
    from monitoring.models import MachineStatusSnapshot, GlobalSettings

    settings = GlobalSettings.load()
    interval_minutes = BOILER_INTERVAL_MINUTES
    target_points = BOILER_TARGET_POINTS
    month_end = month_start + timedelta(days=days_in_month)
    bucket_hours = interval_minutes / 60

    # day_buckets[day_index][bucket_index] = {...}
    steam_buckets = [
        [{'steam_total': 0.0, 'count': 0} for _ in range(target_points)]
        for _ in range(days_in_month)
    ]
    boiler_buckets = [
        [{m: {'total': 0.0, 'count': 0} for m in BOILER_MACHINES} for _ in range(target_points)]
        for _ in range(days_in_month)
    ]

    def _day_and_bucket(ts):
        day_diff = (ts - month_start).days
        # Because of the 06:00 day boundary, use elapsed minutes since month_start
        # to avoid off-by-one issues around midnight.
        total_minutes = (ts - month_start).total_seconds() / 60
        day_index = int(total_minutes // (24 * 60))
        minute_in_day = total_minutes - day_index * 24 * 60
        bucket_index = int(minute_in_day / interval_minutes)
        if bucket_index >= target_points:
            bucket_index = target_points - 1
        if bucket_index < 0:
            bucket_index = 0
        return day_index, bucket_index

    all_steam_machines = Machine.objects.filter(is_active=True, average_steam_usage__gt=0).select_related('group')
    machines_dict = {m.code: m for m in all_steam_machines}

    snapshots = MachineStatusSnapshot.objects.filter(
        timestamp__gte=month_start,
        timestamp__lt=month_end
    ).order_by('timestamp')

    for snapshot in snapshots:
        day_index, bucket_index = _day_and_bucket(snapshot.timestamp)
        if not (0 <= day_index < days_in_month):
            continue

        steam_total = 0.0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = machines_dict.get(machine_code)
            if machine:
                is_active = False
                from monitoring.utils.steam_active import is_steam_active_from_snapshot
                is_active = is_steam_active_from_snapshot(snap_data)
                if is_active:
                    steam_total += machine.average_steam_usage

        steam_buckets[day_index][bucket_index]['steam_total'] += steam_total
        steam_buckets[day_index][bucket_index]['count'] += 1

    logs = MachineMinuteLog.objects.filter(
        machine__code__in=BOILER_MACHINES,
        timestamp__gte=month_start,
        timestamp__lt=month_end
    ).order_by('timestamp').values('machine__code', 'timestamp', 'temperature')

    for log in logs:
        if log['temperature'] is None:
            continue
        day_index, bucket_index = _day_and_bucket(log['timestamp'])
        if not (0 <= day_index < days_in_month):
            continue
        code = log['machine__code']
        boiler_buckets[day_index][bucket_index][code]['total'] += log['temperature']
        boiler_buckets[day_index][bucket_index][code]['count'] += 1

    results = []
    for day_index in range(days_in_month):
        chart_data = []
        pressure_dist = {'ideal': 0, 'under': 0, 'over': 0}

        for i in range(target_points):
            steam_bucket = steam_buckets[day_index][i]
            avg_steam_usage = 0.0
            avg_steam_usage_jet = 0.0
            avg_steam_usage_non_jet = 0.0
            if steam_bucket['count'] > 0:
                c = steam_bucket['count']
                avg_steam_usage = steam_bucket['steam_total'] / c
                avg_steam_usage_jet = steam_bucket.get('steam_total_jet', 0.0) / c
                avg_steam_usage_non_jet = steam_bucket.get('steam_total_non_jet', 0.0) / c

            data_point = {
                "steam_usage": round(avg_steam_usage, 1),
                "usage_jet": round(avg_steam_usage_jet, 1),
                "usage_non_jet": round(avg_steam_usage_non_jet, 1)
            }

            for code in BOILER_MACHINES:
                b_data = boiler_buckets[day_index][i][code]
                if b_data['count'] > 0:
                    data_point[code] = round(b_data['total'] / b_data['count'], 2)
                else:
                    data_point[code] = None

            speed_rb = data_point.get('Speed_RB_Steam')
            speed_r_bakar = data_point.get('Speed_R_Bakar')

            data_point['fuel_kg_steam'] = (
                round(speed_rb * settings.fuel_factor_steam_boiler * bucket_hours, 2)
                if speed_rb is not None and settings.fuel_factor_steam_boiler > 0 else None
            )
            data_point['fuel_kg_hto'] = (
                round(speed_r_bakar * settings.fuel_factor_hto_boiler * bucket_hours, 2)
                if speed_r_bakar is not None and settings.fuel_factor_hto_boiler > 0 else None
            )

            pr = data_point.get('Steam_Pr')
            if pr is not None and pr > 0:
                if pr < 3.5:
                    pressure_dist['under'] += 1
                elif pr > 5.5:
                    pressure_dist['over'] += 1
                else:
                    pressure_dist['ideal'] += 1

            chart_data.append(data_point)

        results.append((chart_data, pressure_dist))

    return results, settings


def _get_boiler_alert_history(start_time, end_time):
    """Return alert history list and severity counts for boiler machines."""
    from monitoring.models import Alert

    alerts_qs = Alert.objects.filter(
        machine__code__in=BOILER_MACHINES,
        created_at__gte=start_time,
        created_at__lt=end_time
    ).select_related('machine').order_by('created_at')

    alert_history = []
    critical_count = 0
    warning_count = 0

    for alert in alerts_qs:
        if alert.severity == Alert.SEVERITY_CRITICAL:
            critical_count += 1
        elif alert.severity == Alert.SEVERITY_WARNING:
            warning_count += 1

        alert_history.append({
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "title": alert.title,
            "message": alert.message,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "created_at": timezone.localtime(alert.created_at).strftime("%Y-%m-%d %H:%M"),
            "is_acknowledged": alert.is_acknowledged,
            "machine_code": alert.machine.code if alert.machine else None,
        })

    return alert_history, critical_count, warning_count


def _get_logical_boiler_today():
    """Tanggal operasional boiler saat ini (hari dimulai 06:00)."""
    logical_now = timezone.localtime() - timedelta(hours=6)
    return logical_now.date()


def upsert_boiler_daily_metric(
    target_date,
    chart_data=None,
    pressure_dist=None,
    alert_critical=None,
    alert_warning=None,
):
    """
    Hitung KPI boiler untuk satu hari (06:00–06:00) dan simpan ke BoilerDailyMetric.
    chart_data/pressure_dist opsional — jika sudah dihitung (bulk month), lewati query ulang.
    """
    from monitoring.models import GlobalSettings, BoilerDailyMetric

    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    start_time = timezone.make_aware(
        datetime.combine(target_date, datetime.min.time()).replace(hour=6, minute=0, second=0)
    )
    end_time = start_time + timedelta(days=1)

    settings = GlobalSettings.load()

    if chart_data is None or pressure_dist is None:
        _, chart_data, pressure_dist = _compute_boiler_chart_data(start_time, end_time, settings)

    kpi = _compute_boiler_kpi_summary(chart_data, pressure_dist, settings)

    if alert_critical is None or alert_warning is None:
        _, alert_critical, alert_warning = _get_boiler_alert_history(start_time, end_time)

    has_data = any(
        (p.get('Steam_Pr') or 0) > 0 or (p.get('steam_usage') or 0) > 0
        for p in chart_data
    )

    # PINN Efficiency Logic
    start_time = timezone.make_aware(datetime.combine(target_date, datetime.min.time())).replace(hour=6)
    end_time = start_time + timedelta(days=1)
    
    jet_processes = DyeingProcess.objects.filter(
        machine__group__process_type='JET',
        start_time__gte=start_time,
        start_time__lt=end_time,
        is_valid_process=True
    )
    sum_lapis_1 = sum((p.predicted_steam_kg or 0) for p in jet_processes)
    # Lapis 3 fallback ke Lapis 1
    sum_lapis_3 = sum((p.predicted_steam_ideal_kg if p.predicted_steam_ideal_kg is not None else (p.predicted_steam_kg or 0)) for p in jet_processes)
    
    ratio = (sum_lapis_3 / sum_lapis_1) if sum_lapis_1 > 0 else 1.0
    
    actual_jet = kpi.get('total_steam_usage_jet_kg', 0.0)
    actual_non_jet = kpi.get('total_steam_usage_non_jet_kg', 0.0)
    
    ideal_jet = actual_jet * ratio
    total_steam_ideal = actual_non_jet + ideal_jet
    
    eff_pct = None
    if kpi['total_steam_usage_kg'] > 0:
        eff_pct = round((total_steam_ideal / kpi['total_steam_usage_kg']) * 100, 1)

    metric, _ = BoilerDailyMetric.objects.update_or_create(
        date=target_date,
        defaults={
            'total_steam_usage_kg': kpi['total_steam_usage_kg'],
            'total_steam_ideal_usage_kg': round(total_steam_ideal, 1),
            'steam_efficiency_percent': eff_pct,
            'avg_pressure': kpi['avg_pressure'],
            'avg_oil_temp': kpi['avg_oil_temp'],
            'total_fuel_kg': kpi['total_fuel_kg'],
            'total_fuel_steam_kg': kpi['total_fuel_steam_kg'],
            'total_fuel_hto_kg': kpi['total_fuel_hto_kg'],
            'specific_fuel_consumption': kpi['specific_fuel_consumption'],
            'pressure_ideal_percent': kpi['pressure_ideal_percent'],
            'pressure_ideal_count': pressure_dist['ideal'],
            'pressure_under_count': pressure_dist['under'],
            'pressure_over_count': pressure_dist['over'],
            'alert_count_critical': alert_critical,
            'alert_count_warning': alert_warning,
            'alert_count_total': alert_critical + alert_warning,
            'has_data': has_data,
        },
    )
    return metric


def _boiler_daily_metric_to_day_dict(metric):
    """Serialisasi BoilerDailyMetric ke format response kalender."""
    return {
        "date": metric.date.strftime("%Y-%m-%d"),
        "total_steam_usage_kg": metric.total_steam_usage_kg,
        "steam_efficiency_percent": metric.steam_efficiency_percent,
        "avg_pressure": metric.avg_pressure,
        "avg_oil_temp": metric.avg_oil_temp,
        "total_fuel_kg": metric.total_fuel_kg,
        "total_fuel_steam_kg": metric.total_fuel_steam_kg,
        "total_fuel_hto_kg": metric.total_fuel_hto_kg,
        "specific_fuel_consumption": metric.specific_fuel_consumption,
        "pressure_ideal_percent": metric.pressure_ideal_percent,
        "alert_count_critical": metric.alert_count_critical,
        "alert_count_warning": metric.alert_count_warning,
        "alert_count_total": metric.alert_count_total,
        "pressure_dist": {
            "ideal": metric.pressure_ideal_count,
            "under": metric.pressure_under_count,
            "over": metric.pressure_over_count,
        },
        "from_cache": True,
    }



def _detect_boiler_regulations(minute_data, settings):
    speed_max = settings.boiler_regulation_speed_max
    pre_window_min = settings.boiler_regulation_pre_window_min
    gap_tolerance = settings.boiler_regulation_gap_tolerance_min

    events = []
    
    def _detect_channel(speed_key, temp_key, min_temp, channel_name):
        channel_events = []
        current_event = None
        for log in minute_data:
            speed = log.get(speed_key)
            temp = log.get(temp_key)
            
            if speed is not None and temp is not None:
                if speed <= speed_max and temp >= min_temp:
                    if current_event is None:
                        current_event = {
                            'channel': channel_name,
                            'start_time': log.get('time', '00:00'),
                            'duration_minutes': 1,
                            'peak_value': temp
                        }
                    else:
                        current_event['duration_minutes'] += 1
                        current_event['peak_value'] = max(current_event['peak_value'], temp)
                else:
                    if current_event is not None:
                        channel_events.append(current_event)
                        current_event = None
        if current_event is not None:
            channel_events.append(current_event)
        
        return channel_events

    events.extend(_detect_channel('Speed_RB_Steam', 'Steam_Pr', settings.boiler_regulation_pressure_min, 'STEAM'))
    events.extend(_detect_channel('Speed_R_Bakar', 'Oil_Temp', settings.boiler_regulation_hto_oil_temp_min, 'HTO'))
    
    return events

def _regulation_events_to_alerts(regulation_events, date_str):
    alerts = []
    for ev in regulation_events:
        if ev['channel'] == 'STEAM':
            title = f"Regulasi Boiler Steam – {ev['duration_minutes']} menit"
            message = f"Speed batu bara turun drastis saat tekanan steam mencapai {ev['peak_value']} bar"
            machine_code = "Speed_RB_Steam"
        else:
            title = f"Regulasi Boiler HTO – {ev['duration_minutes']} menit"
            message = f"Speed HTO turun drastis saat suhu oli mencapai {ev['peak_value']} °C"
            machine_code = "Speed_R_Bakar"
        
        created_at_str = f"{date_str} {ev['start_time']}"
        alerts.append({
            "severity": "WARNING",
            "alert_type": "REGULATION",
            "title": title,
            "message": message,
            "current_value": ev['peak_value'],
            "threshold_value": None,
            "created_at": created_at_str,
            "is_acknowledged": False,
            "machine_code": machine_code,
            "regulation_meta": ev,
        })
    return alerts

@report_router.get("/boiler-summary")
def get_boiler_summary(request, date: str):
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}

    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()

    start_time = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))
    end_time = start_time + timedelta(days=1)

    minute_data, chart_data, pressure_dist = _compute_boiler_chart_data(start_time, end_time, settings)
    kpi_summary = _compute_boiler_kpi_summary(chart_data, pressure_dist, settings)
    alert_history, critical_count, warning_count = _get_boiler_alert_history(start_time, end_time)

    regulation_events = _detect_boiler_regulations(minute_data, settings)
    steam_count = sum(1 for e in regulation_events if e['channel'] == 'STEAM')
    hto_count = sum(1 for e in regulation_events if e['channel'] == 'HTO')
    regulation_alerts = _regulation_events_to_alerts(regulation_events, start_time.strftime("%Y-%m-%d"))
    
    alert_history = sorted(
        alert_history + regulation_alerts,
        key=lambda x: str(x['created_at']), reverse=True
    )
    warning_count += len(regulation_alerts)

    kpi_summary["alert_count_critical"] = critical_count
    kpi_summary["alert_count_warning"] = warning_count
    kpi_summary["alert_count_total"] = len(alert_history)

    return {
        "date_range": f"{start_time.strftime('%d %b %Y %H:%M')} - {end_time.strftime('%d %b %Y %H:%M')}",
        "chart_data": chart_data,
        "pressure_dist": pressure_dist,
        "kpi_summary": kpi_summary,
        "alert_history": alert_history,
        "regulation_summary": {
            "total": len(regulation_events),
            "steam_count": steam_count,
            "hto_count": hto_count,
        },
        "fuel_config": {
            "steam_calibrated": settings.fuel_factor_steam_boiler > 0,
            "hto_calibrated": settings.fuel_factor_hto_boiler > 0,
            "fuel_factor_steam_boiler": settings.fuel_factor_steam_boiler,
            "fuel_factor_hto_boiler": settings.fuel_factor_hto_boiler,
            "steam_sensor_hz": "Speed_RB_Steam",
            "hto_sensor_hz": "Speed_R_Bakar",
            "formula": "kg/jam = Hz × faktor",
        },
    }


@report_router.get("/boiler-weekly-baseline")
def get_boiler_weekly_baseline(request, date: str):
    """Average KPI metrics from the 7 days before the selected date."""
    _require_permission(request, "boiler_report")
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format, use YYYY-MM-DD"}

    from monitoring.models import GlobalSettings
    settings = GlobalSettings.load()

    selected_start = timezone.make_aware(dt.replace(hour=6, minute=0, second=0, microsecond=0))

    from monitoring.models import BoilerDailyMetric
    start_date_7d = (selected_start - timedelta(days=7)).date()
    end_date_7d = (selected_start - timedelta(days=1)).date()
    cached_metrics = {
        m.date: m
        for m in BoilerDailyMetric.objects.filter(date__gte=start_date_7d, date__lte=end_date_7d)
    }

    daily_kpis = []
    for day_offset in range(7, 0, -1):
        day_date = (selected_start - timedelta(days=day_offset)).date()
        metric = cached_metrics.get(day_date)
        if not metric:
            try:
                metric = upsert_boiler_daily_metric(day_date)
            except Exception:
                metric = None

        if metric:
            daily_kpis.append({
                "total_steam_usage_kg": metric.total_steam_usage_kg,
                "avg_pressure": metric.avg_pressure,
                "avg_oil_temp": metric.avg_oil_temp,
                "total_fuel_kg": metric.total_fuel_kg,
                "specific_fuel_consumption": metric.specific_fuel_consumption,
                "pressure_ideal_percent": metric.pressure_ideal_percent,
                "alert_count_total": metric.alert_count_total,
                "alert_count_critical": metric.alert_count_critical,
                "alert_count_warning": metric.alert_count_warning,
            })

    if not daily_kpis:
        return {"error": "No baseline data available"}

    def _avg(values):
        valid = [v for v in values if v is not None]
        return round(sum(valid) / len(valid), 2) if valid else None

    return {
        "period": f"7 hari sebelum {dt.strftime('%d %b %Y')}",
        "days_counted": len(daily_kpis),
        "avg_total_steam_usage_kg": _avg([k["total_steam_usage_kg"] for k in daily_kpis]),
        "avg_pressure": _avg([k["avg_pressure"] for k in daily_kpis]),
        "avg_oil_temp": _avg([k["avg_oil_temp"] for k in daily_kpis]),
        "avg_total_fuel_kg": _avg([k["total_fuel_kg"] for k in daily_kpis if k["total_fuel_kg"] is not None]),
        "avg_specific_fuel_consumption": _avg([k["specific_fuel_consumption"] for k in daily_kpis if k["specific_fuel_consumption"] is not None]),
        "avg_pressure_ideal_percent": _avg([k["pressure_ideal_percent"] for k in daily_kpis if k["pressure_ideal_percent"] is not None]),
        "avg_alert_count_total": round(sum(k["alert_count_total"] for k in daily_kpis) / len(daily_kpis), 1),
        "avg_alert_count_critical": round(sum(k["alert_count_critical"] for k in daily_kpis) / len(daily_kpis), 1),
    }


@report_router.get("/boiler-monthly-calendar")
def get_boiler_monthly_calendar(request, year: int, month: int):
    """
    Ringkasan KPI boiler per hari untuk satu bulan (tampilan kalender).
    Membaca dari BoilerDailyMetric (cache) bila tersedia; hanya menghitung ulang
    hari yang belum di-cache atau hari operasional berjalan (hari ini).
    """
    _require_permission(request, "boiler_calendar")
    if not (1 <= month <= 12):
        return {"error": "Month must be between 1 and 12"}

    from monitoring.models import GlobalSettings, BoilerDailyMetric

    settings = GlobalSettings.load()
    month_start = timezone.make_aware(datetime(year, month, 1, 6, 0, 0))
    next_month = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    month_end = timezone.make_aware(next_month.replace(hour=6, minute=0, second=0, microsecond=0))
    days_in_month = (month_end - month_start).days
    logical_today = _get_logical_boiler_today()

    first_date = month_start.date()
    last_date = (month_start + timedelta(days=days_in_month - 1)).date()

    cached_metrics = {
        m.date: m
        for m in BoilerDailyMetric.objects.filter(
            date__gte=first_date,
            date__lte=last_date,
        )
    }

    days_to_refresh = []
    for day_index in range(days_in_month):
        day_date = (month_start + timedelta(days=day_index)).date()
        
        # Skip future days so we don't recalculate them endlessly
        if day_date > logical_today:
            continue
            
        # Refresh if missing from cache, or if it is today. 
        # Ignore past days that are cached with has_data=False (assumed empty/holiday).
        if day_date not in cached_metrics or day_date == logical_today:
            days_to_refresh.append(day_index)

    cache_hits = days_in_month - len(days_to_refresh)

    if len(days_to_refresh) > 1:
        from monitoring.models import Alert

        daily_chart_pairs, _settings = _bucket_boiler_month_data(month_start, days_in_month)

        alerts_qs = Alert.objects.filter(
            machine__code__in=BOILER_MACHINES,
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).values('created_at', 'severity')

        alert_counts = defaultdict(lambda: {'critical': 0, 'warning': 0})
        for alert in alerts_qs:
            total_minutes = (alert['created_at'] - month_start).total_seconds() / 60
            day_index = int(total_minutes // (24 * 60))
            if 0 <= day_index < days_in_month:
                if alert['severity'] == Alert.SEVERITY_CRITICAL:
                    alert_counts[day_index]['critical'] += 1
                elif alert['severity'] == Alert.SEVERITY_WARNING:
                    alert_counts[day_index]['warning'] += 1

        for day_index in days_to_refresh:
            day_date = (month_start + timedelta(days=day_index)).date()
            chart_data, pressure_dist = daily_chart_pairs[day_index]
            counts = alert_counts.get(day_index, {'critical': 0, 'warning': 0})
            upsert_boiler_daily_metric(
                day_date,
                chart_data=chart_data,
                pressure_dist=pressure_dist,
                alert_critical=counts['critical'],
                alert_warning=counts['warning'],
            )

        cached_metrics = {
            m.date: m
            for m in BoilerDailyMetric.objects.filter(
                date__gte=first_date,
                date__lte=last_date,
            )
        }
    elif len(days_to_refresh) == 1:
        day_date = (month_start + timedelta(days=days_to_refresh[0])).date()
        upsert_boiler_daily_metric(day_date)
        metric = BoilerDailyMetric.objects.get(date=day_date)
        cached_metrics[day_date] = metric

    days = [
        _boiler_daily_metric_to_day_dict(cached_metrics[(month_start + timedelta(days=i)).date()])
        for i in range(days_in_month)
        if (month_start + timedelta(days=i)).date() in cached_metrics
    ]

    # Hari tanpa entri cache (mis. masa depan) — placeholder kosong
    if len(days) < days_in_month:
        existing_dates = {d['date'] for d in days}
        for day_index in range(days_in_month):
            day_date = (month_start + timedelta(days=day_index)).date()
            date_str = day_date.strftime("%Y-%m-%d")
            if date_str not in existing_dates:
                days.append({
                    "date": date_str,
                    "total_steam_usage_kg": 0,
                    "avg_pressure": None,
                    "avg_oil_temp": None,
                    "total_fuel_kg": None,
                    "specific_fuel_consumption": None,
                    "pressure_ideal_percent": None,
                    "alert_count_critical": 0,
                    "alert_count_warning": 0,
                    "alert_count_total": 0,
                    "pressure_dist": {"ideal": 0, "under": 0, "over": 0},
                    "from_cache": False,
                })
        days.sort(key=lambda d: d['date'])

    return {
        "year": year,
        "month": month,
        "days": days,
        "cache_hits": cache_hits,
        "days_computed": days_in_month - cache_hits,
        "fuel_config": {
            "steam_calibrated": settings.fuel_factor_steam_boiler > 0,
            "hto_calibrated": settings.fuel_factor_hto_boiler > 0,
        },
    }


@report_router.get("/machine-daily-summary")
def get_machine_daily_summary(request, date: str, window: str = "1D"):
    _require_permission(request, "machine_daily_report")
    from monitoring.utils.machine_fleet_summary import compute_machine_fleet_summary
    return compute_machine_fleet_summary(date, window)


@report_router.get("/daily-batch-overview")
def get_daily_batch_overview(request, date: str = None, page: int = 1, search: str = None, sort: str = None, status: str = None):
    """
    Porting dari monitoring.views.daily_batch_overview: daftar batch DyeingProcess
    pada satu tanggal + data sparkline (downsampled) per batch.

    Tambahan: pencarian (mesin/batch/program), sorting, filter status
    (running/completed), ringkasan statistik, dan pin batch favorit per user.
    """
    _require_permission(request, "daily_batch_overview")
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    if date:
        try:
            selected_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.localtime(timezone.now()).date()
    else:
        selected_date = timezone.localtime(timezone.now()).date()

    favorite_ids = set()
    if getattr(request, "user", None) and request.user.is_authenticated:
        favorite_ids = set(
            UserFavoriteBatch.objects.filter(user=request.user).values_list("process_id", flat=True)
        )

    day_q = Q(start_time__date=selected_date)
    # Favorit yang masih berjalan ikut muncul meski start beda hari (kecuali filter completed).
    if favorite_ids and status != "completed":
        day_q = day_q | Q(id__in=list(favorite_ids), is_complete=False)

    qs = DyeingProcess.objects.filter(day_q).select_related(
        "machine", "machine__group", "identity", "identity__program"
    )

    if search:
        qs = qs.filter(
            Q(machine__name__icontains=search)
            | Q(machine__code__icontains=search)
            | Q(batch_number__icontains=search)
            | Q(identity__program__nama__icontains=search)
        )

    if status == "running":
        qs = qs.filter(is_complete=False)
    elif status == "completed":
        qs = qs.filter(is_complete=True)

    sort_map = {
        "machine": ("machine__code", "start_time"),
        "start_time": ("start_time",),
        "start_time_desc": ("-start_time",),
    }
    sort_fields = sort_map.get(sort, ("machine__code", "start_time"))

    if favorite_ids:
        qs = qs.annotate(
            fav_rank=Case(
                When(pk__in=list(favorite_ids), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("fav_rank", *sort_fields)
    else:
        qs = qs.order_by(*sort_fields)

    day_qs = DyeingProcess.objects.filter(start_time__date=selected_date)
    running_count = day_qs.filter(is_complete=False).count()
    completed_count = day_qs.filter(is_complete=True).count()

    all_efficiencies = []
    for p in qs:
        ident = getattr(p, "identity", None)
        prog = ident.program if ident else None
        if prog and prog.durasi_ideal is not None and p.duration_effective and p.duration_effective > 0:
            all_efficiencies.append((prog.durasi_ideal / p.duration_effective) * 100)

    paginator = Paginator(qs, 20)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    processes = page_obj.object_list
    results = []

    # Bulk fetch logs untuk seluruh 20 proses sekaligus (menghilangkan 20 query N+1)
    machine_ids = [p.machine_id for p in processes]
    if processes:
        min_start = min(p.start_time for p in processes)
        now_dt = timezone.now()
        max_end = max((p.end_time or now_dt) for p in processes)
        all_logs_qs = (
            MachineMinuteLog.objects
            .filter(machine_id__in=machine_ids, timestamp__range=(min_start, max_end))
            .values_list("machine_id", "timestamp", "temperature")
            .order_by("timestamp")
        )
        logs_by_machine_map = defaultdict(list)
        for m_id, ts, temp in all_logs_qs:
            logs_by_machine_map[m_id].append((ts, temp))
    else:
        logs_by_machine_map = {}

    for process in processes:
        start_dt = process.start_time
        end_dt = process.end_time if process.is_complete else timezone.now()
        m_logs = logs_by_machine_map.get(process.machine_id, [])
        logs_list = [(ts, temp) for ts, temp in m_logs if start_dt <= ts <= end_dt]
        total_logs = len(logs_list)
        target_points = 80
        if total_logs > target_points:
            step = total_logs // target_points
            downsampled = logs_list[::step]
        else:
            downsampled = logs_list

        sparkline = [
            {"time": timezone.localtime(ts).strftime("%H:%M"), "temp": temp}
            for ts, temp in downsampled
        ]

        identity = getattr(process, "identity", None)
        program = identity.program if identity else None

        loss_time = None
        efficiency = None
        if program and program.durasi_ideal is not None and process.duration_effective and process.duration_effective > 0:
            loss_time = round(process.duration_effective - program.durasi_ideal, 1)
            efficiency = round((program.durasi_ideal / process.duration_effective) * 100, 1)

        results.append({
            "id": process.pk,
            "machine_code": process.machine.code,
            "machine_name": process.machine.name,
            "batch_number": process.batch_number,
            "start_time": timezone.localtime(process.start_time).strftime("%H:%M"),
            "end_time": "Now" if not process.is_complete else (timezone.localtime(process.end_time).strftime("%H:%M") if process.end_time else "-"),
            "is_running": not process.is_complete,
            "program_name": program.nama if program else None,
            "loss_time": loss_time,
            "efficiency": efficiency,
            "sparkline": sparkline,
            "is_favorited": process.pk in favorite_ids,
        })

    return {
        "results": results,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "total_matches": qs.count(),
        "total_batches_today": day_qs.count(),
        "running_count": running_count,
        "completed_count": completed_count,
        "avg_efficiency": round(sum(all_efficiencies) / len(all_efficiencies), 1) if all_efficiencies else None,
        "selected_date": selected_date.isoformat(),
    }


@report_router.post("/batch-favorites")
def add_batch_favorite(request, payload: BatchFavoriteIn):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    process = get_object_or_404(DyeingProcess, pk=payload.process_id)
    UserFavoriteBatch.objects.get_or_create(user=request.user, process=process)
    return {"process_id": process.pk, "is_favorited": True}


@report_router.delete("/batch-favorites/{process_id}")
def remove_batch_favorite(request, process_id: int):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    UserFavoriteBatch.objects.filter(user=request.user, process_id=process_id).delete()
    return {"process_id": process_id, "is_favorited": False}

