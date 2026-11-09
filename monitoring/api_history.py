from ninja import Router, Schema
from typing import List, Optional
from django.core.paginator import Paginator
from monitoring.models import DyeingProcess, Machine, MachineGroup

history_router = Router(tags=["History"])

ALLOWED_HISTORY_GROUPS = ["JET PRT", "JD PRC", "JR PRC"]


class HistoryItemSchema(Schema):
    id: int
    machine_code: str
    machine_name: str
    group_name: str
    batch_number: int
    start_time: str
    end_time: Optional[str] = None
    is_complete: bool
    total_duration: Optional[float] = None
    effective_duration: Optional[float] = None
    max_temp: Optional[float] = None
    efficiency: Optional[float] = None
    thermal_status: Optional[str] = None
    program: Optional[str] = None
    process: Optional[str] = None
    artikel: Optional[str] = None
    no_order: Optional[str] = None
    warna: Optional[str] = None
    isi: Optional[str] = None
    batch_kain: Optional[str] = None
    operator: Optional[str] = None
    avg_steam_pressure: Optional[float] = None
    anomaly_types: List[str] = []


class HistoryListResponse(Schema):
    total: int
    page: int
    per_page: int
    num_pages: int
    data: List[HistoryItemSchema]


class HistoryFiltersGroupSchema(Schema):
    code: str
    name: str


class HistoryFiltersMachineSchema(Schema):
    code: str
    name: str
    group_code: str


class HistoryFiltersResponse(Schema):
    groups: List[HistoryFiltersGroupSchema]
    machines: List[HistoryFiltersMachineSchema]


@history_router.get("/filters", response=HistoryFiltersResponse)
def get_history_filters(request):
    groups = [
        {"code": g.code, "name": g.name}
        for g in MachineGroup.objects.filter(code__in=ALLOWED_HISTORY_GROUPS).order_by("code")
    ]

    machines = [
        {"code": m.code, "name": m.name, "group_code": m.group.code}
        for m in (
            Machine.objects.filter(is_active=True, group__code__in=ALLOWED_HISTORY_GROUPS)
            .select_related("group")
            .order_by("group__code", "code")
        )
    ]

    return {"groups": groups, "machines": machines}


@history_router.get("/", response=HistoryListResponse)
def get_history(
    request,
    page: int = 1,
    per_page: int = 10,
    search: str = None,
    group: str = None,
    machine: str = None,
    start_date: str = None,
    end_date: str = None,
):
    queryset = (
        DyeingProcess.objects
        .select_related("machine", "machine__group", "identity", "identity__program")
        .filter(machine__group__code__in=ALLOWED_HISTORY_GROUPS)
        .order_by("-start_time")
    )

    if group and group in ALLOWED_HISTORY_GROUPS:
        queryset = queryset.filter(machine__group__code=group)

    if machine:
        queryset = queryset.filter(machine__code=machine)

    # Date range filters (same semantics as SSR history_list.html)
    if start_date:
        try:
            queryset = queryset.filter(start_time__date__gte=start_date)
        except Exception:
            pass
    if end_date:
        try:
            queryset = queryset.filter(start_time__date__lte=end_date)
        except Exception:
            pass

    # AND-per-token search:
    # - split by whitespace
    # - tokens are OR-matched across multiple fields
    # - successive tokens are chained via successive .filter(...) calls => AND between tokens
    if search:
        from django.db.models import Q, CharField
        from django.db.models.functions import Cast

        tokens = [t.lstrip("#") for t in search.strip().split() if t.strip("#")]
        if tokens:
            queryset = queryset.annotate(
                start_str=Cast("start_time", CharField()),
                batch_str=Cast("batch_number", CharField()),
                max_temp_str=Cast("max_temp", CharField()),
                duration_str=Cast("duration_effective", CharField()),
            )

            for token in tokens:
                queryset = queryset.filter(
                    Q(machine__code__icontains=token)
                    | Q(machine__name__icontains=token)
                    | Q(machine__group__name__icontains=token)
                    | Q(batch_str__icontains=token)
                    | Q(start_str__icontains=token)
                    | Q(max_temp_str__icontains=token)
                    | Q(duration_str__icontains=token)
                    | Q(identity__nomor_order__icontains=token)
                    | Q(identity__artikel_kain__icontains=token)
                    | Q(identity__nomor_warna__icontains=token)
                    | Q(identity__jenis_proses__icontains=token)
                    | Q(identity__isi_per_tube__icontains=token)
                    | Q(identity__batch__icontains=token)
                    | Q(identity__operator__icontains=token)
                    | Q(identity__program__nama__icontains=token)
                )

    paginator = Paginator(queryset, per_page)

    if page < 1:
        page = 1
    if paginator.num_pages == 0:
        page_obj = []
        actual_page = 1
    else:
        if page > paginator.num_pages:
            page = paginator.num_pages
        page_obj = paginator.get_page(page).object_list
        actual_page = page

    # Bulk fetch anomalies
    process_ids = [p.id for p in page_obj]
    from .models import DataAnomaly
    from .api_anomaly import map_anomaly_flags
    anomalies = DataAnomaly.objects.filter(process_record_id__in=process_ids)
    
    anomaly_map = {}
    for a in anomalies:
        flags = a.details.get("flags", []) if isinstance(a.details, dict) else []
        mapped_types = map_anomaly_flags(flags)
        if a.process_record_id not in anomaly_map:
            anomaly_map[a.process_record_id] = []
        # Merge if there are multiple anomalies for the same process
        for t in mapped_types:
            if t not in anomaly_map[a.process_record_id]:
                anomaly_map[a.process_record_id].append(t)

    data = []
    for process in page_obj:
        start_str = process.start_time.isoformat() if process.start_time else ""
        end_str = process.end_time.isoformat() if process.end_time else None

        identity = getattr(process, 'identity', None)
        program_name = identity.program.nama if identity and identity.program else None
        proses_name = identity.get_jenis_proses_display() if identity and identity.jenis_proses else None
        
        # New Efficiency Calculation (Time Efficiency: Ideal / Real)
        eff = None
        if identity and identity.program and identity.program.durasi_ideal is not None and process.duration_effective and process.duration_effective > 0:
            eff = round((identity.program.durasi_ideal / process.duration_effective) * 100, 1)
        
        thermal = None if process.is_complete else (process.machine.last_thermal_status or None)
        avg_steam = round(process.avg_steam_pressure, 1) if process.avg_steam_pressure is not None else None

        data.append({
            "id": process.id,
            "machine_code": process.machine.code,
            "machine_name": process.machine.name,
            "group_name": process.machine.group.name if process.machine.group else "-",
            "batch_number": process.batch_number,
            "start_time": start_str,
            "end_time": end_str,
            "is_complete": process.is_complete,
            "total_duration": round(process.total_duration, 1) if process.total_duration else None,
            "effective_duration": round(process.duration_effective, 1) if process.duration_effective else None,
            "max_temp": round(process.max_temp, 1) if process.max_temp else None,
            "efficiency": eff,
            "thermal_status": thermal,
            "program": program_name,
            "process": proses_name,
            "artikel": identity.artikel_kain if identity else None,
            "no_order": identity.nomor_order if identity else None,
            "warna": identity.nomor_warna if identity else None,
            "isi": identity.isi_per_tube if identity else None,
            "batch_kain": identity.batch if identity else None,
            "operator": identity.operator if identity else None,
            "avg_steam_pressure": avg_steam,
            "anomaly_types": anomaly_map.get(process.id, []),
        })

    return {
        "total": paginator.count,
        "page": actual_page,
        "per_page": per_page,
        "num_pages": paginator.num_pages,
        "data": data
    }
