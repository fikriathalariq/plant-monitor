"""Helper terpusat untuk perubahan status mesin MANUAL."""

from datetime import timedelta

from django.utils import timezone

from monitoring.models import MachineManualLog
from monitoring.utils.signal_freshness import is_signal_stale, STATUS_NO_SIGNAL

MANUAL_STATUS_RUNNING = "Running"
MANUAL_STATUS_STOP = "Stop"

SOURCE_DASHBOARD_TOGGLE = "dashboard_toggle"
SOURCE_MESIN_AKTIF_API = "mesin_aktif_api"
SOURCE_MESIN_AKTIF_VIEW = "mesin_aktif_view"
SOURCE_SYNC_COMMAND = "sync_command"


def format_status_since_display(dt):
    """Format waktu relatif: Hari ini 11:41, Kemarin 09:13, atau 08 Jul 09:13."""
    if not dt:
        return None

    local = timezone.localtime(dt)
    now = timezone.localtime()
    time_str = local.strftime("%H:%M")

    if local.date() == now.date():
        return f"Hari ini {time_str}"

    yesterday = now.date() - timedelta(days=1)
    if local.date() == yesterday:
        return f"Kemarin {time_str}"

    months = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
    return f"{local.day:02d} {months[local.month - 1]} {time_str}"


def _is_manual_inactive(status):
    return status in ("Stop", "OFF", "OFFLINE", "Offline", None, "")


def _get_manual_status_timestamp(machine):
    if machine.status_changed_at:
        return machine.status_changed_at

    latest = (
        MachineManualLog.objects
        .filter(machine=machine)
        .order_by("-timestamp")
        .values_list("timestamp", flat=True)
        .first()
    )
    return latest


def get_status_since_info(machine, active_batch=None):
    """
    Info waktu status saat ini untuk dashboard.
    Mengembalikan dict: status_since (ISO), status_since_display, is_active.
    """
    if machine.operation_mode == "MANUAL":
        status = machine.manual_status or MANUAL_STATUS_STOP
        is_active = status == MANUAL_STATUS_RUNNING
    elif is_signal_stale(machine):
        status = STATUS_NO_SIGNAL
        is_active = False
    elif machine.code in ("Oil_Temp", "Steam_Pr"):
        status = machine.last_status or "Offline"
        is_active = not _is_manual_inactive(status)
    else:
        status = machine.last_thermal_status or "OFFLINE"
        is_active = status in ("HEAT", "STEADY", "Running", "COOL")

    ts = None
    if machine.operation_mode == "MANUAL":
        ts = _get_manual_status_timestamp(machine)
    else:
        if active_batch:
            ts = active_batch.start_time
        elif machine.status_changed_at:
            ts = machine.status_changed_at

    display = format_status_since_display(ts)
    if display and machine.operation_mode == "MANUAL":
        if is_active:
            prefix = ""
        else:
            if display.startswith("Hari ini"):
                display = display.replace("Hari ini", "Mati hari ini", 1)
            elif display.startswith("Kemarin"):
                display = f"Mati {display}"
            else:
                display = f"Mati {display}"

    duration_minutes = None
    if ts and is_active:
        duration_minutes = int((timezone.now() - ts).total_seconds() // 60)

    return {
        "status_since": timezone.localtime(ts).isoformat() if ts else None,
        "status_since_display": display,
        "active_since": display if is_active else None,
        "is_active": is_active,
        "duration_minutes": duration_minutes,
    }


def apply_manual_status_change(machine, new_status, source, user=None):
    """
    Terapkan perubahan status MANUAL secara konsisten.
    Mengupdate status_changed_at dan mencatat MachineManualLog.
    Return True jika status benar-benar berubah.
    """
    old_status = machine.manual_status or MANUAL_STATUS_STOP
    if old_status == new_status:
        return False

    now = timezone.now()
    machine.manual_status = new_status
    machine.last_status = MANUAL_STATUS_RUNNING if new_status == MANUAL_STATUS_RUNNING else MANUAL_STATUS_STOP
    machine.temperature = None
    machine.temperature_gradient = None
    machine.last_update = now
    machine.previous_display_status = old_status
    machine.status_changed_at = now
    machine.save(update_fields=[
        "manual_status",
        "last_status",
        "temperature",
        "temperature_gradient",
        "last_update",
        "previous_display_status",
        "status_changed_at",
    ])

    MachineManualLog.objects.create(
        machine=machine,
        old_status=old_status,
        new_status=new_status,
        changed_by=user,
        changed_by_username=getattr(user, "username", "") or "",
        source=source,
    )
    return True
