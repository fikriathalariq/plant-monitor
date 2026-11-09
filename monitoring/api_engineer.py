"""
API Engineer Workspace — command center, triage, inspeksi, spare parts,
perhitungan, meeting, dan machine dossier.
"""
from datetime import datetime, timedelta, date
from typing import Optional, List, Any

from django.contrib.auth.models import User
from django.db.models import Q, Count, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema, File
from ninja.files import UploadedFile

from monitoring.models import (
    Machine, MachineGroup, MachineMinuteLog, MachineCalibration,
    DataAnomaly, BoilerDailyMetric,
    InspectionTemplate, FieldInspection, SparePart, SparePartUsageLog,
    EngineerIssue, EngineerNote, CalculationSession, MeetingNote, ActionItem,
    DyeingProcess,
)
from monitoring.utils.batch_analyzer import BatchProcessingConfig, analyze_batch_details

engineer_router = Router(tags=["Engineer Workspace"])


def _require_auth(request):
    if not request.user.is_authenticated:
        return False
    return True


def _auth_or_401(request):
    if not _require_auth(request):
        return 401, {"status": "error", "message": "Authentication required"}
    return None


def _user_brief(user):
    if not user:
        return None
    return {"id": user.id, "username": user.username}


def _machine_brief(m):
    if not m:
        return None
    return {"id": m.id, "code": m.code, "name": m.name}


def _issue_to_dict(issue: EngineerIssue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "source_type": issue.source_type,
        "status": issue.status,
        "priority": issue.priority,
        "machine": _machine_brief(issue.machine),
        "data_anomaly_id": issue.data_anomaly_id,
        "field_inspection_id": issue.field_inspection_id,
        "spare_part_id": issue.spare_part_id,
        "assigned_to": _user_brief(issue.assigned_to),
        "created_by": _user_brief(issue.created_by),
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "resolution_notes": issue.resolution_notes,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
    }


# ── Schemas ──────────────────────────────────────────────────────────────────

class IssueCreateIn(Schema):
    title: str
    description: str = ""
    source_type: str = "MANUAL"
    priority: str = "NORMAL"
    machine_id: Optional[int] = None
    data_anomaly_id: Optional[int] = None
    field_inspection_id: Optional[int] = None
    spare_part_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    due_date: Optional[str] = None


class IssueUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to_id: Optional[int] = None
    due_date: Optional[str] = None
    resolution_notes: Optional[str] = None


class NoteCreateIn(Schema):
    machine_id: int
    content: str


class InspectionCreateIn(Schema):
    machine_id: int
    template_id: Optional[int] = None
    checklist_results: dict = {}
    severity: str = "NORMAL"
    notes: str = ""
    recommendation: str = ""
    status: str = "DRAFT"


class SparePartCreateIn(Schema):
    name: str
    part_number: str = ""
    description: str = ""
    machine_ids: List[int] = []
    location: str = ""
    stock_quantity: int = 0
    min_stock: int = 1
    unit: str = "pcs"


class SparePartUpdateIn(Schema):
    name: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    machine_ids: Optional[List[int]] = None
    location: Optional[str] = None
    stock_quantity: Optional[int] = None
    min_stock: Optional[int] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None


class SpareUsageIn(Schema):
    machine_id: Optional[int] = None
    quantity: int = 1
    notes: str = ""


class CalcSessionCreateIn(Schema):
    title: str
    machine_id: int
    start_time: str
    end_time: str
    parameters: dict = {}


class CalcSessionUpdateIn(Schema):
    title: Optional[str] = None
    parameters: Optional[dict] = None
    results: Optional[dict] = None
    status: Optional[str] = None


class CalcRunIn(Schema):
    parameters: dict = {}


class MeetingCreateIn(Schema):
    title: str
    meeting_date: str
    participants: str = ""
    agenda: str = ""
    notes: str = ""


class ActionItemCreateIn(Schema):
    meeting_id: Optional[int] = None
    description: str
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None
    machine_id: Optional[int] = None
    create_issue: bool = False


class ActionItemUpdateIn(Schema):
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


class TemplateCreateIn(Schema):
    name: str
    machine_group_id: Optional[int] = None
    items: List[dict] = []


# ── Command Center ───────────────────────────────────────────────────────────

@engineer_router.get("/command-center/")
def command_center(request, mine_only: bool = False):
    err = _auth_or_401(request)
    if err:
        return err

    user = request.user
    today = timezone.localdate()

    issue_qs = EngineerIssue.objects.filter(status__in=['OPEN', 'IN_PROGRESS', 'WAITING_PARTS'])
    if mine_only:
        issue_qs = issue_qs.filter(assigned_to=user)
    open_issues = issue_qs.count()
    critical_issues = issue_qs.filter(priority='CRITICAL').count()

    anomaly_count = DataAnomaly.objects.filter(is_resolved=False).count()
    pending_inspections = FieldInspection.objects.filter(status='DRAFT').count()
    low_stock_count = SparePart.objects.filter(
        is_active=True, stock_quantity__lte=F('min_stock')
    ).count()

    action_qs = ActionItem.objects.filter(status='OPEN')
    if mine_only:
        action_qs = action_qs.filter(assignee=user)
    overdue_actions = action_qs.filter(due_date__lt=today).count()
    due_today_actions = action_qs.filter(due_date=today).count()

    # Mesin bermasalah: manual status OFF atau ada issue open
    problem_machine_ids = set(
        issue_qs.exclude(machine=None).values_list('machine_id', flat=True)
    )
    problem_machines = Machine.objects.filter(
        Q(id__in=problem_machine_ids) | Q(manual_status='Stop', is_active=True)
    ).distinct()[:10]

    # Energy condition (boiler)
    boiler_group = MachineGroup.objects.filter(code='MC_BOILER').first()
    if not boiler_group:
        boiler_group = MachineGroup.objects.filter(name__icontains='Boiler').first()
    energy_widgets = []
    if boiler_group:
        for m in Machine.objects.filter(group=boiler_group, is_active=True).order_by('id')[:6]:
            energy_widgets.append({
                "id": m.id,
                "name": m.name,
                "value": round(m.temperature, 2) if m.temperature else 0,
                "unit": m.unit or "",
            })

    # Boiler KPI kemarin
    yesterday = today - timedelta(days=1)
    boiler_kpi = None
    bdm = BoilerDailyMetric.objects.filter(date=yesterday).first()
    if bdm:
        boiler_kpi = {
            "date": yesterday.isoformat(),
            "total_fuel_kg": float(bdm.total_fuel_kg) if bdm.total_fuel_kg else None,
            "specific_fuel_consumption": float(bdm.specific_fuel_consumption) if bdm.specific_fuel_consumption else None,
            "total_steam_kg": float(bdm.total_steam_usage_kg) if bdm.total_steam_usage_kg else None,
        }

    recent_issues = list(issue_qs.select_related('machine', 'assigned_to')[:8])
    recent_actions = list(action_qs.select_related('assignee', 'machine')[:8])

    return {
        "status": "success",
        "data": {
            "summary": {
                "open_issues": open_issues,
                "critical_issues": critical_issues,
                "unresolved_anomalies": anomaly_count,
                "pending_inspections": pending_inspections,
                "low_stock_parts": low_stock_count,
                "overdue_actions": overdue_actions,
                "due_today_actions": due_today_actions,
            },
            "energy_widgets": energy_widgets,
            "boiler_kpi_yesterday": boiler_kpi,
            "problem_machines": [
                {"id": m.id, "code": m.code, "name": m.name, "manual_status": m.manual_status}
                for m in problem_machines
            ],
            "recent_issues": [_issue_to_dict(i) for i in recent_issues],
            "recent_actions": [
                {
                    "id": a.id,
                    "description": a.description,
                    "status": a.status,
                    "due_date": a.due_date.isoformat() if a.due_date else None,
                    "assignee": _user_brief(a.assignee),
                    "machine": _machine_brief(a.machine),
                }
                for a in recent_actions
            ],
        },
    }


# ── Issues (Triage Queue) ───────────────────────────────────────────────────

@engineer_router.get("/issues/")
def list_issues(
    request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    mine_only: bool = False,
    machine_id: Optional[int] = None,
):
    err = _auth_or_401(request)
    if err:
        return err

    qs = EngineerIssue.objects.select_related('machine', 'assigned_to', 'created_by')
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status='RESOLVED')
    if priority:
        qs = qs.filter(priority=priority)
    if mine_only:
        qs = qs.filter(assigned_to=request.user)
    if machine_id:
        qs = qs.filter(machine_id=machine_id)

    # Include unresolved anomalies not yet linked to an issue
    linked_anomaly_ids = set(
        EngineerIssue.objects.exclude(data_anomaly=None).values_list('data_anomaly_id', flat=True)
    )
    anomalies = DataAnomaly.objects.filter(is_resolved=False).exclude(
        id__in=linked_anomaly_ids
    ).select_related('identity_record__machine', 'process_record')[:50]

    anomaly_items = []
    for a in anomalies:
        machine = a.identity_record.machine if a.identity_record else None
        anomaly_items.append({
            "id": f"anomaly-{a.id}",
            "anomaly_id": a.id,
            "title": f"Anomali: {a.anomaly_type}",
            "description": str(a.details),
            "source_type": "ANOMALY",
            "status": "OPEN",
            "priority": "CRITICAL" if a.severity == 'CRITICAL' else ("HIGH" if a.severity == 'MEDIUM' else "NORMAL"),
            "machine": _machine_brief(machine),
            "is_virtual": True,
            "created_at": a.created_at.isoformat(),
        })

    issues = [_issue_to_dict(i) for i in qs]
    return {"status": "success", "data": issues, "unlinked_anomalies": anomaly_items}


@engineer_router.post("/issues/")
def create_issue(request, payload: IssueCreateIn):
    err = _auth_or_401(request)
    if err:
        return err

    due = None
    if payload.due_date:
        due = datetime.strptime(payload.due_date, "%Y-%m-%d").date()

    issue = EngineerIssue.objects.create(
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        priority=payload.priority,
        machine_id=payload.machine_id,
        data_anomaly_id=payload.data_anomaly_id,
        field_inspection_id=payload.field_inspection_id,
        spare_part_id=payload.spare_part_id,
        assigned_to_id=payload.assigned_to_id or request.user.id,
        created_by=request.user,
        due_date=due,
    )
    return {"status": "success", "data": _issue_to_dict(issue)}


@engineer_router.post("/issues/from-anomaly/{anomaly_id}/")
def create_issue_from_anomaly(request, anomaly_id: int):
    err = _auth_or_401(request)
    if err:
        return err

    anomaly = get_object_or_404(DataAnomaly, id=anomaly_id)
    machine = anomaly.identity_record.machine if anomaly.identity_record else None
    issue = EngineerIssue.objects.create(
        title=f"Anomali: {anomaly.anomaly_type}",
        description=str(anomaly.details),
        source_type='ANOMALY',
        priority='CRITICAL' if anomaly.severity == 'CRITICAL' else ('HIGH' if anomaly.severity == 'MEDIUM' else 'NORMAL'),
        machine=machine,
        data_anomaly=anomaly,
        assigned_to=request.user,
        created_by=request.user,
    )
    return {"status": "success", "data": _issue_to_dict(issue)}


@engineer_router.patch("/issues/{issue_id}/")
def update_issue(request, issue_id: int, payload: IssueUpdateIn):
    err = _auth_or_401(request)
    if err:
        return err

    issue = get_object_or_404(EngineerIssue, id=issue_id)
    if payload.title is not None:
        issue.title = payload.title
    if payload.description is not None:
        issue.description = payload.description
    if payload.status is not None:
        issue.status = payload.status
        if payload.status == 'RESOLVED':
            issue.resolved_at = timezone.now()
    if payload.priority is not None:
        issue.priority = payload.priority
    if payload.assigned_to_id is not None:
        issue.assigned_to_id = payload.assigned_to_id
    if payload.due_date is not None:
        issue.due_date = datetime.strptime(payload.due_date, "%Y-%m-%d").date() if payload.due_date else None
    if payload.resolution_notes is not None:
        issue.resolution_notes = payload.resolution_notes
    issue.save()
    return {"status": "success", "data": _issue_to_dict(issue)}


# ── Machine Dossier ──────────────────────────────────────────────────────────

@engineer_router.get("/machines/{machine_id}/dossier/")
def machine_dossier(request, machine_id: int):
    err = _auth_or_401(request)
    if err:
        return err

    machine = get_object_or_404(Machine, id=machine_id)
    now = timezone.now()
    start_24h = now - timedelta(hours=24)

    logs = MachineMinuteLog.objects.filter(machine=machine, timestamp__gte=start_24h).order_by('timestamp')
    chart_data = [
        {"time": timezone.localtime(l.timestamp).strftime("%H:%M"), "temp": l.temperature}
        for l in logs[::5]  # downsample
    ]

    calibration = None
    try:
        cal = machine.calibration
        calibration = {
            "a_coeff": cal.a_coeff, "b_coeff": cal.b_coeff, "c_coeff": cal.c_coeff,
            "is_active": cal.is_active, "notes": cal.notes,
            "updated_at": cal.updated_at.isoformat(),
        }
    except MachineCalibration.DoesNotExist:
        pass

    processes = DyeingProcess.objects.filter(
        machine=machine, is_valid_process=True
    ).order_by('-start_time')[:10]

    batch_history = [
        {
            "id": p.id,
            "batch_number": p.batch_number,
            "start_time": p.start_time.isoformat() if p.start_time else None,
            "total_duration": p.total_duration,
            "efficiency": p.avg_heating_efficiency,
        }
        for p in processes
    ]

    issues = EngineerIssue.objects.filter(machine=machine).exclude(status='RESOLVED')[:20]
    anomalies = DataAnomaly.objects.filter(
        identity_record__machine=machine, is_resolved=False
    )[:20]
    inspections = FieldInspection.objects.filter(machine=machine).order_by('-created_at')[:10]
    notes = EngineerNote.objects.filter(machine=machine).select_related('author')[:20]
    spare_parts = SparePart.objects.filter(machines=machine, is_active=True)

    active_batch = DyeingProcess.objects.filter(
        machine=machine, end_time__isnull=True, is_valid_process=True
    ).order_by('-start_time').first()

    return {
        "status": "success",
        "data": {
            "machine": {
                "id": machine.id,
                "code": machine.code,
                "name": machine.name,
                "temperature": machine.temperature,
                "manual_status": machine.manual_status,
                "group": machine.group.name if machine.group else None,
            },
            "active_batch": {
                "batch_number": active_batch.batch_number,
                "start_time": active_batch.start_time.isoformat(),
            } if active_batch else None,
            "chart_24h": chart_data,
            "calibration": calibration,
            "batch_history": batch_history,
            "open_issues": [_issue_to_dict(i) for i in issues],
            "anomalies": [
                {"id": a.id, "type": a.anomaly_type, "severity": a.severity, "details": a.details}
                for a in anomalies
            ],
            "inspections": [
                {
                    "id": ins.id, "severity": ins.severity, "status": ins.status,
                    "created_at": ins.created_at.isoformat(), "notes": ins.notes,
                }
                for ins in inspections
            ],
            "notes": [
                {
                    "id": n.id, "content": n.content,
                    "author": _user_brief(n.author),
                    "created_at": n.created_at.isoformat(),
                }
                for n in notes
            ],
            "spare_parts": [
                {
                    "id": sp.id, "name": sp.name, "part_number": sp.part_number,
                    "stock_quantity": sp.stock_quantity, "is_low_stock": sp.is_low_stock,
                }
                for sp in spare_parts
            ],
        },
    }


@engineer_router.get("/machines/")
def list_machines_brief(request):
    err = _auth_or_401(request)
    if err:
        return err
    machines = Machine.objects.filter(is_active=True).order_by('code')
    return {
        "status": "success",
        "data": [{"id": m.id, "code": m.code, "name": m.name} for m in machines],
    }


# ── Engineer Notes ───────────────────────────────────────────────────────────

@engineer_router.get("/notes/")
def list_notes(request, machine_id: Optional[int] = None):
    err = _auth_or_401(request)
    if err:
        return err
    qs = EngineerNote.objects.select_related('author', 'machine')
    if machine_id:
        qs = qs.filter(machine_id=machine_id)
    return {
        "status": "success",
        "data": [
            {
                "id": n.id, "content": n.content,
                "machine": _machine_brief(n.machine),
                "author": _user_brief(n.author),
                "created_at": n.created_at.isoformat(),
            }
            for n in qs[:50]
        ],
    }


@engineer_router.post("/notes/")
def create_note(request, payload: NoteCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    note = EngineerNote.objects.create(
        machine_id=payload.machine_id,
        author=request.user,
        content=payload.content,
    )
    return {
        "status": "success",
        "data": {"id": note.id, "content": note.content, "created_at": note.created_at.isoformat()},
    }


# ── Field Inspection ─────────────────────────────────────────────────────────

@engineer_router.get("/inspection-templates/")
def list_templates(request):
    err = _auth_or_401(request)
    if err:
        return err
    templates = InspectionTemplate.objects.filter(is_active=True)
    return {
        "status": "success",
        "data": [
            {
                "id": t.id, "name": t.name, "items": t.items,
                "machine_group_id": t.machine_group_id,
            }
            for t in templates
        ],
    }


@engineer_router.post("/inspection-templates/")
def create_template(request, payload: TemplateCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    t = InspectionTemplate.objects.create(
        name=payload.name,
        machine_group_id=payload.machine_group_id,
        items=payload.items,
    )
    return {"status": "success", "data": {"id": t.id, "name": t.name, "items": t.items}}


@engineer_router.get("/inspections/")
def list_inspections(request, status: Optional[str] = None, machine_id: Optional[int] = None):
    err = _auth_or_401(request)
    if err:
        return err
    qs = FieldInspection.objects.select_related('machine', 'inspector', 'template')
    if status:
        qs = qs.filter(status=status)
    if machine_id:
        qs = qs.filter(machine_id=machine_id)
    return {
        "status": "success",
        "data": [
            {
                "id": ins.id,
                "machine": _machine_brief(ins.machine),
                "inspector": _user_brief(ins.inspector),
                "severity": ins.severity,
                "status": ins.status,
                "notes": ins.notes,
                "checklist_results": ins.checklist_results,
                "photo_url": ins.photo.url if ins.photo else None,
                "created_at": ins.created_at.isoformat(),
                "submitted_at": ins.submitted_at.isoformat() if ins.submitted_at else None,
            }
            for ins in qs[:100]
        ],
    }


@engineer_router.post("/inspections/")
def create_inspection(request, payload: InspectionCreateIn):
    err = _auth_or_401(request)
    if err:
        return err

    submitted_at = timezone.now() if payload.status == 'SUBMITTED' else None
    ins = FieldInspection.objects.create(
        machine_id=payload.machine_id,
        inspector=request.user,
        template_id=payload.template_id,
        checklist_results=payload.checklist_results,
        severity=payload.severity,
        notes=payload.notes,
        recommendation=payload.recommendation,
        status=payload.status,
        submitted_at=submitted_at,
    )

    # Auto-create issue if severity is critical/high and submitted
    if payload.status == 'SUBMITTED' and payload.severity in ('CRITICAL', 'HIGH'):
        EngineerIssue.objects.create(
            title=f"Inspeksi: {ins.machine.code} — {payload.severity}",
            description=payload.notes or payload.recommendation,
            source_type='INSPECTION',
            priority=payload.severity,
            machine_id=payload.machine_id,
            field_inspection=ins,
            assigned_to=request.user,
            created_by=request.user,
        )

    return {"status": "success", "data": {"id": ins.id, "status": ins.status}}


@engineer_router.post("/inspections/{inspection_id}/photo/")
def upload_inspection_photo(request, inspection_id: int, file: UploadedFile = File(...)):
    err = _auth_or_401(request)
    if err:
        return err
    ins = get_object_or_404(FieldInspection, id=inspection_id)
    ins.photo = file
    ins.save(update_fields=['photo'])
    return {"status": "success", "photo_url": ins.photo.url}


# ── Spare Parts ──────────────────────────────────────────────────────────────

@engineer_router.get("/spare-parts/")
def list_spare_parts(request, low_stock_only: bool = False):
    err = _auth_or_401(request)
    if err:
        return err
    qs = SparePart.objects.filter(is_active=True).prefetch_related('machines')
    if low_stock_only:
        qs = qs.filter(stock_quantity__lte=F('min_stock'))
    return {
        "status": "success",
        "data": [
            {
                "id": sp.id,
                "name": sp.name,
                "part_number": sp.part_number,
                "description": sp.description,
                "location": sp.location,
                "stock_quantity": sp.stock_quantity,
                "min_stock": sp.min_stock,
                "unit": sp.unit,
                "is_low_stock": sp.is_low_stock,
                "machines": [_machine_brief(m) for m in sp.machines.all()],
            }
            for sp in qs
        ],
    }


@engineer_router.post("/spare-parts/")
def create_spare_part(request, payload: SparePartCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    sp = SparePart.objects.create(
        name=payload.name,
        part_number=payload.part_number,
        description=payload.description,
        location=payload.location,
        stock_quantity=payload.stock_quantity,
        min_stock=payload.min_stock,
        unit=payload.unit,
    )
    if payload.machine_ids:
        sp.machines.set(payload.machine_ids)
    return {"status": "success", "data": {"id": sp.id, "name": sp.name}}


@engineer_router.patch("/spare-parts/{part_id}/")
def update_spare_part(request, part_id: int, payload: SparePartUpdateIn):
    err = _auth_or_401(request)
    if err:
        return err
    sp = get_object_or_404(SparePart, id=part_id)
    for field in ('name', 'part_number', 'description', 'location', 'stock_quantity', 'min_stock', 'unit', 'is_active'):
        val = getattr(payload, field, None)
        if val is not None:
            setattr(sp, field, val)
    sp.save()
    if payload.machine_ids is not None:
        sp.machines.set(payload.machine_ids)

    if sp.is_low_stock:
        existing = EngineerIssue.objects.filter(
            spare_part=sp, status__in=['OPEN', 'IN_PROGRESS', 'WAITING_PARTS']
        ).exists()
        if not existing:
            EngineerIssue.objects.create(
                title=f"Stok rendah: {sp.name}",
                description=f"Stok {sp.stock_quantity} {sp.unit}, minimum {sp.min_stock}",
                source_type='SPARE_PART',
                priority='HIGH',
                spare_part=sp,
                assigned_to=request.user,
                created_by=request.user,
            )

    return {"status": "success", "data": {"id": sp.id}}


@engineer_router.post("/spare-parts/{part_id}/usage/")
def log_spare_usage(request, part_id: int, payload: SpareUsageIn):
    err = _auth_or_401(request)
    if err:
        return err
    sp = get_object_or_404(SparePart, id=part_id)
    SparePartUsageLog.objects.create(
        spare_part=sp,
        machine_id=payload.machine_id,
        quantity=payload.quantity,
        notes=payload.notes,
        used_by=request.user,
    )
    sp.stock_quantity = max(0, sp.stock_quantity - payload.quantity)
    sp.save(update_fields=['stock_quantity', 'updated_at'])
    return {"status": "success", "stock_quantity": sp.stock_quantity}


@engineer_router.get("/spare-parts/{part_id}/usage/")
def list_spare_usage(request, part_id: int):
    err = _auth_or_401(request)
    if err:
        return err
    logs = SparePartUsageLog.objects.filter(spare_part_id=part_id).select_related('machine', 'used_by')
    return {
        "status": "success",
        "data": [
            {
                "id": l.id,
                "quantity": l.quantity,
                "notes": l.notes,
                "machine": _machine_brief(l.machine),
                "used_by": _user_brief(l.used_by),
                "used_at": l.used_at.isoformat(),
            }
            for l in logs[:50]
        ],
    }


# ── Calculation Workbench ────────────────────────────────────────────────────

def _fetch_sensor_data(machine_id: int, start_time, end_time, parameters: dict) -> dict:
    logs = MachineMinuteLog.objects.filter(
        machine_id=machine_id,
        timestamp__gte=start_time,
        timestamp__lte=end_time,
    ).order_by('timestamp')

    raw_points = []
    calibrated_points = []
    outliers = []
    machine = Machine.objects.get(id=machine_id)

    temps = []
    for log in logs:
        raw = log.raw_temperature if log.raw_temperature is not None else log.temperature
        cal_temp = log.temperature
        ts = timezone.localtime(log.timestamp).strftime("%Y-%m-%d %H:%M")
        raw_points.append({"time": ts, "value": raw})
        calibrated_points.append({"time": ts, "value": cal_temp})
        if raw is not None:
            temps.append(cal_temp)
        if raw is not None and cal_temp is not None and abs(float(raw) - float(cal_temp)) > 5:
            outliers.append({"time": ts, "raw": raw, "calibrated": cal_temp})

    stats = {}
    if temps:
        stats = {
            "count": len(temps),
            "min": round(min(temps), 2),
            "max": round(max(temps), 2),
            "avg": round(sum(temps) / len(temps), 2),
        }

    calibration_info = None
    try:
        cal = machine.calibration
        calibration_info = {
            "a_coeff": cal.a_coeff, "b_coeff": cal.b_coeff, "c_coeff": cal.c_coeff,
            "is_active": cal.is_active,
        }
    except MachineCalibration.DoesNotExist:
        pass

    analysis = {}
    if len(logs) >= 15:
        config = BatchProcessingConfig()
        if parameters.get('k_ideal'):
            config.K_IDEAL_SEC = float(parameters['k_ideal'])
        batch_logs = []
        for log in logs:
            batch_logs.append({
                'timestamp': log.timestamp,
                'raw_temp': log.raw_temperature or log.temperature,
                'filtered_temp': log.temperature or 0,
                'gradient': log.temperature_gradient or 0,
                'state': log.thermal_state or 'UNKNOWN',
            })
        peak_temp = max(l['filtered_temp'] for l in batch_logs)
        raw_analysis = analyze_batch_details(batch_logs, peak_temp, config)
        for k, v in raw_analysis.items():
            if hasattr(v, 'isoformat'):
                analysis[k] = v.isoformat()
            elif isinstance(v, float):
                analysis[k] = round(v, 3)
            else:
                analysis[k] = v

    return {
        "stats": stats,
        "calibration": calibration_info,
        "raw_series": raw_points[::max(1, len(raw_points)//200)],
        "calibrated_series": calibrated_points[::max(1, len(calibrated_points)//200)],
        "outliers": outliers[:20],
        "analysis": analysis,
        "log_count": logs.count(),
    }


@engineer_router.get("/calculations/")
def list_calculations(request):
    err = _auth_or_401(request)
    if err:
        return err
    sessions = CalculationSession.objects.select_related('machine', 'created_by').order_by('-updated_at')[:50]
    return {
        "status": "success",
        "data": [
            {
                "id": s.id, "title": s.title, "status": s.status,
                "machine": _machine_brief(s.machine),
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ],
    }


@engineer_router.post("/calculations/")
def create_calculation(request, payload: CalcSessionCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    start = datetime.fromisoformat(payload.start_time.replace('Z', '+00:00'))
    end = datetime.fromisoformat(payload.end_time.replace('Z', '+00:00'))
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)

    session = CalculationSession.objects.create(
        title=payload.title,
        machine_id=payload.machine_id,
        start_time=start,
        end_time=end,
        parameters=payload.parameters,
        created_by=request.user,
    )
    return {"status": "success", "data": {"id": session.id, "title": session.title}}


@engineer_router.get("/calculations/{session_id}/")
def get_calculation(request, session_id: int):
    err = _auth_or_401(request)
    if err:
        return err
    session = get_object_or_404(CalculationSession, id=session_id)
    return {
        "status": "success",
        "data": {
            "id": session.id,
            "title": session.title,
            "status": session.status,
            "machine": _machine_brief(session.machine),
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat(),
            "parameters": session.parameters,
            "results": session.results,
        },
    }


@engineer_router.post("/calculations/{session_id}/run/")
def run_calculation(request, session_id: int, payload: CalcRunIn):
    err = _auth_or_401(request)
    if err:
        return err
    session = get_object_or_404(CalculationSession, id=session_id)
    params = {**session.parameters, **payload.parameters}
    results = _fetch_sensor_data(session.machine_id, session.start_time, session.end_time, params)
    session.parameters = params
    session.results = results
    session.save(update_fields=['parameters', 'results', 'updated_at'])
    return {"status": "success", "data": results}


@engineer_router.patch("/calculations/{session_id}/")
def update_calculation(request, session_id: int, payload: CalcSessionUpdateIn):
    err = _auth_or_401(request)
    if err:
        return err
    session = get_object_or_404(CalculationSession, id=session_id)
    if payload.title is not None:
        session.title = payload.title
    if payload.parameters is not None:
        session.parameters = payload.parameters
    if payload.results is not None:
        session.results = payload.results
    if payload.status is not None:
        session.status = payload.status
    session.save()
    return {"status": "success", "data": {"id": session.id, "status": session.status}}


# ── Meetings & Action Items ──────────────────────────────────────────────────

@engineer_router.get("/meetings/")
def list_meetings(request):
    err = _auth_or_401(request)
    if err:
        return err
    meetings = MeetingNote.objects.select_related('created_by').order_by('-meeting_date')[:50]
    return {
        "status": "success",
        "data": [
            {
                "id": m.id, "title": m.title,
                "meeting_date": m.meeting_date.isoformat(),
                "participants": m.participants,
                "agenda": m.agenda,
                "notes": m.notes,
                "action_count": m.action_items.count(),
                "created_by": _user_brief(m.created_by),
            }
            for m in meetings
        ],
    }


@engineer_router.post("/meetings/")
def create_meeting(request, payload: MeetingCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    meeting = MeetingNote.objects.create(
        title=payload.title,
        meeting_date=datetime.strptime(payload.meeting_date, "%Y-%m-%d").date(),
        participants=payload.participants,
        agenda=payload.agenda,
        notes=payload.notes,
        created_by=request.user,
    )
    return {"status": "success", "data": {"id": meeting.id, "title": meeting.title}}


@engineer_router.get("/meetings/{meeting_id}/")
def get_meeting(request, meeting_id: int):
    err = _auth_or_401(request)
    if err:
        return err
    meeting = get_object_or_404(MeetingNote, id=meeting_id)
    actions = meeting.action_items.select_related('assignee', 'machine')
    return {
        "status": "success",
        "data": {
            "id": meeting.id,
            "title": meeting.title,
            "meeting_date": meeting.meeting_date.isoformat(),
            "participants": meeting.participants,
            "agenda": meeting.agenda,
            "notes": meeting.notes,
            "action_items": [
                {
                    "id": a.id, "description": a.description,
                    "status": a.status, "due_date": a.due_date.isoformat() if a.due_date else None,
                    "assignee": _user_brief(a.assignee),
                    "machine": _machine_brief(a.machine),
                }
                for a in actions
            ],
        },
    }


@engineer_router.get("/action-items/")
def list_action_items(request, status: Optional[str] = None, mine_only: bool = False):
    err = _auth_or_401(request)
    if err:
        return err
    qs = ActionItem.objects.select_related('assignee', 'machine', 'meeting')
    if status:
        qs = qs.filter(status=status)
    if mine_only:
        qs = qs.filter(assignee=request.user)
    return {
        "status": "success",
        "data": [
            {
                "id": a.id, "description": a.description, "status": a.status,
                "due_date": a.due_date.isoformat() if a.due_date else None,
                "assignee": _user_brief(a.assignee),
                "machine": _machine_brief(a.machine),
                "meeting_id": a.meeting_id,
                "meeting_title": a.meeting.title if a.meeting else None,
            }
            for a in qs[:100]
        ],
    }


@engineer_router.post("/action-items/")
def create_action_item(request, payload: ActionItemCreateIn):
    err = _auth_or_401(request)
    if err:
        return err
    due = None
    if payload.due_date:
        due = datetime.strptime(payload.due_date, "%Y-%m-%d").date()

    item = ActionItem.objects.create(
        meeting_id=payload.meeting_id,
        description=payload.description,
        assignee_id=payload.assignee_id or request.user.id,
        due_date=due,
        machine_id=payload.machine_id,
    )

    if payload.create_issue:
        issue = EngineerIssue.objects.create(
            title=f"Action: {payload.description[:100]}",
            description=payload.description,
            source_type='MEETING',
            machine_id=payload.machine_id,
            assigned_to_id=payload.assignee_id or request.user.id,
            created_by=request.user,
            due_date=due,
        )
        item.engineer_issue = issue
        item.save(update_fields=['engineer_issue'])

    return {"status": "success", "data": {"id": item.id}}


@engineer_router.patch("/action-items/{item_id}/")
def update_action_item(request, item_id: int, payload: ActionItemUpdateIn):
    err = _auth_or_401(request)
    if err:
        return err
    item = get_object_or_404(ActionItem, id=item_id)
    if payload.description is not None:
        item.description = payload.description
    if payload.assignee_id is not None:
        item.assignee_id = payload.assignee_id
    if payload.due_date is not None:
        item.due_date = datetime.strptime(payload.due_date, "%Y-%m-%d").date() if payload.due_date else None
    if payload.status is not None:
        item.status = payload.status
        if payload.status == 'DONE':
            item.completed_at = timezone.now()
    item.save()
    return {"status": "success", "data": {"id": item.id, "status": item.status}}


@engineer_router.get("/users/")
def list_users(request):
    err = _auth_or_401(request)
    if err:
        return err
    users = User.objects.filter(is_active=True).order_by('username')
    return {
        "status": "success",
        "data": [{"id": u.id, "username": u.username} for u in users],
    }
