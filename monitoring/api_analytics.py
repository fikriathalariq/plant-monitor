from ninja import Router
from ninja.errors import HttpError
from datetime import datetime, timedelta
from django.utils.timezone import make_aware, localtime
from django.db.models import Case, When, IntegerField
from django.db.models.functions import ExtractMinute
from django.conf import settings
from django.db import connection, reset_queries
import json
import logging
import os
import time
import uuid

from monitoring.models import Machine, MachineMinuteLog, MachineStatusSnapshot
from monitoring.decorators import user_can_access_page

analytics_router = Router(tags=["Analytics"])

PAGE_CODE = "analytics"

# ============================================================
# Profiling logger — analytics_perf.log di root project
# Dipakai untuk diagnose lag /grafik sebelum optimasi backend.
# ============================================================
_perf_log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
)
os.makedirs(_perf_log_dir, exist_ok=True)
_perf_log_path = os.path.join(_perf_log_dir, "analytics_perf.log")
_perf_logger = logging.getLogger("analytics_perf_logger")
if not _perf_logger.handlers:
    _handler = logging.FileHandler(_perf_log_path, encoding="utf-8", delay=True)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _perf_logger.addHandler(_handler)
    _perf_logger.setLevel(logging.INFO)
    _perf_logger.propagate = False


class AnalyticsProfiler:
    """Timer sederhana per request analytics."""

    def __init__(self, endpoint: str, **meta):
        self.endpoint = endpoint
        self.meta = meta
        self.req_id = uuid.uuid4().hex[:10]
        self.t0 = time.perf_counter()
        self.marks = {}
        self.row_counts = {}
        self._dbg_q0 = None
        if settings.DEBUG:
            reset_queries()
            self._dbg_q0 = len(connection.queries)

    def mark(self, name: str):
        self.marks[name] = round((time.perf_counter() - self.t0) * 1000, 1)

    def set_rows(self, name: str, count: int):
        self.row_counts[name] = count

    def finish(self, payload=None, error=None):
        total_ms = round((time.perf_counter() - self.t0) * 1000, 1)
        resp_bytes = 0
        if payload is not None:
            try:
                resp_bytes = len(json.dumps(payload, default=str))
            except Exception:
                resp_bytes = -1

        query_count = None
        if settings.DEBUG and self._dbg_q0 is not None:
            query_count = len(connection.queries) - self._dbg_q0

        parts = [
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"id={self.req_id}",
            f"endpoint={self.endpoint}",
            f"total_ms={total_ms}",
            f"resp_bytes={resp_bytes}",
        ]
        if query_count is not None:
            parts.append(f"db_queries={query_count}")
        for k, v in self.marks.items():
            parts.append(f"{k}_ms={v}")
        for k, v in self.row_counts.items():
            parts.append(f"{k}={v}")
        for k, v in self.meta.items():
            if v is not None:
                parts.append(f"{k}={v}")
        if error:
            parts.append(f"error={error}")
        _perf_logger.info(" | ".join(parts))
        return payload


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


@analytics_router.get("/machines")
def get_analytics_machines(request):
    """Porting dari monitoring.views.graph_menu — daftar mesin untuk dropdown chart."""
    _require_permission(request)
    prof = AnalyticsProfiler("machines")

    machines = list(
        Machine.objects.filter(is_active=True)
        .select_related("group")
        .annotate(
            boiler_sort=Case(
                When(group__code="MC_BOILER", then=1),
                default=0,
                output_field=IntegerField(),
            )
        )
        .order_by("boiler_sort", "name")
    )
    prof.mark("db")
    prof.set_rows("machines", len(machines))

    payload = [
        {
            "code": m.code,
            "name": m.name,
            "unit": m.unit_symbol,
            "group": m.group.name if m.group else None,
            "group_code": m.group.code if m.group else None,
        }
        for m in machines
    ]
    return prof.finish(payload)


@analytics_router.get("/graph-multi")
def get_graph_multi(request, machines: str, start: str, end: str):
    """Porting dari monitoring.views.graph_multi_api."""
    _require_permission(request)
    machine_codes = [c.strip() for c in machines.split(",") if c.strip()]
    prof = AnalyticsProfiler(
        "graph-multi",
        machines_n=len(machine_codes),
        start=start,
        end=end,
    )

    try:
        start_dt = make_aware(datetime.strptime(start, "%Y-%m-%d %H:%M"))
        end_dt = make_aware(datetime.strptime(end, "%Y-%m-%d %H:%M"))
    except ValueError:
        raise HttpError(400, "Invalid datetime format")

    range_hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    prof.meta["range_hours"] = range_hours

    machine_lookup = {m.code: m for m in Machine.objects.filter(code__in=machine_codes)}
    prof.mark("db_machines")

    logs = (
        MachineMinuteLog.objects
        .filter(machine__code__in=machine_codes, timestamp__range=(start_dt, end_dt))
        .values("timestamp", "machine__code", "temperature", "filtered_temp", "gradient", "thermal_state", "ewma_temp", "kalman_x")
        .order_by("timestamp")
    )

    table = {}
    row_count = 0
    for log in logs:
        row_count += 1
        ts = localtime(log["timestamp"]).strftime("%Y-%m-%d %H:%M")
        table.setdefault(ts, {})[log["machine__code"]] = {
            "temp": log["temperature"],
            "filtered": log["filtered_temp"],
            "gradient": log["gradient"],
            "state": log["thermal_state"],
            "ewma": log["ewma_temp"],
            "kalman": log["kalman_x"],
        }
    prof.mark("db_and_build")
    prof.set_rows("log_rows", row_count)
    prof.set_rows("timestamps", len(table))

    timestamps = sorted(table.keys())
    meta_map = {
        code: {"unit": machine_lookup[code].unit_symbol, "nominal_power": machine_lookup[code].nominal_power}
        for code in machine_codes if code in machine_lookup
    }

    payload = {"timestamps": timestamps, "machines": machine_codes, "table": table, "meta": meta_map}
    return prof.finish(payload)


@analytics_router.get("/steam-hto")
def get_steam_hto_analytics(request, start: str, end: str, interval: int = 5):
    """Porting dari monitoring.views.steam_hto_analytics_api."""
    _require_permission(request)
    prof = AnalyticsProfiler("steam-hto", start=start, end=end, interval=interval)

    try:
        start_dt = make_aware(datetime.strptime(start, "%Y-%m-%d %H:%M"))
        end_dt = make_aware(datetime.strptime(end, "%Y-%m-%d %H:%M"))
    except ValueError:
        raise HttpError(400, "Invalid datetime format")

    if interval not in [1, 5, 15, 30, 60]:
        interval = 5
        prof.meta["interval"] = interval

    range_hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
    prof.meta["range_hours"] = range_hours

    snapshots_qs = MachineStatusSnapshot.objects.filter(timestamp__range=(start_dt, end_dt)).order_by("timestamp")
    if interval > 1:
        valid_minutes = [i * interval for i in range(60 // interval)]
        snapshots_qs = snapshots_qs.annotate(minute_val=ExtractMinute("timestamp")).filter(minute_val__in=valid_minutes)

    snapshots = list(snapshots_qs.values_list("timestamp", "snapshot_data"))
    prof.mark("db_snapshots")
    prof.set_rows("snapshots_loaded", len(snapshots))

    machine_dict = {m.code: m for m in Machine.objects.filter(is_active=True).select_related("group")}
    prof.mark("db_machines")

    results = []
    for snap_timestamp, snapshot_data in snapshots:

        total_steam = 0.0
        total_hto = 0.0
        steam_machine_count = 0
        hto_machine_count = 0
        steam_pressure = None
        steam_by_group, hto_by_group = {}, {}
        steam_count_by_group, hto_count_by_group = {}, {}

        for machine_code, snap_data in (snapshot_data or {}).items():
            if machine_code.lower() == "steam_pr":
                steam_pressure = snap_data.get("temperature")
                continue

            machine = machine_dict.get(machine_code)
            if not machine:
                continue

            if snap_data.get("mode") == "MANUAL":
                is_active = snap_data.get("status") == "Running"
            else:
                is_active = snap_data.get("detail") in ["HEAT", "STEADY"]

            if is_active:
                group_name = machine.group.name if machine.group else "Lainnya"
                if machine.average_steam_usage and machine.average_steam_usage > 0:
                    total_steam += machine.average_steam_usage
                    steam_machine_count += 1
                    steam_by_group[group_name] = steam_by_group.get(group_name, 0.0) + machine.average_steam_usage
                    steam_count_by_group[group_name] = steam_count_by_group.get(group_name, 0) + 1
                if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                    total_hto += machine.avg_hto_calories
                    hto_machine_count += 1
                    hto_by_group[group_name] = hto_by_group.get(group_name, 0.0) + machine.avg_hto_calories
                    hto_count_by_group[group_name] = hto_count_by_group.get(group_name, 0) + 1

        results.append({
            "timestamp": localtime(snap_timestamp).strftime("%Y-%m-%d %H:%M"),
            "steam": total_steam,
            "hto": total_hto,
            "steam_machines": steam_machine_count,
            "hto_machines": hto_machine_count,
            "steam_pressure": round(steam_pressure, 2) if steam_pressure is not None else None,
            "steam_by_group": steam_by_group,
            "hto_by_group": hto_by_group,
            "steam_count_by_group": steam_count_by_group,
            "hto_count_by_group": hto_count_by_group,
        })

    prof.mark("python_agg")
    prof.set_rows("data_points", len(results))

    all_steam_groups = sorted(set(g for r in results for g in r["steam_by_group"]))
    all_hto_groups = sorted(set(g for r in results for g in r["hto_by_group"]))

    steam_by_group_series = {g: [round(r["steam_by_group"].get(g, 0.0), 2) for r in results] for g in all_steam_groups}
    hto_by_group_series = {g: [round(r["hto_by_group"].get(g, 0.0), 2) for r in results] for g in all_hto_groups}
    steam_count_by_group_series = {g: [r["steam_count_by_group"].get(g, 0) for r in results] for g in all_steam_groups}
    hto_count_by_group_series = {g: [r["hto_count_by_group"].get(g, 0) for r in results] for g in all_hto_groups}

    payload = {
        "timestamps": [r["timestamp"] for r in results],
        "steam_totals": [r["steam"] for r in results],
        "hto_totals": [r["hto"] for r in results],
        "steam_machine_counts": [r["steam_machines"] for r in results],
        "hto_machine_counts": [r["hto_machines"] for r in results],
        "steam_pressures": [r["steam_pressure"] for r in results],
        "steam_by_group": steam_by_group_series,
        "hto_by_group": hto_by_group_series,
        "steam_count_by_group": steam_count_by_group_series,
        "hto_count_by_group": hto_count_by_group_series,
        "steam_groups": all_steam_groups,
        "hto_groups": all_hto_groups,
        "interval": interval,
        "data_points": len(results),
    }
    return prof.finish(payload)


@analytics_router.get("/snapshot-detail")
def get_snapshot_detail(request, timestamp: str, type: str = "steam"):
    """Porting dari monitoring.views.snapshot_detail_api."""
    _require_permission(request)
    prof = AnalyticsProfiler("snapshot-detail", timestamp=timestamp, type=type)

    try:
        timestamp_dt = make_aware(datetime.strptime(timestamp, "%Y-%m-%d %H:%M"))
    except ValueError:
        raise HttpError(400, "Invalid timestamp format. Use YYYY-MM-DD HH:MM")

    try:
        snapshot = MachineStatusSnapshot.objects.get(timestamp=timestamp_dt)
    except MachineStatusSnapshot.DoesNotExist:
        payload = {
            "error": "No snapshot found at this timestamp",
            "timestamp": timestamp,
            "machines": [],
            "total_machines": 0,
            "total_usage": 0,
        }
        return prof.finish(payload)

    machine_dict = {m.code: m for m in Machine.objects.filter(is_active=True).select_related("group")}
    one_hour_ago = timestamp_dt - timedelta(hours=1)
    prev_snapshot = MachineStatusSnapshot.objects.filter(timestamp__lte=one_hour_ago).order_by("-timestamp").first()
    prof.mark("db")

    machines_data = []
    total_usage = 0.0

    for machine_code, snap_data in snapshot.snapshot_data.items():
        machine = machine_dict.get(machine_code)
        if not machine:
            continue

        current_state = snap_data.get("detail", "Unknown")
        current_status = snap_data.get("status", "Unknown")
        current_mode = snap_data.get("mode", "Unknown")

        usage_value = 0.0
        unit = ""
        if type == "steam":
            if machine.average_steam_usage and machine.average_steam_usage > 0:
                usage_value = machine.average_steam_usage
                unit = "kg/h"
            else:
                continue
        else:
            if machine.avg_hto_calories and machine.avg_hto_calories > 0:
                usage_value = machine.avg_hto_calories
                unit = "kCal/h"
            else:
                continue

        is_currently_active = (
            snap_data.get("status") == "Running" if snap_data.get("mode") == "MANUAL"
            else snap_data.get("detail") in ["HEAT", "STEADY"]
        )

        if is_currently_active:
            total_usage += usage_value

        status_change = None
        if prev_snapshot and machine_code in prev_snapshot.snapshot_data:
            prev_data = prev_snapshot.snapshot_data[machine_code]
            prev_state = prev_data.get("detail", "Unknown")
            prev_status = prev_data.get("status", "Unknown")
            prev_mode = prev_data.get("mode", "Unknown")
            hours_ago = (timestamp_dt - prev_snapshot.timestamp).total_seconds() / 3600

            state_changed = False
            change_description = []
            if prev_mode != current_mode:
                state_changed = True
                change_description.append(f"Mode: {prev_mode} \u2192 {current_mode}")
            if prev_status != current_status:
                state_changed = True
                change_description.append(f"Status: {prev_status} \u2192 {current_status}")
            if prev_state != current_state:
                state_changed = True
                change_description.append(f"State: {prev_state} \u2192 {current_state}")

            if state_changed:
                status_change = {
                    "changed": True, "from_state": prev_state, "to_state": current_state,
                    "from_status": prev_status, "to_status": current_status,
                    "from_mode": prev_mode, "to_mode": current_mode,
                    "description": " | ".join(change_description), "hours_ago": round(hours_ago, 1),
                }
            else:
                status_change = {"changed": False, "description": f"Stable for {round(hours_ago, 1)}h"}
        else:
            status_change = {"changed": False, "description": "New in this period"}

        machines_data.append({
            "code": machine.code,
            "name": machine.name or machine.code,
            "status": snap_data.get("status", "Unknown"),
            "mode": snap_data.get("mode", "Unknown"),
            "thermal_state": snap_data.get("detail", "Unknown"),
            "usage_value": round(usage_value, 1),
            "unit": unit,
            "group": machine.group.name if machine.group else "No Group",
            "status_change": status_change,
            "is_currently_active": is_currently_active,
        })

    machines_data.sort(key=lambda x: x["usage_value"], reverse=True)
    total_active = sum(1 for m in machines_data if m["is_currently_active"])
    total_inactive = len(machines_data) - total_active
    prof.set_rows("machines", len(machines_data))

    state_counts = {"running": 0, "heat": 0, "steady": 0, "off": 0, "cool": 0, "stop": 0}
    for m in machines_data:
        if m["mode"] == "MANUAL":
            state_counts["running" if m["status"] == "Running" else "stop"] += 1
        else:
            state = m["thermal_state"].upper()
            if state in ("HEAT", "STEADY", "COOL", "OFF"):
                state_counts[state.lower()] += 1
            else:
                state_counts["off"] += 1

    payload = {
        "timestamp": timestamp,
        "type": type,
        "machines": machines_data,
        "total_machines": len(machines_data),
        "total_active_machines": total_active,
        "total_inactive_machines": total_inactive,
        "state_counts": state_counts,
        "total_usage": round(total_usage, 1),
        "unit": "kg/h" if type == "steam" else "kCal/h",
    }
    return prof.finish(payload)


# ============================================================
# NEW PINN STEAM ANALYTICS ENDPOINTS
# ============================================================
from monitoring.models import DyeingProcess, MachinePhysicsProfile

@analytics_router.get("/steam/recent-batches")
def get_recent_steam_batches(request, limit: int = 50):
    """
    Menampilkan batch-batch terbaru yang sudah dikalkulasi uapnya.
    """
    _require_permission(request)
    
    batches = DyeingProcess.objects.filter(
        predicted_steam_kg__isnull=False
    ).select_related('machine', 'machine__group').order_by('-end_time')[:limit]
    
    data = []
    for b in batches:
        data.append({
            'batch_number': b.batch_number,
            'machine_code': b.machine.code,
            'group_name': b.machine.group.name if b.machine.group else None,
            'start_time': b.start_time.strftime('%Y-%m-%d %H:%M') if b.start_time else None,
            'end_time': b.end_time.strftime('%Y-%m-%d %H:%M') if b.end_time else None,
            'predicted_steam_kg': b.predicted_steam_kg,
            'predicted_steam_best_kg': b.predicted_steam_best_kg,
            'predicted_steam_ideal_kg': b.predicted_steam_ideal_kg,
        })
    
    return {"status": "success", "data": data}


@analytics_router.get("/steam/machine/{machine_code}")
def get_machine_steam_history(request, machine_code: str, limit: int = 20):
    """
    Melihat tren historis konsumsi uap untuk 1 mesin tertentu.
    """
    _require_permission(request)
    
    batches = DyeingProcess.objects.filter(
        machine__code=machine_code,
        predicted_steam_kg__isnull=False
    ).order_by('batch_number')
    
    # Ambil latest 'limit' batches, tapi urutkan chronologically
    batches = list(batches.reverse()[:limit])
    batches.reverse()
    
    data = []
    for b in batches:
        data.append({
            'batch_number': b.batch_number,
            'predicted_steam_kg': b.predicted_steam_kg,
            'predicted_steam_best_kg': b.predicted_steam_best_kg,
            'predicted_steam_ideal_kg': b.predicted_steam_ideal_kg,
            'date': b.start_time.strftime('%m-%d') if b.start_time else ''
        })
        
    return {"status": "success", "machine": machine_code, "data": data}


@analytics_router.get("/steam/group-comparison")
def get_group_steam_comparison(request, group_code: str):
    """
    Membandingkan performa mesin dalam 1 grup.
    (Misal: membandingkan JD_03 dan JD_13 di grup B_4000L).
    """
    _require_permission(request)
    
    profiles = MachinePhysicsProfile.objects.filter(
        machine_group=group_code,
        is_active=True
    ).select_related('machine')
    
    data = []
    for p in profiles:
        data.append({
            'machine_code': p.machine.code,
            'meq': p.meq,
            'uloss': p.uloss,
            'is_best': p.is_best_of_group,
            'mae_pct': p.calibration_mae_pct,
            'k_drop': p.k_drop,
            'n_exp': p.n_exp,
        })
        
    return {"status": "success", "group": group_code, "profiles": data}
