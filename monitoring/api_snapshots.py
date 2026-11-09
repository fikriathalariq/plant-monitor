from ninja import Router
from ninja.errors import HttpError
from datetime import datetime, timedelta
from collections import defaultdict
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models.functions import ExtractMinute

from monitoring.models import Machine, MachineGroup, MachineStatusSnapshot, MachineMinuteLog
from monitoring.decorators import user_can_access_page
from monitoring.utils.shift_time import (
    TOTAL_BUCKETS,
    current_shift_start,
    hour_axis_labels,
)
from monitoring.utils.steam_calc import (
    compute_steam_timeline_from_minute_buckets,
    is_steam_active_state,
)

snapshots_router = Router(tags=["Snapshots"])

PAGE_CODE = "snapshot_history"
BUCKET_MINUTES = 1


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


def _snap_to_state(snap_data, machine_code=None):
    if not snap_data:
        return "ERROR"
    if snap_data.get("mode") == "MANUAL":
        return "RUNNING" if snap_data.get("status") == "Running" else "OFF"
    detail = snap_data.get("detail", "")
    if detail in ("HEAT", "STEADY", "COOL", "FAULT", "OFFLINE"):
        return detail
    if snap_data.get("status") in ("-", "Unknown") or detail == "-":
        return "ERROR"
    return "OFF"


def _log_to_state(log, machine):
    """State timeline dari MachineMinuteLog (mendukung dict dan model instance)."""
    if not log:
        return "ERROR"
    last_status = log.get("last_status") if isinstance(log, dict) else getattr(log, "last_status", None)
    thermal = log.get("thermal_state") if isinstance(log, dict) else getattr(log, "thermal_state", None)
    if machine.operation_mode == "MANUAL":
        return "RUNNING" if last_status == "Running" else "OFF"
    thermal = thermal or ""
    if thermal in ("HEAT", "STEADY", "COOL", "FAULT", "OFFLINE"):
        return thermal
    if last_status in ("-", "Unknown") or thermal == "-":
        return "ERROR"
    return "OFF"


def _log_is_steam_active(log, machine):
    """Mesin dianggap memakai uap saat HEAT/STEADY (AUTO) atau Running (MANUAL)."""
    state = _log_to_state(log, machine)
    return is_steam_active_state(state, machine.operation_mode)


def _buckets_to_segments(buckets, max_bucket, is_completed_shift=False):
    """Konversi bucket menit → segmen berurutan dengan lebar persentase (relatif 24 jam penuh)."""
    segments = []
    current_state = None
    seg_start = 0
    effective_end = TOTAL_BUCKETS if is_completed_shift else max_bucket + 1

    for i in range(effective_end + 1):
        s = buckets.get(i, "OFF") if i < effective_end else None
        if s != current_state:
            if current_state is not None:
                segments.append({
                    "state": current_state,
                    "start_pct": round(seg_start / TOTAL_BUCKETS * 100, 4),
                    "width_pct": round((i - seg_start) / TOTAL_BUCKETS * 100, 4),
                })
            if s is not None:
                current_state = s
                seg_start = i

    # Koreksi floating point: pastikan total width_pct = 100% untuk shift selesai
    if segments and is_completed_shift:
        total_w = sum(s["width_pct"] for s in segments)
        if abs(total_w - 100.0) > 0.01:
            segments[-1]["width_pct"] = round(
                100.0 - sum(s["width_pct"] for s in segments[:-1]), 4
            )
    return segments


@snapshots_router.get("/meta")
def get_snapshot_meta(request):
    """Data untuk dropdown filter: groups, machines, dan rentang tanggal data tersedia."""
    _require_permission(request)

    all_groups = MachineGroup.objects.filter(machine__is_active=True).distinct().order_by("code")
    all_machines = Machine.objects.filter(is_active=True).order_by("group__code", "code")

    first_snapshot = MachineStatusSnapshot.objects.order_by("timestamp").first()
    last_snapshot = MachineStatusSnapshot.objects.order_by("-timestamp").first()

    return {
        "groups": [{"code": g.code, "name": g.name} for g in all_groups],
        "machines": [{"code": m.code, "name": m.name, "group": m.group.code if m.group else None} for m in all_machines],
        "first_snapshot_date": first_snapshot.timestamp.date().isoformat() if first_snapshot else None,
        "last_snapshot_date": last_snapshot.timestamp.date().isoformat() if last_snapshot else None,
        "interval_options": [1, 5, 15, 30, 60],
    }


@snapshots_router.get("/timeline")
def get_snapshot_timeline(
    request,
    date: str = None,
    page: int = None,
    groups: str = None,
    machines: str = None,
):
    """
    Timeline bar per mesin untuk satu shift 06:00–06:00.
    Parameter date (YYYY-MM-DD) = tanggal awal shift (jam 06:00 hari itu).
    Shift hari berjalan berakhir di waktu sekarang.
    """
    _require_permission(request)

    now = timezone.localtime()
    current_start = current_shift_start(now)

    if date:
        try:
            picked = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            picked = current_start.date()
    elif page and page > 1:
        picked = (current_start - timedelta(days=page - 1)).date()
    else:
        picked = current_start.date()

    shift_start = timezone.make_aware(
        datetime.combine(picked, datetime.min.time()).replace(hour=6, minute=0, second=0, microsecond=0)
    )
    full_end = shift_start + timedelta(days=1)

    is_current = shift_start == current_start
    if is_current:
        shift_end = now
    elif shift_start > current_start:
        shift_end = shift_start
    else:
        shift_end = full_end

    selected_group_codes = groups.split(",") if groups else []
    selected_machine_codes = machines.split(",") if machines else []

    machines_query = Machine.objects.filter(is_active=True).select_related("group")
    if selected_group_codes:
        machines_query = machines_query.filter(group__code__in=selected_group_codes)
    if selected_machine_codes:
        machines_query = machines_query.filter(code__in=selected_machine_codes)

    machine_list = list(machines_query.order_by("group__code", "code"))
    code_to_machine = {m.code: m for m in machine_list}

    if is_current:
        elapsed_seconds = (shift_end - shift_start).total_seconds()
        elapsed_minutes_float = elapsed_seconds / 60.0
        floor_elapsed = int(elapsed_minutes_float)
        max_bucket = min(floor_elapsed - 1, TOTAL_BUCKETS - 1)
    else:
        elapsed_minutes_float = float(TOTAL_BUCKETS)
        floor_elapsed = TOTAL_BUCKETS
        max_bucket = TOTAL_BUCKETS - 1

    machine_buckets = defaultdict(dict)
    steam_buckets = defaultdict(float)
    if machine_list:
        steam_usage_by_code = {
            m.code: float(m.average_steam_usage or 0)
            for m in Machine.objects.filter(
                is_active=True,
                average_steam_usage__gt=0,
                id__in=[m.id for m in machine_list],
            )
        }

        logs = MachineMinuteLog.objects.filter(
            machine_id__in=[m.id for m in machine_list],
            timestamp__gte=shift_start,
            timestamp__lt=shift_end,
        ).values("machine__code", "timestamp", "thermal_state", "last_status").order_by("timestamp")

        for log in logs:
            machine = code_to_machine.get(log["machine__code"])
            if not machine:
                continue
            time_diff = (timezone.localtime(log['timestamp']) - shift_start).total_seconds() / 60
            bucket_index = int(time_diff / BUCKET_MINUTES)
            if 0 <= bucket_index <= max_bucket:
                machine_buckets[machine.code][bucket_index] = _log_to_state(log, machine)
                usage = steam_usage_by_code.get(machine.code, 0)
                if usage and _log_is_steam_active(log, machine):
                    steam_buckets[bucket_index] += usage

    _data_end = TOTAL_BUCKETS if not is_current else max_bucket + 1
    steam_heatmap = compute_steam_timeline_from_minute_buckets(steam_buckets, _data_end)

    # Tekanan uap global (Steam_Pr) — tidak terpengaruh filter group/machine
    pressure_buckets = {}
    steam_pr_machine = Machine.objects.filter(code="Steam_Pr", is_active=True).first()
    if steam_pr_machine and max_bucket >= 0:
        pr_logs = MachineMinuteLog.objects.filter(
            machine=steam_pr_machine,
            timestamp__gte=shift_start,
            timestamp__lt=shift_end,
        ).values("timestamp", "temperature").order_by("timestamp")
        for log in pr_logs:
            log_ts = log["timestamp"] if isinstance(log, dict) else log.timestamp
            log_temp = log["temperature"] if isinstance(log, dict) else log.temperature
            time_diff = (timezone.localtime(log_ts) - shift_start).total_seconds() / 60
            bucket_index = int(time_diff / BUCKET_MINUTES)
            if 0 <= bucket_index <= max_bucket and log_temp is not None:
                pressure_buckets[bucket_index] = round(float(log_temp), 2)
    pressure_values = [pressure_buckets.get(i) for i in range(max(0, _data_end))]

    group_map = defaultdict(list)
    for machine in machine_list:
        segs = _buckets_to_segments(
            machine_buckets.get(machine.code, {}),
            max_bucket,
            is_completed_shift=not is_current
        )
        group_name = machine.group.name if machine.group else "Lain-lain"
        group_map[group_name].append({
            "code": machine.code,
            "name": machine.name,
            "segments": segs,
        })

    timeline_groups = [
        {"group_name": gname, "machines": machines_in_group}
        for gname, machines_in_group in sorted(group_map.items())
    ]

    first_snapshot = MachineStatusSnapshot.objects.order_by("timestamp").first()
    last_snapshot = MachineStatusSnapshot.objects.order_by("-timestamp").first()
    if first_snapshot:
        min_shift_date = current_shift_start(timezone.localtime(first_snapshot.timestamp)).date()
    else:
        min_shift_date = picked
    if last_snapshot:
        max_shift_date = current_shift_start(timezone.localtime(last_snapshot.timestamp)).date()
    else:
        max_shift_date = picked

    if is_current:
        shift_label = (
            f"{shift_start.strftime('%d %b %Y, %H:%M')} – sekarang ({now.strftime('%H:%M')})"
        )
    else:
        shift_label = (
            f"{shift_start.strftime('%d %b %Y, %H:%M')} – {full_end.strftime('%d %b %Y, %H:%M')}"
        )

    progress_pct = round(elapsed_minutes_float / TOTAL_BUCKETS * 100, 4) if is_current else 100.0

    return {
        "shift_date": picked.isoformat(),
        "min_shift_date": min_shift_date.isoformat(),
        "max_shift_date": max_shift_date.isoformat(),
        "is_current_shift": is_current,
        "shift_label": shift_label,
        "shift_start": shift_start.isoformat(),
        "shift_end": shift_end.isoformat(),
        "progress_pct": progress_pct,
        "elapsed_minutes": round(elapsed_minutes_float, 4),
        "time_labels": hour_axis_labels(),
        "steam_heatmap": steam_heatmap,
        "steam_pressure": {
            "values": pressure_values,
            "unit": "barg",
            "scale_min": 0,
            "scale_max": 6,
            "critical_low": 3.0,
        },
        "groups": timeline_groups,
    }


@snapshots_router.get("/history")
def get_snapshot_history(
    request,
    interval: int = 5,
    date_from: str = None,
    date_to: str = None,
    groups: str = None,
    machines: str = None,
    page: int = 1,
):
    """Porting dari monitoring.views.snapshot_history (pivot table)."""
    _require_permission(request)

    today = timezone.now().date()
    try:
        date_from_parsed = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else today
    except ValueError:
        date_from_parsed = today
    try:
        date_to_parsed = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else today
    except ValueError:
        date_to_parsed = today

    if not date_from and not date_to:
        start_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        end_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        today_count = MachineStatusSnapshot.objects.filter(timestamp__range=(start_today, end_today)).count()
        if today_count == 0:
            latest_snapshot = MachineStatusSnapshot.objects.order_by("-timestamp").first()
            if latest_snapshot:
                date_from_parsed = date_to_parsed = latest_snapshot.timestamp.date()

    selected_group_codes = groups.split(",") if groups else []
    selected_machine_codes = machines.split(",") if machines else []

    machines_query = Machine.objects.filter(is_active=True)
    if selected_group_codes:
        machines_query = machines_query.filter(group__code__in=selected_group_codes)
    if selected_machine_codes:
        machines_query = machines_query.filter(code__in=selected_machine_codes)

    machine_list = list(machines_query.order_by("group__code", "code"))

    start_datetime = timezone.make_aware(datetime.combine(date_from_parsed, datetime.min.time()))
    end_datetime = timezone.make_aware(datetime.combine(date_to_parsed, datetime.max.time()))

    snapshots_qs = MachineStatusSnapshot.objects.filter(
        timestamp__range=(start_datetime, end_datetime)
    ).order_by("-timestamp")

    if interval > 1:
        valid_minutes = [i * interval for i in range(60 // interval)]
        snapshots_qs = snapshots_qs.annotate(minute_val=ExtractMinute("timestamp")).filter(minute_val__in=valid_minutes)

    total_count = snapshots_qs.count()
    paginator = Paginator(range(total_count), 50)
    page_num = max(1, min(page, paginator.num_pages or 1))
    offset = (page_num - 1) * 50

    # Ambil 1 baris ekstra sebelum offset (jika page > 1) agar prev_steam_total terisi akurat untuk delta
    fetch_offset = max(0, offset - 1) if offset > 0 else 0
    fetch_limit = offset + 50
    paged_snapshots = list(snapshots_qs[fetch_offset:fetch_limit])

    all_machines_dict = {m.code: m for m in Machine.objects.filter(is_active=True)}

    table_data = []
    prev_steam_total = None
    prev_hto_total = None
    has_predecessor = (offset > 0 and len(paged_snapshots) > 0)

    for idx, snapshot in enumerate(paged_snapshots):
        cur_steam = 0.0
        cur_hto = 0.0
        for machine_code, snap_data in (snapshot.snapshot_data or {}).items():
            machine = all_machines_dict.get(machine_code)
            if machine:
                is_active = (
                    snap_data.get("status") == "Running" if snap_data.get("mode") == "MANUAL"
                    else snap_data.get("detail") in ["HEAT", "STEADY"]
                )
                if is_active:
                    cur_steam += machine.average_steam_usage
                    cur_hto += machine.avg_hto_calories

        # Baris ekstra hanya digunakan untuk menginisialisasi prev_total
        if has_predecessor and idx == 0:
            prev_steam_total = cur_steam
            prev_hto_total = cur_hto
            continue

        row = {
            "timestamp": timezone.localtime(snapshot.timestamp).isoformat(),
            "machine_data": [],
            "total_steam": round(cur_steam, 1),
            "total_hto": round(cur_hto, 1),
            "delta_steam": None,
            "delta_hto": None,
        }

        for machine in machine_list:
            snap_data = (snapshot.snapshot_data or {}).get(machine.code)
            if snap_data:
                row["machine_data"].append({
                    "code": machine.code,
                    "status": snap_data.get("status", "Unknown"),
                    "detail": snap_data.get("detail", ""),
                    "mode": snap_data.get("mode", "AUTO"),
                })
            else:
                row["machine_data"].append({"code": machine.code, "status": "-", "detail": "-", "mode": "AUTO"})

        if prev_steam_total is not None:
            row["delta_steam"] = round(prev_steam_total - cur_steam, 1)
        if prev_hto_total is not None:
            row["delta_hto"] = round(prev_hto_total - cur_hto, 1)

        prev_steam_total = cur_steam
        prev_hto_total = cur_hto
        table_data.append(row)

    return {
        "results": table_data,
        "page": page_num,
        "num_pages": paginator.num_pages,
        "count": total_count,
        "machine_list": [{"code": m.code, "name": m.name} for m in machine_list],
        "date_from": date_from_parsed.isoformat(),
        "date_to": date_to_parsed.isoformat(),
        "interval": interval,
    }
