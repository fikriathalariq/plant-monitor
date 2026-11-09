from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional
from django.db.models import Prefetch
from django.utils import timezone
from django.shortcuts import get_object_or_404

from monitoring.models import Machine, MachineGroup
from monitoring.decorators import user_can_access_page
from monitoring.utils.activity_logger import log_activity
from monitoring.utils.manual_status import (
    apply_manual_status_change,
    get_status_since_info,
    MANUAL_STATUS_RUNNING,
    MANUAL_STATUS_STOP,
    SOURCE_DASHBOARD_TOGGLE,
    SOURCE_MESIN_AKTIF_API,
)

machines_router = Router(tags=["Machines"])

PAGE_CODE = "manual_input"


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


class ManualUpdateSchema(Schema):
    machine_ids_on: List[int]


@machines_router.get("/manual")
def get_manual_machines(request):
    """
    Porting dari monitoring.views.manual_machine_usage (GET).
    Mengembalikan grup mesin (MANUAL + preview AUTO), dan kalkulasi total steam/HTO.
    """
    _require_permission(request)

    all_active_machines = Machine.objects.filter(is_active=True)
    manual_machines = all_active_machines.filter(operation_mode="MANUAL")

    groups = (
        MachineGroup.objects
        .filter(machine__in=all_active_machines)
        .exclude(process_type="ENERGY_SOURCE")
        .distinct()
        .prefetch_related(
            Prefetch(
                "machine_set",
                queryset=all_active_machines.order_by("operation_mode", "code"),
            )
        )
        .order_by("code")
    )

    def _group_priority(group):
        name_lower = (group.name or "").lower()
        if group.process_type == "CONTINUOUS":
            return 0
        if "gedung processing" in name_lower:
            return 1
        if "gedung printing" in name_lower:
            return 2
        return 3

    groups = sorted(groups, key=lambda g: (_group_priority(g), g.code))

    from monitoring.utils.steam_active import is_steam_active_from_machine

    total_steam = 0.0
    total_hto = 0.0
    groups_data = []
    for group in groups:
        machines_data = []
        for m in group.machine_set.all():
            is_running = is_steam_active_from_machine(m)
            if is_running:
                total_steam += (m.average_steam_usage or 0.0)
                total_hto += (m.avg_hto_calories or 0.0)

            machines_data.append({
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "steam": m.average_steam_usage or 0.0,
                "hto": m.avg_hto_calories or 0.0,
                "operation_mode": m.operation_mode,
                "is_running": is_running,
                "thermal_status": m.last_thermal_status,
                "temperature": round(m.temperature, 1) if m.temperature is not None else None,
            })
        groups_data.append({
            "code": group.code,
            "name": group.name,
            "machines": machines_data,
        })

    return {
        "groups": groups_data,
        "total_steam": round(total_steam, 1),
        "total_hto": round(total_hto, 1),
    }


@machines_router.post("/manual")
def update_manual_machines(request, payload: ManualUpdateSchema):
    """
    Porting dari monitoring.views.manual_machine_usage (POST).
    payload.machine_ids_on = daftar ID mesin MANUAL yang harus di-set Running.
    """
    _require_permission(request)

    manual_machines = Machine.objects.filter(is_active=True, operation_mode="MANUAL")
    ids_on = set(payload.machine_ids_on)

    changes = []
    for m in manual_machines:
        old_status = m.manual_status
        new_status = MANUAL_STATUS_RUNNING if m.id in ids_on else MANUAL_STATUS_STOP
        if apply_manual_status_change(m, new_status, SOURCE_MESIN_AKTIF_API, request.user):
            changes.append({"code": m.code, "name": m.name, "old": old_status, "new": new_status})

    if changes:
        change_summary = ", ".join([f"{c['code']} ({c['old']}\u2192{c['new']})" for c in changes])
        log_activity(
            request=request,
            action="UPDATE",
            description=f"Changed machine status: {change_summary}",
            additional_data={"changes": changes, "total_changed": len(changes), "operation": "machine_status_update"},
        )

    return {"success": True, "message": "Status mesin (mode manual) berhasil diperbarui.", "changed": len(changes)}


@machines_router.post("/manual/{machine_id}/toggle")
def toggle_manual_machine(request, machine_id: int):
    """Toggle satu mesin MANUAL antara Running dan Stop."""
    _require_permission(request)

    machine = get_object_or_404(Machine, id=machine_id, is_active=True)
    if machine.operation_mode != "MANUAL":
        raise HttpError(400, "Hanya mesin mode MANUAL yang dapat di-toggle.")

    old_status = machine.manual_status or MANUAL_STATUS_STOP
    new_status = MANUAL_STATUS_STOP if old_status == MANUAL_STATUS_RUNNING else MANUAL_STATUS_RUNNING

    if not apply_manual_status_change(machine, new_status, SOURCE_DASHBOARD_TOGGLE, request.user):
        since_info = get_status_since_info(machine)
        return {
            "success": True,
            "machine_id": machine.id,
            "status": machine.manual_status,
            "norm_status": "RUNNING" if machine.manual_status == MANUAL_STATUS_RUNNING else "OFF",
            "active_since": since_info.get("active_since"),
            "status_since_display": since_info.get("status_since_display"),
        }

    log_activity(
        request=request,
        action="UPDATE",
        description=f"Toggled {machine.code}: {old_status} → {new_status}",
        additional_data={
            "machine_id": machine.id,
            "code": machine.code,
            "old": old_status,
            "new": new_status,
            "operation": "machine_toggle",
        },
    )

    since_info = get_status_since_info(machine)
    return {
        "success": True,
        "machine_id": machine.id,
        "status": machine.manual_status,
        "norm_status": "RUNNING" if machine.manual_status == MANUAL_STATUS_RUNNING else "OFF",
        "active_since": since_info.get("active_since"),
        "status_since_display": since_info.get("status_since_display"),
    }
