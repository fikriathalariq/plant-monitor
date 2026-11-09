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

from monitoring.services.batch_cost_calculator import BatchCostCalculator, ProcessDiagnosticService
from monitoring.services.daily_summary_service import DailySummaryService
from monitoring.services.process_analytics_service import ProcessAnalyticsService

# Re-export aliases for full backward compatibility
sort_machines_custom = ProcessDiagnosticService.sort_machines_custom
classify_process_problems = ProcessDiagnosticService.classify_process_problems
_compute_downtime_ranking = ProcessDiagnosticService.compute_downtime_ranking
_compute_batch_electricity_metrics = BatchCostCalculator.compute_electricity
_compute_changeover_stats = ProcessDiagnosticService.compute_changeover_stats


@report_router.get("/daily-summary")
def get_daily_summary(request, date: str):
    _require_permission(request, "daily_report")
    return _compute_daily_summary_data(date)


def _compute_daily_summary_data(date: str):
    """Logika inti daily-summary didelegasikan ke DailySummaryService untuk
    menjaga modularitas, performa, dan kemudahan testing."""
    return DailySummaryService.compute_daily_summary(date)


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
    try:
        daily_summary = _compute_daily_summary_data(date)
        machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)
    except Exception:
        machine_stats = None

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
    try:
        daily_summary = _compute_daily_summary_data(date)
        machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)
    except Exception:
        machine_stats = None

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
    return ProcessAnalyticsService.compute_analytics(process_id=process_id, machine=machine, batch=batch, request=request)


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
    try:
        daily_summary = _compute_daily_summary_data(end_date or start_date)
        machine_stats = next((m for m in daily_summary.get('efficiency_summary', {}).get('machines', []) if m['machine_id'] == machine_id), None)
    except Exception:
        machine_stats = None

    return {
        "summary": machine_stats,
        "machine_name": machine.name,
        "chart_data": chart_data,
        "avg": round(avg, 1),
        "max": max_val,
        "min": min_val
    }


from monitoring.services.boiler_analytics_service import BoilerAnalyticsService

# Re-export aliases & constants for backward compatibility (used by api_boiler.py, api_dashboard.py, etc.)
BOILER_MACHINES = BoilerAnalyticsService.MACHINES
BOILER_INTERVAL_MINUTES = BoilerAnalyticsService.INTERVAL_MINUTES
BOILER_TARGET_POINTS = BoilerAnalyticsService.TARGET_POINTS

_compute_boiler_chart_data = BoilerAnalyticsService.compute_chart_data
_compute_boiler_kpi_summary = BoilerAnalyticsService.compute_kpi_summary
_bucket_boiler_month_data = BoilerAnalyticsService.bucket_boiler_month_data
_get_boiler_alert_history = BoilerAnalyticsService.get_alert_history
_get_logical_boiler_today = BoilerAnalyticsService.get_logical_today
upsert_boiler_daily_metric = BoilerAnalyticsService.upsert_daily_metric
_boiler_daily_metric_to_day_dict = BoilerAnalyticsService.daily_metric_to_day_dict
_detect_boiler_regulations = BoilerAnalyticsService.detect_regulations
_regulation_events_to_alerts = BoilerAnalyticsService.regulation_events_to_alerts


@report_router.get("/boiler-summary")
def get_boiler_summary(request, date: str):
    return BoilerAnalyticsService.get_summary(date)


@report_router.get("/boiler-weekly-baseline")
def get_boiler_weekly_baseline(request, date: str):
    """Average KPI metrics from the 7 days before the selected date."""
    _require_permission(request, "boiler_report")
    return BoilerAnalyticsService.get_weekly_baseline(date)


@report_router.get("/boiler-monthly-calendar")
def get_boiler_monthly_calendar(request, year: int, month: int):
    """
    Ringkasan KPI boiler per hari untuk satu bulan (tampilan kalender).
    Membaca dari BoilerDailyMetric (cache) bila tersedia; hanya menghitung ulang
    hari yang belum di-cache atau hari operasional berjalan (hari ini).
    """
    _require_permission(request, "boiler_calendar")
    return BoilerAnalyticsService.get_monthly_calendar(year, month)


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

