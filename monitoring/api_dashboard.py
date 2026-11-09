from ninja import Router

from ninja.errors import HttpError

from datetime import datetime, timedelta

from django.utils import timezone

from django.db.models import Count, Q, F

from django.shortcuts import get_object_or_404

import random

from monitoring.models import Machine, MachineGroup, DyeingProcess, MachineMinuteLog

from monitoring.utils.manual_status import get_status_since_info

from monitoring.utils.signal_freshness import get_machine_display_status

dashboard_router = Router(tags=["Dashboard"])

def get_machine_status_logic(machine):

    return get_machine_display_status(machine)

def get_active_since(machine, active_batch=None):

    """Backward-compatible wrapper — returns display string only."""

    info = get_status_since_info(machine, active_batch)

    return info.get("active_since") or info.get("status_since_display")

def normalize_heatmap_status(status):

    norm_status = (status or "OFF").upper()

    if norm_status in ("STOP", "OFFLINE", "NO SIGNAL"):

        return "OFF" if norm_status != "NO SIGNAL" else "NOSIGNAL"

    if norm_status == "RUNNING":

        return "RUNNING"

    return norm_status

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

@dashboard_router.get("/steam-traffic")

def get_steam_traffic(request):

    machines = list(Machine.objects.filter(is_active=True))

    steam_pr_machine = next((m for m in machines if m.code == 'Steam_Pr'), None)

    current_pressure = steam_pr_machine.temperature if steam_pr_machine and steam_pr_machine.temperature else 0.0

    oil_temp_machine = next((m for m in machines if m.code == 'Oil_Temp'), None)

    current_oil_temp = oil_temp_machine.temperature if oil_temp_machine and oil_temp_machine.temperature else 0.0

    current_usage = 0.0

    current_hto = 0.0

    active_count = 0

    from monitoring.utils.steam_active import is_steam_active_from_machine

    for m in machines:

        status = get_machine_status_logic(m)

        is_active = is_steam_active_from_machine(m)

        if is_active:

            current_usage += (m.average_steam_usage or 0.0)

            if m.avg_hto_calories and m.avg_hto_calories > 0:

                current_hto += m.avg_hto_calories

            active_count += 1

    # Generate 24h dummy series

    now = datetime.now()

    series = []

    for i in range(24, -1, -1):

        dt = now - timedelta(hours=i)

        # Bikin data melengkung (sinusoidal) untuk usage & pressure

        hour_factor = (dt.hour / 24.0) * 3.14 * 2

        base_usage = 1000 + (500 * (1 + random.random()))

        base_pressure = 3.0 + (1.0 * random.random())

        series.append({

            "time": dt.strftime("%H:00"),

            "usage": round(base_usage, 1),

            "pressure": round(base_pressure, 2)

        })

    return {

        "current_usage": round(current_usage, 1),

        "current_hto": round(current_hto, 1),

        "active_machines": active_count,

        "current_pressure": round(current_pressure, 2),

        "current_oil_temp": round(current_oil_temp, 1),

        "series": series

    }

@dashboard_router.get("/steam-sales")
def get_steam_sales(request, days: int = 7):
    from django.core.cache import cache
    cache_key = f"dashboard_steam_sales_v3_{days}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val

    from monitoring.models import DailyPlantMetric, BoilerDailyMetric
    from monitoring.api_report import _compute_daily_summary_data, upsert_boiler_daily_metric

    now = timezone.localtime()
    logical_now = now - timedelta(hours=6)
    logical_today = logical_now.date()

    series = []
    total = 0.0
    yesterday_availability = 0.0
    yesterday_efficiency = 0.0

    num_days = min(max(days, 1), 60)
    availabilities = []
    efficiencies = []

    if num_days > 7:
        min_date = logical_today - timedelta(days=num_days - 1)
        boiler_metrics = {
            m.date: m
            for m in BoilerDailyMetric.objects.filter(date__gte=min_date, date__lt=logical_today)
        }
        plant_metrics = {
            m.date: m
            for m in DailyPlantMetric.objects.filter(date__gte=min_date, date__lt=logical_today)
        }

        for i in range(num_days - 1, 0, -1):
            target_date = logical_today - timedelta(days=i)
            bm = boiler_metrics.get(target_date)
            usage = bm.total_steam_usage_kg if bm else 0.0

            # Kumpulkan efisiensi hanya untuk hari yang memiliki efisiensi
            eff = bm.steam_efficiency_percent if bm else None
            if eff is not None and eff > 0:
                efficiencies.append(eff)

            pm = plant_metrics.get(target_date)
            if pm and pm.average_availability:
                availabilities.append(pm.average_availability)

            if i == 1:
                if pm and pm.average_availability:
                    yesterday_availability = pm.average_availability
                if eff is not None and eff > 0:
                    yesterday_efficiency = eff

            series.append({
                "day": target_date.strftime("%d %b"),
                "pemakaian": round(usage, 1)
            })
            total += usage

    else:
        for i in range(num_days - 1, 0, -1):
            target_date = logical_today - timedelta(days=i)
            metric_plant = DailyPlantMetric.objects.filter(date=target_date).first()
            if not metric_plant:
                date_str = target_date.strftime('%Y-%m-%d')
                try:
                    summary = _compute_daily_summary_data(date_str)
                    metric_plant = DailyPlantMetric.objects.create(
                        date=target_date,
                        total_steam_usage=summary.get('total_steam_usage', 0.0),
                        average_availability=summary.get('availability_summary', {}).get('average', 0.0),
                        productivity_goal=0.0
                    )
                except Exception:
                    metric_plant = None

            if i == 1 and metric_plant:
                yesterday_availability = metric_plant.average_availability or 0.0

            metric_boiler = BoilerDailyMetric.objects.filter(date=target_date).first()
            if not metric_boiler:
                try:
                    upsert_boiler_daily_metric(target_date)
                    metric_boiler = BoilerDailyMetric.objects.filter(date=target_date).first()
                except Exception:
                    pass

            usage = metric_boiler.total_steam_usage_kg if metric_boiler else 0.0
            eff = metric_boiler.steam_efficiency_percent if metric_boiler else None
            if eff is not None and eff > 0:
                efficiencies.append(eff)
            if i == 1 and eff is not None and eff > 0:
                yesterday_efficiency = eff

            series.append({
                'day': target_date.strftime('%d %b'),
                'pemakaian': round(usage, 1)
            })
            total += usage

    # Ambil hari ini (live) murni dari Boiler Report API
    today_usage = 0.0
    has_error_today = False

    try:
        from monitoring.api_report import _compute_boiler_chart_data, _compute_boiler_kpi_summary
        from monitoring.models import GlobalSettings
        from datetime import datetime

        settings = GlobalSettings.load()
        start_time = timezone.make_aware(datetime.combine(logical_today, datetime.min.time()).replace(hour=6, minute=0, second=0))
        end_time = start_time + timedelta(days=1)
        _, c_data, p_dist = _compute_boiler_chart_data(start_time, end_time, settings)
        kpi = _compute_boiler_kpi_summary(c_data, p_dist, settings)
        today_usage = kpi['total_steam_usage_kg']
    except Exception as e:
        has_error_today = True
        print("Error live boiler today:", e)

    series.append({
        "day": "Hari Ini",
        "pemakaian": round(today_usage, 1)
    })
    total += today_usage

    # Rata-rata availability dan efisiensi: hanya membagi hari-hari yang memiliki data
    avg_avail = round(sum(availabilities) / len(availabilities), 1) if availabilities else round(yesterday_availability, 1)
    avg_eff = round(sum(efficiencies) / len(efficiencies), 1) if efficiencies else round(yesterday_efficiency, 1)

    res_payload = {
        "days": num_days,
        "series": series,
        "total": round(total, 1),
        "yesterday_availability": round(yesterday_availability, 1),
        "yesterday_efficiency": round(yesterday_efficiency, 1),
        "avg_availability": avg_avail,
        "avg_efficiency": avg_eff,
        # Alias untuk kompatibilitas ke belakang
        "yesterday_productivity": round(yesterday_efficiency, 1),
        "avg_productivity": avg_eff,
    }
    if not has_error_today:
        cache.set(cache_key, res_payload, 300 if num_days > 7 else 60)
    return res_payload

# Grup yang ditampilkan di "Jumlah Proses Per Mesin" (urutan tampilan)
PROCESS_COUNT_GROUP_NAMES = [
    "Jet Dyeing Gedung Processing",
    "Jet Relax Gedung Processing",
    "Mesin Jet Gedung Printing",
]

def is_boiler_hto_group(machine):
    """True jika mesin termasuk grup Mesin Boiler HTO dan Uap (MC_BOILER)."""
    if not machine.group:
        return False
    if machine.group.code == "MC_BOILER":
        return True
    name = (machine.group.name or "").strip().lower()
    return name == "mesin boiler hto dan uap"

@dashboard_router.get("/daily-processes")
def daily_processes_api(request, days: int = 1):
    from django.core.cache import cache
    cache_key = f"dashboard_daily_processes_v3_{days}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val

    now = timezone.localtime()
    if days > 1:
        start_time = now - timedelta(days=days)
        end_time = now
        date_range_str = f"{start_time.strftime('%d %b %Y')} - {end_time.strftime('%d %b %Y')}"
    else:
        end_time = now.replace(hour=6, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=1)
        date_range_str = f"{start_time.strftime('%d %b %H:%M')} - {end_time.strftime('%d %b %H:%M')}"

    # Hanya 3 grup jet yang relevan untuk hitungan proses dashboard
    from django.db.models import Count
    from collections import defaultdict
    processes_qs = DyeingProcess.objects.filter(
        start_time__gte=start_time,
        start_time__lte=end_time,
        is_valid_process=True,
        machine__group__name__in=PROCESS_COUNT_GROUP_NAMES,
    )

    counts_qs = processes_qs.values('machine_id').annotate(cnt=Count('id'))
    process_counts = {item['machine_id']: item['cnt'] for item in counts_qs}
    total_processes = sum(process_counts.values())

    # Hitung tanggal-tanggal operasional aktif per mesin (jam operasional pabrik 06:00 - 06:00)
    machine_active_dates = defaultdict(set)
    if days > 1:
        for p in processes_qs.values('machine_id', 'start_time'):
            dt = timezone.localtime(p['start_time'])
            log_date = (dt - timedelta(hours=6)).date()
            machine_active_dates[p['machine_id']].add(log_date)

    groups = (
        MachineGroup.objects
        .filter(name__in=PROCESS_COUNT_GROUP_NAMES, machine__is_active=True)
        .distinct()
    )
    groups_by_name = {g.name: g for g in groups}
    ordered_groups = [groups_by_name[n] for n in PROCESS_COUNT_GROUP_NAMES if n in groups_by_name]

    groups_data = []

    for group in ordered_groups:
        machines = Machine.objects.filter(group=group, is_active=True).order_by('name')
        if not machines.exists():
            continue

        group_processes = 0
        machines_data = []
        for m in machines:
            count = process_counts.get(m.id, 0)
            group_processes += count
            act_days = len(machine_active_dates.get(m.id, set()))
            # Rata-rata harian hanya membagi hari-hari yang memiliki batch (hari tanpa batch diabaikan dari pembagi)
            if days > 1:
                avg_val = round(count / float(act_days), 1) if act_days > 0 else 0.0
            else:
                avg_val = count

            machines_data.append({
                "id": m.id,
                "name": m.name,
                "process_count": count,
                "active_days": act_days,
                "avg_per_day": avg_val,
            })

        sort_machines_custom(machines_data, name_key="name")

        groups_data.append({
            "group_name": group.name,
            "machine_count": machines.count(),
            "total_group_processes": group_processes,
            "machines": machines_data
        })

    res = {
        "days": days,
        "date_range": date_range_str,
        "total_processes_today": total_processes,
        "groups": groups_data
    }
    cache.set(cache_key, res, 300 if days > 1 else 60)
    return res

@dashboard_router.get("/process-summary-30d")
def get_process_summary_30d(request):
    from django.core.cache import cache
    cached = cache.get("dashboard_process_summary_30d_v2")
    if cached is not None:
        return cached

    now = timezone.localtime()
    start_30d = now - timedelta(days=30)

    # 1. DyeingProcess aggregations
    from django.db.models import Count
    from collections import defaultdict
    processes_qs = DyeingProcess.objects.filter(
        start_time__gte=start_30d,
        is_valid_process=True
    )
    total_processes = processes_qs.count()
    completed_processes = processes_qs.filter(is_complete=True).count()

    # Top 5 most active machines in last 30d
    top_machines_qs = (
        processes_qs
        .filter(machine__isnull=False)
        .values('machine__id', 'machine__name', 'machine__group__code')
        .annotate(total_batch=Count('id'))
        .order_by('-total_batch')[:5]
    )

    # Hitung tanggal operasional aktif untuk top machines
    top_machine_ids = [item['machine__id'] for item in top_machines_qs]
    top_active_dates = defaultdict(set)
    if top_machine_ids:
        for p in processes_qs.filter(machine_id__in=top_machine_ids).values('machine_id', 'start_time'):
            dt = timezone.localtime(p['start_time'])
            log_date = (dt - timedelta(hours=6)).date()
            top_active_dates[p['machine_id']].add(log_date)

    top_machines = []
    for item in top_machines_qs:
        m_id = item['machine__id']
        total_b = item['total_batch']
        act_d = len(top_active_dates.get(m_id, set()))
        avg_val = round(total_b / float(act_d), 1) if act_d > 0 else 0.0
        top_machines.append({
            "id": m_id,
            "name": item['machine__name'],
            "group": item['machine__group__code'] or '-',
            "batches": total_b,
            "active_days": act_d,
            "avg_per_day": avg_val,
        })

    # Average effective duration
    durations = [
        p.duration_effective for p in processes_qs.filter(duration_effective__isnull=False)
        if isinstance(p.duration_effective, (int, float)) and p.duration_effective > 0
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    # 2. Anomalies in last 30 days
    from monitoring.models import DataAnomaly
    anomalies_qs = DataAnomaly.objects.filter(created_at__gte=start_30d)
    total_anomalies = anomalies_qs.count()
    unresolved_anomalies = anomalies_qs.filter(is_resolved=False).count()

    flag_counts = {}
    for anom in anomalies_qs.only('details'):
        flags = anom.details.get('flags', []) if isinstance(anom.details, dict) else []
        for f in flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    sorted_flags = sorted(flag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_flag_list = [{"flag": k, "count": v} for k, v in sorted_flags]

    res = {
        "period_days": 30,
        "date_range": f"{start_30d.strftime('%d %b %Y')} - {now.strftime('%d %b %Y')}",
        "total_processes": total_processes,
        "completed_processes": completed_processes,
        "avg_duration_minutes": avg_duration,
        "top_machines": top_machines,
        "total_anomalies": total_anomalies,
        "unresolved_anomalies": unresolved_anomalies,
        "top_anomalies": top_flag_list,
    }
    cache.set("dashboard_process_summary_30d_v2", res, 300)
    return res

@dashboard_router.get("/active-machines")

def get_active_machines(request):

    machines = list(Machine.objects.filter(is_active=True).select_related("group"))

    # Pre-fetch active batches untuk efisiensi

    active_batches = {dp.machine_id: dp for dp in DyeingProcess.objects.filter(is_complete=False)}

    total_active = 0

    group_stats = {} # Untuk Pie 1 (Active) — legacy

    off_cool_stats = {"Cooling": 0, "Off": 0} # Untuk Pie 2 — legacy

    active_steam_ids = set()

    active_hto_ids = set()

    active_heat = 0

    active_keep = 0

    active_running = 0

    cool_off_steam_ids = set()

    cool_off_hto_ids = set()

    cool_off_cooling = 0

    cool_off_off = 0

    table_data = []

    for m in machines:

        status = get_machine_status_logic(m)

        steam = m.average_steam_usage or 0.0

        hto = m.avg_hto_calories or 0.0

        has_steam = steam > 0

        has_hto = hto > 0

        # Sensor boiler HTO/uap tidak dihitung sebagai "mesin aktif" produksi

        if is_boiler_hto_group(m):

            continue

        # Anggap mesin aktif jika Heat, Steady, Running, Cool

        if status in ["HEAT", "STEADY", "Running", "COOL"]:

            total_active += 1

            # Determine start_time

            active_batch = active_batches.get(m.id)

            start_time_str = ""

            start_time_iso = None

            if active_batch:

                local_start = timezone.localtime(active_batch.start_time)

                start_time_str = local_start.strftime("%H:%M")

                start_time_iso = local_start.isoformat()

            elif m.status_changed_at:

                local_start = timezone.localtime(m.status_changed_at)

                start_time_str = local_start.strftime("%H:%M")

                start_time_iso = local_start.isoformat()

            table_data.append({

                "id": m.id,

                "name": m.name,

                "group_name": m.group.code if m.group else "Lainnya",

                "temperature": m.temperature,

                "gradient": m.temperature_gradient,

                "status": status,

                "steam": steam,

                "hto": hto,

                "start_time": start_time_str,

                "start_time_iso": start_time_iso,

            })

        # Kartu A: Steam & HTO Aktif (HEAT / STEADY / Running)

        from monitoring.utils.steam_active import is_steam_active_from_machine

        if is_steam_active_from_machine(m):

            if has_steam:

                active_steam_ids.add(m.id)

                grp = m.group.code if m.group else "Lainnya"

                group_stats[grp] = group_stats.get(grp, 0) + 1

            if has_hto:

                active_hto_ids.add(m.id)

            if has_steam or has_hto:

                if status == "HEAT":

                    active_heat += 1

                elif status == "STEADY":

                    active_keep += 1

                else:

                    active_running += 1

        # Kartu B: Steam & HTO Cooling & Off

        if status in ["COOL", "Stop", "OFF", "Offline"]:

            if has_steam:

                cool_off_steam_ids.add(m.id)

            if has_hto:

                cool_off_hto_ids.add(m.id)

            if has_steam or has_hto:

                if status == "COOL":

                    cool_off_cooling += 1

                else:

                    cool_off_off += 1

            # Legacy pie_2: hanya yang masih pakai steam

            if has_steam:

                if status == "COOL":

                    off_cool_stats["Cooling"] += 1

                else:

                    off_cool_stats["Off"] += 1

    pie_1 = [{"name": k, "value": v} for k, v in group_stats.items()]

    pie_2 = [{"name": k, "value": v} for k, v in off_cool_stats.items() if v > 0]

    cooling_off_count = sum(off_cool_stats.values())

    energy_active = {

        "total": len(active_steam_ids | active_hto_ids),

        "steam": len(active_steam_ids),

        "hto": len(active_hto_ids),

        "heat": active_heat,

        "keep": active_keep,

        "running": active_running,

    }

    energy_cooling_off = {

        "total": len(cool_off_steam_ids | cool_off_hto_ids),

        "steam": len(cool_off_steam_ids),

        "hto": len(cool_off_hto_ids),

        "cooling": cool_off_cooling,

        "off": cool_off_off,

    }

    # Calculate steam for pie 2

    cooling_off_steam = 0.0

    # Build status_heatmap_groups

    status_groups_dict = {}

    for m in machines:

        status = get_machine_status_logic(m)

        steam = m.average_steam_usage or 0.0

        from monitoring.utils.steam_active import is_steam_active_from_machine

        # Mesin masuk kategori pendinginan uap jika tidak aktif uap tapi punya steam

        if not is_steam_active_from_machine(m) and steam > 0 and status != "RUNNING":

            cooling_off_steam += steam

        # Group logic for heatmap (exclude MC_BOILER)

        if m.group and m.group.code == 'MC_BOILER':

            continue

        grp_name = m.group.code if m.group else "Lainnya"

        if grp_name not in status_groups_dict:

            status_groups_dict[grp_name] = {"group_name": grp_name, "machines": []}

        norm_status = normalize_heatmap_status(status)

        since_info = get_status_since_info(m, active_batches.get(m.id))

        status_groups_dict[grp_name]["machines"].append({

            "id": m.id,

            "name": m.name,

            "status": norm_status,

            "operation_mode": m.operation_mode,

            "can_toggle": m.operation_mode == "MANUAL",

            "active_since": since_info.get("active_since"),

            "status_since": since_info.get("status_since"),

            "status_since_display": since_info.get("status_since_display"),

            "duration_minutes": since_info.get("duration_minutes"),

        })

    status_heatmap_groups = list(status_groups_dict.values())

    status_heatmap_groups.sort(key=lambda x: x["group_name"])

    for g in status_heatmap_groups:

        sort_machines_custom(g["machines"], name_key="name")

    if not pie_1:

        pie_1 = [{"name": "Tidak Ada", "value": 1}]

    if not pie_2:

        pie_2 = [{"name": "Tidak Ada", "value": 1}]

    # Sort table_data using the custom sort logic so that groupedActiveMachines in frontend is sorted

    sort_machines_custom(table_data, name_key="name")

    return {

        "total_active": total_active,

        "pie_1": pie_1,

        "pie_2": pie_2,

        "table_data": table_data,

        "cooling_off_count": cooling_off_count,

        "cooling_off_steam": round(cooling_off_steam, 1),

        "energy_active": energy_active,

        "energy_cooling_off": energy_cooling_off,

        "status_heatmap_groups": status_heatmap_groups

    }

@dashboard_router.get("/recent-history")

def get_recent_history(request):

    machines = Machine.objects.filter(

        is_active=True,

        status_changed_at__isnull=False

    ).order_by('-status_changed_at')[:20]

    data = []

    for m in machines:

        status = get_machine_status_logic(m)

        local_time = timezone.localtime(m.status_changed_at)

        data.append({

            "id": m.id,

            "name": m.name,

            "time": local_time.strftime("%H:%M"),

            "status": status,

        })

    return data

@dashboard_router.get("/machine/{machine_id}/detail")

def get_machine_detail(request, machine_id: str, hours: int = None):

    if str(machine_id).isdigit():

        machine = get_object_or_404(Machine, id=int(machine_id))

    else:

        machine = get_object_or_404(Machine, code=str(machine_id))

    is_manual = machine.operation_mode == "MANUAL"

    active_batch = DyeingProcess.objects.filter(machine=machine, is_complete=False).order_by('-start_time').first()

    now = timezone.localtime()

    if hours and hours > 0:

        chart_start_time = now - timedelta(hours=hours)

    else:

        # Default: Mulai dari Real Heat jika batch aktif

        if active_batch and active_batch.heating_start_time:

            chart_start_time = active_batch.heating_start_time

        elif active_batch and active_batch.start_time:

            chart_start_time = active_batch.start_time

        else:

            chart_start_time = now - timedelta(hours=2)

    # Ambil log mesin ini

    machine_logs = MachineMinuteLog.objects.filter(

        machine=machine, timestamp__gte=chart_start_time

    ).order_by('timestamp')

    # Deteksi profil energi mesin: Steam vs HTO

    has_steam = (machine.average_steam_usage or 0) > 0

    has_hto = (machine.avg_hto_calories or 0) > 0

    if has_hto and not has_steam:

        energy_type = "hto"

    elif has_steam:

        energy_type = "steam"

    elif "HTO" in machine.code or "HTO" in (machine.name or "") or (machine.group and machine.group.code in ("PRT CNT", "PRC CNT")):

        energy_type = "hto"

    else:

        energy_type = "steam"

    # Ambil log pressure dari mesin Steam_Pr

    steam_logs = MachineMinuteLog.objects.filter(

        machine__code='Steam_Pr', timestamp__gte=chart_start_time

    ).order_by('timestamp')

    # Ambil log suhu dari mesin Oil_Temp (Suhu Sirkulasi HTO)

    hto_logs = MachineMinuteLog.objects.filter(

        machine__code='Oil_Temp', timestamp__gte=chart_start_time

    ).order_by('timestamp')

    # Ambil count mesin aktif (hanya yang HEAT/STEADY/Running dan pakai uap)

    active_counts = MachineMinuteLog.objects.filter(

        timestamp__gte=chart_start_time,

        machine__average_steam_usage__gt=0

    ).filter(

        Q(thermal_state="HEAT") | Q(thermal_state="STEADY", temperature__gte=90.0) | Q(last_status="Running")

    ).values('timestamp').annotate(active_count=Count('machine', distinct=True))

    # Gabungkan ke dalam dictionary berdasarkan datetime (menit),

    # bukan string HH:mm — agar sort tetap kronologis lintas tengah malam.

    timeline = {}

    def get_dt_key(ts):

        t = timezone.localtime(ts)

        return t.replace(second=0, microsecond=0)

    for log in machine_logs:

        dt_key = get_dt_key(log.timestamp)

        is_on = 1 if log.last_status == "Running" else 0

        timeline[dt_key] = {

            "temp": round(log.temperature, 1) if log.temperature else 0,

            "pressure": 0,

            "hto_temp": 0,

            "active_count": 0,

            "is_on": is_on,

        }

    for log in steam_logs:

        dt_key = get_dt_key(log.timestamp)

        if dt_key not in timeline:

            timeline[dt_key] = {"temp": 0, "pressure": 0, "hto_temp": 0, "active_count": 0, "is_on": 0}

        timeline[dt_key]["pressure"] = round(log.temperature, 2) if log.temperature else 0

    for log in hto_logs:

        dt_key = get_dt_key(log.timestamp)

        if dt_key not in timeline:

            timeline[dt_key] = {"temp": 0, "pressure": 0, "hto_temp": 0, "active_count": 0, "is_on": 0}

        timeline[dt_key]["hto_temp"] = round(log.temperature, 1) if log.temperature else 0

    for ac in active_counts:

        dt_key = get_dt_key(ac['timestamp'])

        if dt_key not in timeline:

            timeline[dt_key] = {"temp": 0, "pressure": 0, "hto_temp": 0, "active_count": 0, "is_on": 0}

        timeline[dt_key]["active_count"] = ac['active_count']

    # Urutkan berdasarkan datetime, lalu format HH:mm untuk label chart

    chart_data = [

        {

            "time": dt_key.strftime("%H:%M"),

            "temp": val["temp"],

            "pressure": val["pressure"],

            "hto_temp": val["hto_temp"],

            "active_count": val["active_count"],

            "is_on": val["is_on"],

        }

        for dt_key, val in sorted(timeline.items())

    ]

    # Kalkulasi durasi manual jika batch sedang jalan tapi belum selesai

    duration = None

    if active_batch:

        if active_batch.end_time:

            duration = (active_batch.end_time - active_batch.start_time).total_seconds() / 60.0

        else:

            duration = (timezone.now() - active_batch.start_time).total_seconds() / 60.0

    since_info = get_status_since_info(machine, active_batch)

    return {

        "energy_type": energy_type,

        "secondary_metric": {

            "type": energy_type,

            "name": "Suhu Sirkulasi HTO (Oil_Temp)" if energy_type == "hto" else "Tekanan Uap (Steam_Pr)",

            "unit": "°C" if energy_type == "hto" else "bar",

            "key": "hto_temp" if energy_type == "hto" else "pressure",

        },

        "machine": {

            "id": machine.id,

            "name": machine.name,

            "group": machine.group.name if machine.group else "-",

            "mode": machine.operation_mode,

            "is_manual": is_manual,

            "can_toggle": is_manual,

            "status": get_machine_status_logic(machine),

            "current_temp": round(machine.temperature, 1) if machine.temperature else 0,

            "gradient": machine.temperature_gradient,

            "steam_usage": machine.average_steam_usage,

            "hto_usage": machine.avg_hto_calories or 0.0,

            "active_since": since_info.get("active_since"),

            "status_since": since_info.get("status_since"),

            "status_since_display": since_info.get("status_since_display"),

            "duration_minutes": since_info.get("duration_minutes"),

        },

        "batch": {

            "is_active": bool(active_batch),

            "batch_number": active_batch.batch_number if active_batch else None,

            "start_time": timezone.localtime(active_batch.start_time).strftime("%d %b %Y %H:%M") if active_batch else None,

            "duration": round(duration, 1) if duration is not None else None

        },

        "chart_data": chart_data

    }

@dashboard_router.get("/running-summary")

def get_running_summary(request):

    from monitoring.utils.steam_active import is_steam_active_from_machine

    CONTINUOUS_PRT = "PRT CNT"   # Continous Gedung Printing

    CONTINUOUS_PRC = "PRC CNT"   # Continous Gedung Processing

    JD_PRC_CODE    = "JD PRC"    # Jet Dyeing Processing

    JD_PRT_CODE    = "JET PRT"   # Jet Printing / ZET

    JR_PRC_CODE    = "JR PRC"    # Jet Relax Processing

    ALL_CODES = {CONTINUOUS_PRT, CONTINUOUS_PRC, JD_PRC_CODE, JD_PRT_CODE, JR_PRC_CODE}

    machines = Machine.objects.filter(

        is_active=True,

        group__code__in=ALL_CODES

    ).select_related("group")

    # Inisialisasi counter per grup x sumber energi

    summary = {

        "steam_cont":  {"running": 0, "total": 0},

        "steam_jd_jr": {"running": 0, "total": 0},

        "hto_prc":     {"running": 0, "total": 0},

        "hto_prt":     {"running": 0, "total": 0},

    }

    for m in machines:

        code = m.group.code

        is_running = is_steam_active_from_machine(m)

        has_steam  = (m.average_steam_usage or 0) > 0

        has_hto    = (m.avg_hto_calories or 0) > 0

        # 1. Baris Steam - Continous (PRT CNT + PRC CNT)

        if code in {CONTINUOUS_PRT, CONTINUOUS_PRC} and has_steam:

            summary["steam_cont"]["total"] += 1

            if is_running:

                summary["steam_cont"]["running"] += 1

        # 2. Baris Steam - JD + JR

        if code in {JD_PRC_CODE, JD_PRT_CODE, JR_PRC_CODE} and has_steam:

            summary["steam_jd_jr"]["total"] += 1

            if is_running:

                summary["steam_jd_jr"]["running"] += 1

        # 3. Baris HTO - Continous Processing (PRC CNT)

        if code == CONTINUOUS_PRC and has_hto:

            summary["hto_prc"]["total"] += 1

            if is_running:

                summary["hto_prc"]["running"] += 1

        # 4. Baris HTO - Continous Printing (PRT CNT)

        if code == CONTINUOUS_PRT and has_hto:

            summary["hto_prt"]["total"] += 1

            if is_running:

                summary["hto_prt"]["running"] += 1

    return {

        "steam": {

            "continuous": summary["steam_cont"],

            "jd_jr":      summary["steam_jd_jr"],

        },

        "hto": {

            "processing": summary["hto_prc"],

            "printing":   summary["hto_prt"],

        },

    }

@dashboard_router.get("/energy-condition")

def get_energy_condition(request):

    try:

        boiler_group = MachineGroup.objects.filter(code='MC_BOILER').first()

        if not boiler_group:

            boiler_group = MachineGroup.objects.filter(name__icontains='Boiler').first()

        if not boiler_group:

            return {"data": []}

        machines = Machine.objects.filter(group=boiler_group, is_active=True).order_by('id')

        now = timezone.now()

        start_time = now - timedelta(hours=1)

        energy_data = []

        for m in machines:

            unit_val = m.unit if m.unit else ""

            unit_display = ""

            if unit_val == "C":

                unit_display = "°C"

            elif unit_val == "BAR":

                unit_display = "Bar"

            elif unit_val == "HZ":

                unit_display = "Hz"

            elif unit_val == "V":

                unit_display = "V"

            elif unit_val == "A":

                unit_display = "A"

            elif unit_val == "KW":

                unit_display = "kW"

            else:

                unit_display = unit_val

            logs = list(MachineMinuteLog.objects.filter(

                machine=m,

                timestamp__gte=start_time

            ).order_by('timestamp'))

            valid_temps = [log.temperature for log in logs if log.temperature is not None]

            avg_1h = sum(valid_temps) / len(valid_temps) if valid_temps else (m.temperature or 0)

            energy_data.append({

                "id": m.id,

                "name": m.name,

                "value": round(m.temperature, 2) if m.temperature else 0,

                "unit": unit_display,

                "average_1h": round(avg_1h, 2)

            })

        return {"data": energy_data}

    except Exception as e:

        raise HttpError(500, f"Error computing energy condition: {str(e)}")

@dashboard_router.get("/machine/{machine_id}/daily-chart")

def get_machine_daily_chart(request, machine_id: int):

    machine = get_object_or_404(Machine, id=machine_id)

    now = timezone.localtime()

    end_time = now.replace(hour=6, minute=0, second=0, microsecond=0)

    start_time = end_time - timedelta(days=1)

    machine_logs = MachineMinuteLog.objects.filter(

        machine=machine, timestamp__gte=start_time, timestamp__lt=end_time

    ).order_by('timestamp')

    steam_logs = MachineMinuteLog.objects.filter(

        machine__code='Steam_Pr', timestamp__gte=start_time, timestamp__lt=end_time

    ).order_by('timestamp')

    # Downsampling: 1 data per 10 menit

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

            "pressure": round(val["pressure"], 2)

        })

    return {

        "machine_name": machine.name,

        "date_range": f"{start_time.strftime('%d %b %H:%M')} - {end_time.strftime('%d %b %H:%M')}",

        "chart_data": chart_data

    }

@dashboard_router.get("/executive-overview")

def get_executive_overview(request):

    """

    Agregator Executive Overview untuk Executive Command Center (/dashboard-1).

    Merangkum data KPI lintas-modul (Anomali, Boiler Health, Engineering issues,

    Dyeing Identity hygiene, dan Shift summary).

    """

    from django.core.cache import cache

    cached = cache.get("dashboard_executive_overview_v1")

    if cached:

        return cached

    now = timezone.localtime()

    logical_now = now - timedelta(hours=6)

    logical_today = logical_now.date()

    start_today = timezone.make_aware(datetime.combine(logical_today, datetime.min.time()).replace(hour=6, minute=0, second=0))

    end_today = start_today + timedelta(days=1)

    from monitoring.models import DataAnomaly, EngineerIssue, FieldInspection, SparePart, DyeingProcess

    unresolved_anomalies_qs = DataAnomaly.objects.filter(is_resolved=False).select_related(

        'identity_record__machine', 'identity_record__program', 'process_record'

    ).order_by('-created_at')

    total_unresolved = unresolved_anomalies_qs.count()

    top_anomalies = []

    for a in unresolved_anomalies_qs[:5]:

        machine_code = a.identity_record.machine.code if a.identity_record and a.identity_record.machine else (

            a.process_record.machine.code if a.process_record and a.process_record.machine else '-'

        )

        batch_number = a.process_record.batch_number if a.process_record else '-'

        program_name = a.identity_record.program.nama if a.identity_record and a.identity_record.program else '-'

        artikel_kain = a.identity_record.artikel_kain if a.identity_record else '-'

        flags = a.details.get("flags", []) if isinstance(a.details, dict) else []

        top_anomalies.append({

            "id": a.id,

            "machine_code": machine_code,

            "batch_number": batch_number,

            "program_name": program_name,

            "artikel_kain": artikel_kain,

            "anomaly_types": flags if flags else [a.anomaly_type],

            "created_at": a.created_at.isoformat() if a.created_at else None,

            "details": a.details or {},

        })

    open_issues = EngineerIssue.objects.filter(status__in=['OPEN', 'IN_PROGRESS', 'WAITING_PARTS']).count()

    critical_issues = EngineerIssue.objects.filter(status__in=['OPEN', 'IN_PROGRESS', 'WAITING_PARTS'], priority='CRITICAL').count()

    pending_inspections = FieldInspection.objects.filter(status='DRAFT').count()

    low_stock_parts = SparePart.objects.filter(is_active=True, stock_quantity__lte=F('min_stock')).count()

    today_processes = DyeingProcess.objects.filter(start_time__gte=start_today, start_time__lt=end_today)

    total_processes_today = today_processes.count()

    completed_processes_today = today_processes.filter(is_complete=True).count()

    missing_identity_count = 0

    for p in today_processes.filter(is_complete=True).select_related('identity'):

        ident = getattr(p, 'identity', None)

        if not ident or not ident.nomor_order or not ident.artikel_kain:

            missing_identity_count += 1

    payload = {

        "date": logical_today.isoformat(),

        "total_processes_today": total_processes_today,

        "completed_processes_today": completed_processes_today,

        "anomalies": {

            "total_unresolved": total_unresolved,

            "top_anomalies": top_anomalies,

        },

        "engineering": {

            "open_issues": open_issues,

            "critical_issues": critical_issues,

            "pending_inspections": pending_inspections,

            "low_stock_parts": low_stock_parts,

        },

        "data_hygiene": {

            "missing_identities": missing_identity_count,

        }

    }

    cache.set("dashboard_executive_overview_v1", payload, 30)

    return payload

@dashboard_router.get("/fleet-health-waste")
def get_fleet_health_waste(request, window: str = "7D"):
    from django.core.cache import cache
    from monitoring.utils.machine_fleet_summary import compute_machine_fleet_summary

    win = (window or "7D").upper()
    if win not in ("1D", "7D", "30D"):
        win = "7D"

    now = timezone.localtime()
    logical_today = (now - timedelta(hours=6)).date()
    date_str = logical_today.isoformat()

    cache_key = f"dashboard_fleet_health_waste_v1_{win}_{date_str}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    raw = compute_machine_fleet_summary(date_str, win)
    tariffs = raw.get("tariffs") or {}
    steam_rate = float(tariffs.get("steam_cost_per_kg") or 350.0)
    elec_rate = float(tariffs.get("electricity_base_rate") or 1035.8)

    enriched_machines = []
    for m in raw.get("machines", []):
        batches = m.get("recent_batches") or []
        n_b = len(batches)
        if n_b > 0:
            avg_heat_act = round(sum((b.get("heat_mins") or 0) for b in batches) / n_b, 1)
            avg_heat_idl = round(sum((b.get("ideal_heat") or 0) for b in batches) / n_b, 1)
            avg_keep_act = round(sum((b.get("steady_mins") or 0) for b in batches) / n_b, 1)
            avg_keep_idl = round(sum((b.get("ideal_steady") or 0) for b in batches) / n_b, 1)
            avg_cool_act = round(sum((b.get("cool_mins") or 0) for b in batches) / n_b, 1)
            avg_cool_idl = round(sum((b.get("ideal_cool") or 0) for b in batches) / n_b, 1)
            avg_tot_act = round(sum((b.get("total_mins") or 0) for b in batches) / n_b, 1)
            avg_tot_idl = round(sum((b.get("ideal_total") or 0) for b in batches) / n_b, 1)
        else:
            avg_heat_act = avg_heat_idl = avg_keep_act = avg_keep_idl = avg_cool_act = avg_cool_idl = avg_tot_act = avg_tot_idl = 0.0

        waste_steam_kg = float(m.get("waste_steam_kg") or 0.0)
        waste_power_kwh = float(m.get("waste_power_kwh") or 0.0)
        proj_steam_kg = float(m.get("projected_30d_steam_kg") or 0.0)
        proj_power_kwh = float(m.get("projected_30d_power_kwh") or 0.0)
        nom_kw = float(m.get("nominal_power_kw") or 15.0)

        slim_batches = []
        for b in batches[:10]:
            b_heat_del = max(0.0, float(b.get("delta_heat") or 0.0))
            b_keep_del = max(0.0, float(b.get("delta_steady") or 0.0))
            b_cool_del = max(0.0, float(b.get("delta_cool") or 0.0))
            b_excess_hrs = (b_heat_del + b_keep_del + b_cool_del) / 60.0
            b_power_kwh = round(b_excess_hrs * nom_kw, 1)
            slim_batches.append({
                "id": b.get("id"),
                "batch_number": b.get("batch_number"),
                "program_name": b.get("program_name"),
                "date_str": b.get("date_str"),
                "time_str": b.get("time_str"),
                "heat_mins": b.get("heat_mins"),
                "ideal_heat": b.get("ideal_heat"),
                "delta_heat": b.get("delta_heat"),
                "steady_mins": b.get("steady_mins"),
                "ideal_steady": b.get("ideal_steady"),
                "delta_steady": b.get("delta_steady"),
                "cool_mins": b.get("cool_mins"),
                "ideal_cool": b.get("ideal_cool"),
                "delta_cool": b.get("delta_cool"),
                "total_mins": b.get("total_mins"),
                "ideal_total": b.get("ideal_total"),
                "eff": b.get("eff"),
                "max_temp": b.get("max_temp"),
                "waste_steam_kg": round(float(b.get("waste_steam_kg") or 0.0), 1),
                "waste_power_kwh": b_power_kwh,
                "waste_cost_rp": round(float(b.get("waste_cost_rp") or 0.0)),
            })

        enriched_machines.append({
            "machine_id": m.get("machine_id"),
            "machine_name": m.get("machine_name"),
            "machine_code": m.get("machine_code"),
            "group_name": m.get("group_name"),
            "group_code": m.get("group_code"),
            "nominal_power_kw": nom_kw,
            "evaluated_batches_count": m.get("evaluated_batches_count") or 0,
            "health_score": m.get("health_score") or 0,
            "health_grade": m.get("health_grade") or "B",
            "avg_delta_heat": round(float(m.get("avg_delta_heat") or 0.0), 1),
            "avg_delta_steady": round(float(m.get("avg_delta_steady") or 0.0), 1),
            "avg_delta_cool": round(float(m.get("avg_delta_cool") or 0.0), 1),
            "avg_heat_actual": avg_heat_act,
            "avg_heat_ideal": avg_heat_idl,
            "avg_keep_actual": avg_keep_act,
            "avg_keep_ideal": avg_keep_idl,
            "avg_cool_actual": avg_cool_act,
            "avg_cool_ideal": avg_cool_idl,
            "avg_total_actual": avg_tot_act,
            "avg_total_ideal": avg_tot_idl,
            "waste_steam_kg": round(waste_steam_kg, 1),
            "waste_steam_rp": round(waste_steam_kg * steam_rate),
            "waste_power_kwh": round(waste_power_kwh, 1),
            "waste_power_rp": round(waste_power_kwh * elec_rate),
            "waste_pump_hours": round(waste_power_kwh / max(nom_kw, 1.0), 1),
            "waste_cost_rp": round(float(m.get("waste_cost_rp") or 0.0)),
            "avg_waste_rp_batch": round(float(m.get("avg_waste_rp_batch") or 0.0)),
            "projected_30d_rp": round(float(m.get("projected_30d_rp") or 0.0)),
            "projected_30d_steam_kg": round(proj_steam_kg, 1),
            "projected_30d_steam_rp": round(proj_steam_kg * steam_rate),
            "projected_30d_power_kwh": round(proj_power_kwh, 1),
            "projected_30d_power_rp": round(proj_power_kwh * elec_rate),
            "primary_diagnosis": m.get("primary_diagnosis"),
            "programs": (m.get("programs") or [])[:6],
            "recent_batches": slim_batches,
        })

    result = {
        "date": raw.get("date"),
        "window": win,
        "date_range_label": raw.get("date_range_label"),
        "tariffs": tariffs,
        "fleet_kpi": raw.get("fleet_kpi"),
        "machines": enriched_machines,
    }
    cache.set(cache_key, result, 300)
    return result
