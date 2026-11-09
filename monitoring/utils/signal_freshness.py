"""Freshness / No Signal helpers for AUTO Modbus readings."""

import time
from django.utils import timezone

# Poll interval jumo_realtime = 10s → 6 miss ≈ 60s
STALE_THRESHOLD_SECONDS = 60
STALE_AFTER_FAILURES = 6

STATUS_NO_SIGNAL = "No Signal"

_polled_codes_cache = None
_polled_codes_cache_time = 0.0
_CACHE_TTL = 30.0


def get_polled_machine_codes():
    """
    Kode mesin yang diharapkan menerima data dari jumo_realtime.
    Diambil dari DB, di-cache selama 30 detik untuk performa per-request.
    """
    global _polled_codes_cache, _polled_codes_cache_time
    now = time.time()
    
    if _polled_codes_cache is None or (now - _polled_codes_cache_time) > _CACHE_TTL:
        from monitoring.services.jumo_config import get_active_polled_machine_codes
        _polled_codes_cache = get_active_polled_machine_codes()
        _polled_codes_cache_time = now

    return _polled_codes_cache


def is_signal_stale(machine, now=None, threshold_seconds=STALE_THRESHOLD_SECONDS):
    """
    True jika mesin AUTO yang dipoll JUMO sudah lama tanpa pembacaan valid.
    last_valid_reading_at HANYA diisi jumo_realtime (bukan log_minute_history).
    """
    if getattr(machine, "operation_mode", None) != "AUTO":
        return False
    code = getattr(machine, "code", None)
    if not code or code not in get_polled_machine_codes():
        return False

    reading_at = getattr(machine, "last_valid_reading_at", None)
    if reading_at is None:
        return False

    now = now or timezone.now()
    return (now - reading_at).total_seconds() > threshold_seconds


def get_machine_display_status(machine, now=None):
    """
    Status untuk UI/API dashboard.
    Override ke 'No Signal' jika pembacaan Modbus sudah stale.
    """
    if machine.operation_mode == "MANUAL":
        return machine.manual_status or "Stop"

    if is_signal_stale(machine, now=now):
        return STATUS_NO_SIGNAL

    if machine.code in ("Oil_Temp", "Steam_Pr"):
        return machine.last_status or "Offline"

    return machine.last_thermal_status or "OFFLINE"
