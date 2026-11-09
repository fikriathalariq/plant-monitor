from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from monitoring.models import DyeingIdentity, DyeingProcess, Machine, ProgramMaster, MachineMinuteLog
from monitoring.decorators import user_can_access_page
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404

identity_router = Router(tags=["Dyeing Identity"])

PAGE_CODE = "dyeing_identities"


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


class MachineSchema(Schema):
    id: int
    code: str
    name: str


class ProgramSchema(Schema):
    id: int
    nama: str
    suhu_max: Optional[float] = None
    durasi_ideal: Optional[float] = None
    durasi_heating_ideal: Optional[float] = None
    durasi_keeping_ideal: Optional[float] = None
    durasi_cooling_ideal: Optional[float] = None


class DyeingIdentityOut(Schema):
    id: int
    machine: Optional[MachineSchema] = None
    nomor_order: str
    artikel_kain: str
    batch: str
    kode_buyer: str
    program: Optional[ProgramSchema] = None
    isi_per_tube: Optional[str] = None
    operator: Optional[str] = None
    nomor_warna: str
    nomor_desain: str
    handling_quality: str
    jenis_proses: str
    cycle_60: Optional[str] = None
    cycle_puncak: Optional[str] = None
    nozzle_main_pump: Optional[str] = None
    masalah: Optional[str] = ""
    keterangan: Optional[str] = ""
    output_yard: Optional[float] = None
    start_time_snapshot: Optional[datetime] = None
    dyeing_process_id: Optional[int] = None
    dyeing_process_batch: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def resolve_dyeing_process_batch(obj):
        if obj.dyeing_process:
            return obj.dyeing_process.batch_number
        return None

    @staticmethod
    def resolve_output_yard(obj):
        try:
            return obj.output_yard
        except Exception:
            return None


class DyeingIdentityIn(Schema):
    dyeing_process_id: Optional[int] = None
    machine_id: Optional[int] = None
    nomor_order: str = ""
    artikel_kain: str = ""
    batch: str = ""
    kode_buyer: str = ""
    program_id: Optional[int] = None
    isi_per_tube: str = ""
    operator: str = ""
    nomor_warna: str = ""
    nomor_desain: str = ""
    handling_quality: str = ""
    jenis_proses: str = "FRESH"
    cycle_60: str = ""
    cycle_puncak: str = ""
    nozzle_main_pump: str = ""
    masalah: str = ""
    keterangan: str = ""


class PendingBatchItem(Schema):
    id: int  # DyeingProcess ID
    machine_id: int
    machine_code: str
    machine_name: str
    batch_number: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    peak_temp: Optional[float] = None
    heating_duration: Optional[float] = None
    steady_duration: Optional[float] = None
    cooling_duration: Optional[float] = None
    is_complete: bool
    identity_id: Optional[int] = None
    nomor_order: Optional[str] = None
    status: str  # "UNFILLED" or "INCOMPLETE"


class PendingBatchesResponse(Schema):
    count: int
    unfilled_count: int
    incomplete_count: int
    items: List[PendingBatchItem]


@identity_router.get("/options")
def get_options(request):
    _require_permission(request)
    machines = list(Machine.objects.filter(is_active=True).values('id', 'code', 'name').order_by('code'))
    programs = list(ProgramMaster.objects.values(
        'id', 'nama', 'suhu_max', 'durasi_ideal',
        'durasi_heating_ideal', 'durasi_keeping_ideal', 'durasi_cooling_ideal'
    ).order_by('nama'))
    jenis_proses_choices = [{"value": v, "label": l} for v, l in DyeingIdentity.JENIS_PROSES_CHOICES]
    return {
        "machines": machines,
        "programs": programs,
        "jenis_proses": jenis_proses_choices
    }


@identity_router.get("/process-telemetry/{process_id}")
def get_process_telemetry(request, process_id: int):
    _require_permission(request)
    process = get_object_or_404(
        DyeingProcess.objects.select_related('machine'),
        id=process_id
    )

    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()

    logs_qs = MachineMinuteLog.objects.filter(
        machine=process.machine,
        timestamp__range=(start_dt, end_dt)
    ).values_list('timestamp', 'temperature').order_by('timestamp')

    logs_list = list(logs_qs)
    total_logs = len(logs_list)
    target_points = 80
    if total_logs > target_points:
        step = max(1, total_logs // target_points)
        downsampled = logs_list[::step]
    else:
        downsampled = logs_list

    curve = [
        {
            "time": timezone.localtime(ts).strftime("%H:%M"),
            "temp": round(temp, 1) if temp is not None else None
        }
        for ts, temp in downsampled
    ]

    heating_duration = round(process.real_heating_duration or process.heating_duration, 1) if (process.real_heating_duration or process.heating_duration) is not None else None
    steady_duration = round(process.steady_duration, 1) if process.steady_duration is not None else None
    cooling_duration = round(process.cooling_duration, 1) if process.cooling_duration is not None else None
    duration_effective = round(process.duration_effective, 1) if process.duration_effective is not None else None

    return {
        "id": process.id,
        "machine_id": process.machine_id,
        "machine_code": process.machine.code if process.machine else "-",
        "machine_name": process.machine.name if process.machine else "-",
        "batch_number": process.batch_number,
        "start_time": process.start_time,
        "end_time": process.end_time,
        "duration_minutes": round(process.total_duration, 1) if process.total_duration else None,
        "duration_effective": duration_effective,
        "max_temp": round(process.max_temp, 1) if process.max_temp is not None else None,
        "heating_duration": heating_duration,
        "steady_duration": steady_duration,
        "cooling_duration": cooling_duration,
        "heating_start_time": timezone.localtime(process.heating_start_time).strftime("%H:%M") if process.heating_start_time else None,
        "steady_start_time": timezone.localtime(process.steady_start_time).strftime("%H:%M") if process.steady_start_time else None,
        "reached_70c_time": timezone.localtime(process.reached_70c_time or process.cooling_start_time).strftime("%H:%M") if (process.reached_70c_time or process.cooling_start_time) else None,
        "curve": curve,
    }


@identity_router.get("/pending-batches", response=PendingBatchesResponse)
def list_pending_batches(
    request,
    days: int = 7,
    machine_id: Optional[int] = None,
    search: Optional[str] = None
):
    _require_permission(request)
    now = timezone.now()
    since = now - timedelta(days=max(1, min(days, 60)))

    qs = DyeingProcess.objects.filter(
        start_time__gte=since,
        is_valid_process=True
    ).select_related('machine', 'identity')

    if machine_id:
        qs = qs.filter(machine_id=machine_id)

    if search:
        search = search.strip()
        qs = qs.filter(
            Q(machine__code__icontains=search) |
            Q(batch_number__icontains=search)
        )

    qs = qs.order_by('-start_time')

    items = []
    unfilled_count = 0
    incomplete_count = 0

    for p in qs[:200]:
        has_id = hasattr(p, 'identity') and p.identity is not None
        h_dur = round(p.real_heating_duration or p.heating_duration, 1) if (p.real_heating_duration or p.heating_duration) is not None else None
        s_dur = round(p.steady_duration, 1) if p.steady_duration is not None else None
        c_dur = round(p.cooling_duration, 1) if p.cooling_duration is not None else None

        if not has_id:
            unfilled_count += 1
            items.append(PendingBatchItem(
                id=p.id,
                machine_id=p.machine_id,
                machine_code=p.machine.code if p.machine else "-",
                machine_name=p.machine.name if p.machine else "-",
                batch_number=p.batch_number,
                start_time=p.start_time,
                end_time=p.end_time,
                duration_minutes=round(p.total_duration, 1) if p.total_duration else None,
                peak_temp=round(p.max_temp, 1) if p.max_temp is not None else None,
                heating_duration=h_dur,
                steady_duration=s_dur,
                cooling_duration=c_dur,
                is_complete=p.is_complete,
                identity_id=None,
                nomor_order=None,
                status="UNFILLED"
            ))
        elif not p.identity.nomor_order:
            incomplete_count += 1
            items.append(PendingBatchItem(
                id=p.id,
                machine_id=p.machine_id,
                machine_code=p.machine.code if p.machine else "-",
                machine_name=p.machine.name if p.machine else "-",
                batch_number=p.batch_number,
                start_time=p.start_time,
                end_time=p.end_time,
                duration_minutes=round(p.total_duration, 1) if p.total_duration else None,
                peak_temp=round(p.max_temp, 1) if p.max_temp is not None else None,
                heating_duration=h_dur,
                steady_duration=s_dur,
                cooling_duration=c_dur,
                is_complete=p.is_complete,
                identity_id=p.identity.id,
                nomor_order=p.identity.nomor_order,
                status="INCOMPLETE"
            ))

    return {
        "count": len(items),
        "unfilled_count": unfilled_count,
        "incomplete_count": incomplete_count,
        "items": items
    }


@identity_router.get("/prefill")
def get_prefill_data(
    request,
    machine_id: Optional[int] = None,
    order_no: Optional[str] = None
):
    _require_permission(request)
    result = {}

    if order_no:
        clean_order = order_no.strip()
        match = DyeingIdentity.objects.filter(
            nomor_order__iexact=clean_order
        ).exclude(nomor_order='').select_related('program').order_by('-id').first()
        if match:
            result["order_match"] = {
                "nomor_order": match.nomor_order,
                "artikel_kain": match.artikel_kain,
                "kode_buyer": match.kode_buyer,
                "nomor_warna": match.nomor_warna,
                "nomor_desain": match.nomor_desain,
                "program_id": match.program_id,
                "program_nama": match.program.nama if match.program else None,
                "jenis_proses": match.jenis_proses,
            }

    if machine_id:
        last_machine_id = DyeingIdentity.objects.filter(
            machine_id=machine_id
        ).exclude(nomor_order='').select_related('program').order_by('-id').first()
        if last_machine_id:
            result["machine_last"] = {
                "nomor_order": last_machine_id.nomor_order,
                "artikel_kain": last_machine_id.artikel_kain,
                "batch": last_machine_id.batch,
                "kode_buyer": last_machine_id.kode_buyer,
                "program_id": last_machine_id.program_id,
                "program_nama": last_machine_id.program.nama if last_machine_id.program else None,
                "jenis_proses": last_machine_id.jenis_proses,
                "isi_per_tube": last_machine_id.isi_per_tube,
                "operator": last_machine_id.operator,
                "nomor_warna": last_machine_id.nomor_warna,
                "nomor_desain": last_machine_id.nomor_desain,
                "cycle_60": last_machine_id.cycle_60,
                "cycle_puncak": last_machine_id.cycle_puncak,
                "nozzle_main_pump": last_machine_id.nozzle_main_pump,
                "handling_quality": last_machine_id.handling_quality,
            }

    return result


@identity_router.get("/stats")
def get_identity_stats(request):
    _require_permission(request)
    now = timezone.now()
    since_7d = now - timedelta(days=7)

    total_identities = DyeingIdentity.objects.count()
    fresh_count = DyeingIdentity.objects.filter(jenis_proses="FRESH").count()
    rework_count = DyeingIdentity.objects.exclude(jenis_proses__in=["FRESH", ""]).count()
    orphan_count = DyeingIdentity.objects.filter(dyeing_process__isnull=True).count()

    # Pending batches in last 7 days
    recent_processes = DyeingProcess.objects.filter(
        start_time__gte=since_7d,
        is_valid_process=True
    ).select_related('identity')
    pending_count = sum(
        1 for p in recent_processes
        if not hasattr(p, 'identity') or p.identity is None or not p.identity.nomor_order
    )

    return {
        "total_identities": total_identities,
        "fresh_count": fresh_count,
        "rework_count": rework_count,
        "orphan_count": orphan_count,
        "pending_batches_7d": pending_count,
    }


@identity_router.get("/", response=List[DyeingIdentityOut])
@paginate(PageNumberPagination, page_size=20)
def list_identities(
    request,
    search: Optional[str] = None,
    machine_id: Optional[int] = None,
    jenis_proses: Optional[str] = None,
    program_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    is_orphan: Optional[bool] = None
):
    _require_permission(request)
    qs = DyeingIdentity.objects.select_related('machine', 'program', 'dyeing_process').order_by('-id')

    if search:
        search = search.strip()
        qs = qs.filter(
            Q(nomor_order__icontains=search) |
            Q(artikel_kain__icontains=search) |
            Q(batch__icontains=search) |
            Q(kode_buyer__icontains=search) |
            Q(operator__icontains=search)
        )

    if machine_id:
        qs = qs.filter(machine_id=machine_id)

    if jenis_proses:
        qs = qs.filter(jenis_proses=jenis_proses)

    if program_id:
        qs = qs.filter(program_id=program_id)

    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d")
            qs = qs.filter(created_at__date__gte=df.date())
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d")
            qs = qs.filter(created_at__date__lte=dt.date())
        except ValueError:
            pass

    if is_orphan is not None:
        qs = qs.filter(dyeing_process__isnull=is_orphan)

    return qs


@identity_router.get("/{identity_id}", response=DyeingIdentityOut)
def get_identity(request, identity_id: int):
    _require_permission(request)
    return get_object_or_404(
        DyeingIdentity.objects.select_related('machine', 'program', 'dyeing_process'),
        id=identity_id
    )


@identity_router.post("/", response=DyeingIdentityOut)
def create_identity(request, payload: DyeingIdentityIn):
    _require_permission(request)
    data = payload.dict()
    process_id = data.pop('dyeing_process_id', None)

    if process_id:
        process = get_object_or_404(DyeingProcess, id=process_id)
        # Check if process already has an identity (to avoid OneToOne unique error)
        existing_identity = getattr(process, 'identity', None)
        if existing_identity:
            # Update the existing identity instead of duplicating
            for attr, value in data.items():
                setattr(existing_identity, attr, value)
            existing_identity.machine = process.machine
            if not existing_identity.start_time_snapshot:
                existing_identity.start_time_snapshot = process.start_time
            existing_identity.save()
            return existing_identity
        else:
            data['dyeing_process'] = process
            data['machine'] = process.machine
            data['start_time_snapshot'] = process.start_time
            identity = DyeingIdentity.objects.create(**data)
            return identity

    # Regular creation without linked process
    identity = DyeingIdentity.objects.create(**data)
    return identity


@identity_router.put("/{identity_id}", response=DyeingIdentityOut)
def update_identity(request, identity_id: int, payload: DyeingIdentityIn):
    _require_permission(request)
    identity = get_object_or_404(DyeingIdentity, id=identity_id)
    data = payload.dict()
    process_id = data.pop('dyeing_process_id', None)

    if process_id:
        process = get_object_or_404(DyeingProcess, id=process_id)
        identity.dyeing_process = process
        identity.machine = process.machine
        if not identity.start_time_snapshot:
            identity.start_time_snapshot = process.start_time

    for attr, value in data.items():
        setattr(identity, attr, value)

    identity.save()
    return identity


@identity_router.delete("/{identity_id}")
def delete_identity(request, identity_id: int):
    _require_permission(request)
    identity = get_object_or_404(DyeingIdentity, id=identity_id)
    identity.delete()
    return {"success": True}
