"""
API Perencanaan Produksi (drag board Heat/Hold/Cool per mesin AUTO,
Running on/off per mesin MANUAL).
"""
from datetime import datetime, timedelta
from collections import defaultdict

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional

from monitoring.models import (
    Machine,
    MachineGroup,
    ProductionPlan,
    ProductionPlanBatch,
    ProductionPlanBlock,
    ProgramMaster,
)
from monitoring.decorators import user_can_access_page
from monitoring.utils.shift_time import TOTAL_BUCKETS, hour_axis_labels, minutes_to_pct
from monitoring.utils.steam_calc import (
    compute_carryover_blocks,
    compute_carryover_steam_contribution,
    compute_steam_timeline_from_plan_batches,
)

planning_router = Router(tags=["Production Planning"])
PAGE_CODE = "production_planning"

AUTO_PHASES = ["HEAT", "STEADY", "COOL"]


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


class BlockIn(Schema):
    phase: str
    duration_minutes: int


class BatchIn(Schema):
    machine_code: str
    label: str = ""
    start_offset_minutes: int
    blocks: List[BlockIn]
    client_id: Optional[str] = None
    program_id: Optional[int] = None


class PlanUpdateIn(Schema):
    version: int
    name: str = ""
    notes: str = ""
    batches: List[BatchIn]


class PlanCreateIn(Schema):
    shift_date: str
    name: str = ""
    notes: str = ""


class DuplicateIn(Schema):
    shift_date: str
    name: str = ""


def _validate_batch_structure(batch: BatchIn, machine) -> int:
    """
    Validasi satu batch (rentang offset, struktur fase per operation_mode, durasi).
    TIDAK cek overlap (itu tanggung jawab pemanggil, beda konteks antara bulk-save vs
    single-batch patch). Return total_minutes kalau valid, raise HttpError kalau tidak.
    """
    if batch.start_offset_minutes < 0 or batch.start_offset_minutes >= TOTAL_BUCKETS:
        raise HttpError(400, f"start_offset_minutes di luar rentang: {batch.machine_code}")

    mode = machine.operation_mode or "AUTO"

    if mode == "AUTO":
        if len(batch.blocks) != 3:
            raise HttpError(
                400,
                f"Mesin AUTO {batch.machine_code} wajib tepat 3 fase (Heat/Hold/Cool)",
            )
        for i, block in enumerate(batch.blocks):
            if block.phase != AUTO_PHASES[i]:
                raise HttpError(
                    400,
                    f"Urutan fase AUTO harus HEAT, STEADY, COOL "
                    f"(dapat {block.phase} di posisi {i})",
                )
            if block.duration_minutes < 0:
                raise HttpError(400, "duration_minutes tidak boleh negatif")
        if batch.program_id is not None:
            if not ProgramMaster.objects.filter(pk=batch.program_id).exists():
                raise HttpError(400, f"ProgramMaster id={batch.program_id} tidak ditemukan")
    elif mode == "MANUAL":
        if len(batch.blocks) != 1 or batch.blocks[0].phase != "RUNNING":
            raise HttpError(
                400,
                f"Mesin MANUAL {batch.machine_code} wajib tepat 1 fase RUNNING",
            )
        if batch.blocks[0].duration_minutes < 0:
            raise HttpError(400, "duration_minutes tidak boleh negatif")
        if batch.program_id is not None:
            raise HttpError(400, f"Mesin MANUAL {batch.machine_code} tidak boleh punya program_id")
    else:
        raise HttpError(400, f"operation_mode tidak dikenal: {mode}")

    total = sum(b.duration_minutes for b in batch.blocks)
    if total <= 0:
        raise HttpError(400, f"Total durasi batch harus > 0: {batch.machine_code}")
    if total > TOTAL_BUCKETS:
        # Batch tunggal > 24 jam dianggap anomali data, bukan overflow wajar ke hari
        # berikutnya. start_offset + total BOLEH > TOTAL_BUCKETS (meluber ke shift
        # berikutnya) -- lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md Bagian II.
        raise HttpError(
            400,
            f"Durasi batch {batch.machine_code} melebihi 24 jam ({total} menit) — kemungkinan data anomali",
        )
    return total


def _validate_batches_payload(batches: List[BatchIn], machine_by_code: dict):
    """Validasi overlap, batas shift, struktur fase per operation_mode. Raises HttpError."""
    by_machine = defaultdict(list)

    for batch in batches:
        machine = machine_by_code.get(batch.machine_code)
        if not machine:
            raise HttpError(400, f"Mesin tidak ditemukan: {batch.machine_code}")
        total = _validate_batch_structure(batch, machine)
        by_machine[batch.machine_code].append(
            (batch.start_offset_minutes, batch.start_offset_minutes + total)
        )

    for code, ranges in by_machine.items():
        ranges.sort()
        for i in range(1, len(ranges)):
            prev_end = ranges[i - 1][1]
            curr_start = ranges[i][0]
            if curr_start < prev_end:
                raise HttpError(400, f"Overlap batch pada mesin {code}")


def _check_single_batch_overlap(plan, machine_code, start, total, exclude_batch_id=None):
    """Cek overlap 1 batch terhadap sibling-nya di plan yang SAMA (dipakai oleh patch_batch)."""
    end = start + total
    siblings = (
        plan.batches.filter(machine__code=machine_code)
        .exclude(pk=exclude_batch_id)
        .prefetch_related("blocks")
    )
    ranges = [(start, end)]
    for s in siblings:
        s_total = sum(b.duration_minutes for b in s.blocks.all())
        ranges.append((s.start_offset_minutes, s.start_offset_minutes + s_total))
    ranges.sort()
    for i in range(1, len(ranges)):
        if ranges[i][0] < ranges[i - 1][1]:
            raise HttpError(400, f"Overlap batch pada mesin {machine_code} (plan sumber)")


def _pick_plan_for_date(shift_date, exclude_plan_id=None):
    """
    Pilih 1 plan 'representatif' untuk shift_date tertentu (dipakai untuk cari plan hari
    sebelumnya, sumber carryover). Prioritas: PUBLISHED, kalau tidak ada pakai yang paling baru
    diupdate. Semua status ikut dipertimbangkan (bukan cuma PUBLISHED) sesuai keputusan produk.
    """
    candidates = list(
        ProductionPlan.objects.filter(shift_date=shift_date)
        .exclude(pk=exclude_plan_id)
        .order_by("-updated_at")
    )
    if not candidates:
        return None
    published = [p for p in candidates if p.status == "PUBLISHED"]
    return published[0] if published else candidates[0]


def _serialize_plan(plan: ProductionPlan):
    """Bangun response detail plan + steam_preview. Prefetch wajib."""
    batches = list(
        plan.batches.select_related("machine", "machine__group", "program")
        .prefetch_related("blocks")
        .order_by("machine__group__code", "machine__code", "start_offset_minutes")
    )

    steam_usage = {
        b.machine_id: float(b.machine.average_steam_usage or 0) for b in batches
    }
    steam_preview = compute_steam_timeline_from_plan_batches(batches, steam_usage)

    # Carryover: batch overflow dari plan HARI SEBELUMNYA yang "meluber" ke plan ini --
    # ditampilkan sebagai batch editable di offset 0+, ikut disumbangkan ke steam_preview.
    # Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
    prev_plan = _pick_plan_for_date(plan.shift_date - timedelta(days=1), exclude_plan_id=plan.id)
    carryover_by_machine = {}
    if prev_plan:
        prev_batches = list(
            prev_plan.batches.select_related("machine").prefetch_related("blocks")
        )
        carryover_by_machine = compute_carryover_blocks(prev_batches)
        if carryover_by_machine:
            carryover_values = compute_carryover_steam_contribution(carryover_by_machine)
            combined = [
                round((a or 0) + (b or 0), 1)
                for a, b in zip(steam_preview["values"], carryover_values)
            ]
            steam_preview = {
                "values": combined,
                "max_kg_h": max(combined) if combined else 0.0,
                "unit": steam_preview.get("unit", "kg/h"),
            }

    all_machines = list(
        Machine.objects.filter(is_active=True)
        .select_related("group")
        .order_by("group__code", "code")
    )
    batches_by_machine = defaultdict(list)
    for batch in batches:
        blocks_payload = []
        cursor = batch.start_offset_minutes
        for block in batch.blocks.all():
            dur = block.duration_minutes
            blocks_payload.append({
                "phase": block.phase,
                "sequence": block.sequence,
                "duration_minutes": dur,
                "start_pct": minutes_to_pct(cursor),
                "width_pct": minutes_to_pct(dur) if dur > 0 else 0.0,
            })
            cursor += dur
        batches_by_machine[batch.machine.code].append({
            "id": batch.id,
            "label": batch.label,
            "start_offset_minutes": batch.start_offset_minutes,
            "program_id": batch.program_id,
            "program_name": batch.program.nama if batch.program_id else None,
            "blocks": blocks_payload,
            "is_continuation": False,
        })

    # Sisipkan continuation di DEPAN list batch per mesin (tampil paling kiri/pagi).
    for machine_code, entries in carryover_by_machine.items():
        continuation_payloads = []
        for entry in entries:
            blocks_payload = []
            cursor = 0
            for block in entry["tail_blocks"]:
                dur = block["duration_minutes"]
                blocks_payload.append({
                    "phase": block["phase"],
                    "sequence": len(blocks_payload),
                    "duration_minutes": dur,
                    "start_pct": minutes_to_pct(cursor),
                    "width_pct": minutes_to_pct(dur) if dur > 0 else 0.0,
                })
                cursor += dur
            continuation_payloads.append({
                "id": entry["source_batch_id"],
                "label": entry["label"],
                "start_offset_minutes": 0,
                "program_id": None,
                "program_name": None,
                "blocks": blocks_payload,
                "is_continuation": True,
                "source_plan_id": entry["source_plan_id"],
                "source_plan_version": prev_plan.version,
                "source_start_offset_minutes": entry["source_start_offset_minutes"],
                "source_blocks": entry["source_blocks"],
            })
        batches_by_machine[machine_code] = continuation_payloads + batches_by_machine.get(machine_code, [])

    group_map = defaultdict(list)
    for machine in all_machines:
        group_name = machine.group.name if machine.group else "Lain-lain"
        group_map[group_name].append({
            "code": machine.code,
            "name": machine.name,
            "average_steam_usage": float(machine.average_steam_usage or 0),
            "operation_mode": machine.operation_mode or "AUTO",
            "batches": batches_by_machine.get(machine.code, []),
        })

    groups = [
        {"group_name": gname, "machines": machines}
        for gname, machines in sorted(group_map.items())
    ]

    return {
        "id": plan.id,
        "version": plan.version,
        "shift_date": plan.shift_date.isoformat(),
        "name": plan.name,
        "notes": plan.notes,
        "status": plan.status,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        "time_labels": hour_axis_labels(),
        "steam_preview": steam_preview,
        "groups": groups,
        "conflicts": [],
    }


@planning_router.get("/meta")
def get_planning_meta(request):
    _require_permission(request)
    all_groups = MachineGroup.objects.filter(machine__is_active=True).distinct().order_by("code")
    all_machines = Machine.objects.filter(is_active=True).select_related("group").order_by(
        "group__code", "code"
    )
    programs = ProgramMaster.objects.all().order_by("nama")
    return {
        "groups": [{"code": g.code, "name": g.name} for g in all_groups],
        "machines": [
            {
                "code": m.code,
                "name": m.name,
                "group": m.group.code if m.group else None,
                "average_steam_usage": float(m.average_steam_usage or 0),
                "operation_mode": m.operation_mode or "AUTO",
            }
            for m in all_machines
        ],
        "programs": [
            {
                "id": p.id,
                "nama": p.nama,
                "suhu_max": p.suhu_max,
                "durasi_heating_ideal": p.durasi_heating_ideal,
                "durasi_keeping_ideal": p.durasi_keeping_ideal,
                "durasi_cooling_ideal": p.durasi_cooling_ideal,
            }
            for p in programs
        ],
        "grid_minutes": 15,
        "shift_minutes": TOTAL_BUCKETS,
    }


@planning_router.get("/plans")
def list_plans(request, shift_date: str = None):
    _require_permission(request)
    qs = ProductionPlan.objects.all()
    if shift_date:
        try:
            d = datetime.strptime(shift_date, "%Y-%m-%d").date()
        except ValueError:
            raise HttpError(400, "Format shift_date harus YYYY-MM-DD")
        qs = qs.filter(shift_date=d)
    qs = qs.order_by("-shift_date", "-created_at")[:50]
    return {
        "results": [
            {
                "id": p.id,
                "shift_date": p.shift_date.isoformat(),
                "name": p.name,
                "status": p.status,
                "version": p.version,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in qs
        ]
    }


@planning_router.post("/plans")
def create_plan(request, payload: PlanCreateIn):
    _require_permission(request)
    try:
        shift_date = datetime.strptime(payload.shift_date, "%Y-%m-%d").date()
    except ValueError:
        raise HttpError(400, "Format shift_date harus YYYY-MM-DD")

    name = payload.name.strip() or f"Rencana {shift_date.isoformat()}"
    plan = ProductionPlan.objects.create(
        shift_date=shift_date,
        name=name,
        notes=payload.notes or "",
        status="DRAFT",
        created_by=request.user,
        updated_by=request.user,
    )
    return _serialize_plan(plan)


@planning_router.get("/plans/{plan_id}")
def get_plan(request, plan_id: int):
    _require_permission(request)
    plan = get_object_or_404(ProductionPlan, pk=plan_id)
    return _serialize_plan(plan)


@planning_router.put("/plans/{plan_id}")
def update_plan(request, plan_id: int, payload: PlanUpdateIn):
    _require_permission(request)
    plan = get_object_or_404(ProductionPlan, pk=plan_id)

    if plan.version != payload.version:
        raise HttpError(
            409,
            "Rencana sudah diubah pihak lain. Muat ulang lalu coba lagi.",
        )

    machine_codes = {b.machine_code for b in payload.batches}

    with transaction.atomic():
        # Lock mesin yang terlibat agar operation_mode tidak berubah di tengah validasi/write
        locked = list(
            Machine.objects.select_for_update().filter(
                is_active=True,
                code__in=machine_codes,
            )
        ) if machine_codes else []
        # Juga butuh semua mesin aktif untuk lookup, tapi lock hanya yang di payload
        machine_by_code = {
            m.code: m for m in Machine.objects.filter(is_active=True)
        }
        # Refresh locked instances into map
        for m in locked:
            machine_by_code[m.code] = m

        _validate_batches_payload(payload.batches, machine_by_code)

        plan.batches.all().delete()
        for idx, batch_in in enumerate(payload.batches):
            machine = machine_by_code[batch_in.machine_code]
            program = None
            if machine.operation_mode == "AUTO" and batch_in.program_id:
                program = ProgramMaster.objects.filter(pk=batch_in.program_id).first()
            batch = ProductionPlanBatch.objects.create(
                plan=plan,
                machine=machine,
                program=program,
                label=batch_in.label or "",
                order=idx,
                start_offset_minutes=batch_in.start_offset_minutes,
            )
            for seq, block_in in enumerate(batch_in.blocks):
                ProductionPlanBlock.objects.create(
                    batch=batch,
                    phase=block_in.phase,
                    sequence=seq,
                    duration_minutes=block_in.duration_minutes,
                )

        plan.name = payload.name if payload.name is not None else plan.name
        plan.notes = payload.notes if payload.notes is not None else plan.notes
        plan.version = plan.version + 1
        plan.updated_by = request.user
        plan.save(update_fields=["name", "notes", "version", "updated_by", "updated_at"])

    plan.refresh_from_db()
    return _serialize_plan(plan)


@planning_router.post("/plans/{plan_id}/publish")
def publish_plan(request, plan_id: int):
    _require_permission(request)
    plan = get_object_or_404(ProductionPlan, pk=plan_id)
    if plan.status == "ARCHIVED":
        raise HttpError(400, "Rencana yang diarsipkan tidak bisa dipublish")
    plan.status = "PUBLISHED"
    plan.updated_by = request.user
    plan.version = plan.version + 1
    plan.save(update_fields=["status", "updated_by", "version", "updated_at"])
    return _serialize_plan(plan)


@planning_router.delete("/plans/{plan_id}")
def delete_plan(request, plan_id: int):
    _require_permission(request)
    plan = get_object_or_404(ProductionPlan, pk=plan_id)
    if plan.status == "PUBLISHED":
        raise HttpError(400, "Hapus hanya diizinkan untuk status DRAFT (atau arsipkan dulu)")
    plan_id_out = plan.id
    plan.delete()
    return {"ok": True, "id": plan_id_out}


@planning_router.post("/plans/{plan_id}/duplicate")
def duplicate_plan(request, plan_id: int, payload: DuplicateIn):
    _require_permission(request)
    source = get_object_or_404(
        ProductionPlan.objects.prefetch_related(
            "batches__blocks", "batches__machine", "batches__program"
        ),
        pk=plan_id,
    )
    try:
        shift_date = datetime.strptime(payload.shift_date, "%Y-%m-%d").date()
    except ValueError:
        raise HttpError(400, "Format shift_date harus YYYY-MM-DD")

    name = payload.name.strip() or f"Copy of {source.name or source.shift_date}"
    with transaction.atomic():
        new_plan = ProductionPlan.objects.create(
            shift_date=shift_date,
            name=name,
            notes=source.notes,
            status="DRAFT",
            created_by=request.user,
            updated_by=request.user,
        )
        for batch in source.batches.all():
            new_batch = ProductionPlanBatch.objects.create(
                plan=new_plan,
                machine=batch.machine,
                program=batch.program,
                label=batch.label,
                order=batch.order,
                start_offset_minutes=batch.start_offset_minutes,
            )
            for block in batch.blocks.all():
                ProductionPlanBlock.objects.create(
                    batch=new_batch,
                    phase=block.phase,
                    sequence=block.sequence,
                    duration_minutes=block.duration_minutes,
                )
    return _serialize_plan(new_plan)


class BatchPatchIn(Schema):
    version: int  # version PLAN SUMBER (hari sebelumnya), bukan plan yg sedang dibuka
    label: str = ""
    start_offset_minutes: int
    blocks: List[BlockIn]
    program_id: Optional[int] = None


@planning_router.patch("/batches/{batch_id}")
def patch_batch(request, batch_id: int, payload: BatchPatchIn):
    """
    Edit SATU batch langsung by id, lintas-plan. Dipakai board untuk mengedit batch
    "continuation" (proses overflow dari plan hari sebelumnya) langsung dari board hari ini,
    tanpa perlu berpindah ke plan sumbernya. Lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §10.
    """
    _require_permission(request)
    batch = get_object_or_404(
        ProductionPlanBatch.objects.select_related("plan", "machine"), pk=batch_id
    )
    plan = batch.plan

    if plan.version != payload.version:
        raise HttpError(
            409,
            "Plan sumber (hari sebelumnya) sudah diubah pihak lain. Muat ulang lalu coba lagi.",
        )

    with transaction.atomic():
        machine = Machine.objects.select_for_update().get(pk=batch.machine_id)
        batch_in = BatchIn(
            machine_code=machine.code,
            label=payload.label,
            start_offset_minutes=payload.start_offset_minutes,
            blocks=payload.blocks,
            program_id=payload.program_id,
        )
        total = _validate_batch_structure(batch_in, machine)
        _check_single_batch_overlap(
            plan, machine.code, payload.start_offset_minutes, total, exclude_batch_id=batch.id
        )

        program = None
        if machine.operation_mode == "AUTO" and payload.program_id:
            program = ProgramMaster.objects.filter(pk=payload.program_id).first()

        batch.label = payload.label or ""
        batch.start_offset_minutes = payload.start_offset_minutes
        batch.program = program
        batch.save(update_fields=["label", "start_offset_minutes", "program"])

        batch.blocks.all().delete()
        for seq, block_in in enumerate(payload.blocks):
            ProductionPlanBlock.objects.create(
                batch=batch,
                phase=block_in.phase,
                sequence=seq,
                duration_minutes=block_in.duration_minutes,
            )

        plan.version = plan.version + 1
        plan.updated_by = request.user
        plan.save(update_fields=["version", "updated_by", "updated_at"])

    return {"ok": True, "plan_id": plan.id, "plan_version": plan.version}


@planning_router.delete("/batches/{batch_id}")
def delete_batch(request, batch_id: int, version: int):
    """Hapus SATU batch by id, lintas-plan (dipakai utk hapus continuation dari board hari ini)."""
    _require_permission(request)
    batch = get_object_or_404(ProductionPlanBatch.objects.select_related("plan"), pk=batch_id)
    plan = batch.plan

    if plan.version != version:
        raise HttpError(
            409,
            "Plan sumber (hari sebelumnya) sudah diubah pihak lain. Muat ulang lalu coba lagi.",
        )

    with transaction.atomic():
        batch.delete()
        plan.version = plan.version + 1
        plan.updated_by = request.user
        plan.save(update_fields=["version", "updated_by", "updated_at"])

    return {"ok": True, "plan_id": plan.id, "plan_version": plan.version}
