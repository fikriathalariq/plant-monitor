"""
JUMO Live Monitor — baca Modbus langsung untuk diagnosa channel/controller.

- Tidak menyimpan ke DB
- Tidak mengubah jumo_realtime.py
- Cache + lock agar tidak membombardir perangkat yang sama dengan jumo_realtime
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from typing import Any, Dict, List, Optional

from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from pymodbus.client import ModbusTcpClient

from monitoring.services.jumo_config import (
    JUMO_PORT,
    load_active_devices_config,
    read_all_ai_safe,
    sanitize_values,
)
from monitoring.models import Machine
from monitoring.decorators import user_can_access_page
from monitoring.utils.signal_freshness import (
    STATUS_NO_SIGNAL,
    get_machine_display_status,
    is_signal_stale,
)

jumo_live_router = Router(tags=["JUMO Live"])

PAGE_CODE = "jumo_live_monitor"

# Timeout pendek: cukup untuk LAN, cepat lepas jika device hang
# agar tidak menahan socket lama saat jumo_realtime juga polling.
MODBUS_TIMEOUT_SEC = 1.5
CACHE_TTL_SEC = 5.0
MAX_WORKERS = 4

# Batas waktu TOTAL untuk satu batch (semua controller), terlepas dari apakah
# pymodbus benar-benar menghormati MODBUS_TIMEOUT_SEC per socket atau tidak.
# Ini mencegah satu controller yang "hang" (connect diterima tapi tidak pernah
# membalas) menyandera thread request selama puluhan detik.
BATCH_DEADLINE_SEC = 4.0

# Thread pool PERSISTEN (dibuat sekali, dipakai ulang di setiap request).
# Kalau kita pakai `with ThreadPoolExecutor(...)` per-request, keluar dari
# blok `with` akan tetap menunggu SEMUA thread selesai (termasuk yang hang),
# sehingga request tetap tersandera walau kita sudah "give up" menunggu.
# Dengan pool persisten, thread yang macet cukup dibiarkan berjalan di
# background tanpa menahan thread Waitress yang melayani request ini.
_poll_pool = ThreadPoolExecutor(
    max_workers=MAX_WORKERS, thread_name_prefix="jumo-live-poll"
)

_cache_lock = threading.Lock()
_inflight_lock = threading.Lock()
_inflight_event: Optional[threading.Event] = None
_cache: Dict[str, Any] = {
    "payload": None,
    "fetched_at": 0.0,
}


def _timeout_result(dev: dict) -> dict:
    """Hasil placeholder untuk controller yang belum selesai dibaca saat batch deadline habis."""
    channels_cfg = list(dev.get("channels") or [])
    num_ai = int(dev.get("num_ai") or 0)
    return {
        "name": dev["name"],
        "ip": dev["ip"],
        "ok": False,
        "error": f"Timeout keseluruhan batch (> {BATCH_DEADLINE_SEC:.0f}s, device tidak merespons)",
        "latency_ms": None,
        "num_ai": num_ai,
        "channel_count": len(channels_cfg),
        "ai_mismatch": bool(num_ai and len(channels_cfg) and num_ai != len(channels_cfg)),
        "channels": [
            {"index": i, "code": code, "live_value": None}
            for i, code in enumerate(channels_cfg)
        ],
    }


def _require_login(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


def _poll_controller(dev: dict) -> dict:
    """Baca satu controller; selalu tutup koneksi di finally."""
    label = f"{dev['name']} ({dev['ip']})"
    started = time.perf_counter()
    channels_cfg = list(dev.get("channels") or [])
    num_ai = int(dev.get("num_ai") or 0)
    result = {
        "name": dev["name"],
        "ip": dev["ip"],
        "ok": False,
        "error": None,
        "latency_ms": None,
        "num_ai": num_ai,
        "channel_count": len(channels_cfg),
        "ai_mismatch": bool(num_ai and len(channels_cfg) and num_ai != len(channels_cfg)),
        "channels": [],
    }

    client = ModbusTcpClient(dev["ip"], port=dev.get("port", JUMO_PORT), timeout=MODBUS_TIMEOUT_SEC)
    live_values: Optional[List[Optional[float]]] = None
    try:
        if not client.connect():
            result["error"] = "Gagal connect"
            return result
        raw_values, err = read_all_ai_safe(client, dev, label)
        if err:
            result["error"] = err
            return result
        live_values = sanitize_values(raw_values)
        result["ok"] = True
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    finally:
        try:
            client.close()
        except Exception:
            pass
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)

    # Bangun baris channel (nilai live saja; enrichment DB di layer luar)
    for i, code in enumerate(channels_cfg):
        live = None
        if live_values is not None and i < len(live_values):
            live = live_values[i]
        result["channels"].append(
            {
                "index": i,
                "code": code,
                "live_value": round(live, 2) if isinstance(live, (int, float)) else None,
            }
        )
    return result


def _enrich_with_db(controllers: List[dict], now) -> None:
    codes = {ch["code"] for c in controllers for ch in c.get("channels") or []}
    machines = {
        m.code: m
        for m in Machine.objects.filter(code__in=codes).select_related("group")
    }

    for ctrl in controllers:
        for ch in ctrl.get("channels") or []:
            issues: List[str] = []
            m = machines.get(ch["code"])
            mapped = m is not None
            ch["mapped"] = mapped

            if not mapped:
                issues.append("UNMAPPED_MACHINE")
                ch["db_temperature"] = None
                ch["db_last_valid_reading_at"] = None
                ch["db_status"] = None
                ch["is_stale"] = False
                ch["machine_id"] = None
                ch["machine_name"] = None
                ch["group"] = None
                ch["average_steam_usage"] = None
                ch["nominal_power"] = None
                ch["max_water_capacity"] = None
                ch["max_fabric_capacity"] = None
                ch["avg_hto_calories"] = None
            else:
                ch["machine_id"] = m.id
                ch["machine_name"] = m.name
                ch["group"] = m.group.name if m.group_id else None
                ch["average_steam_usage"] = m.average_steam_usage
                ch["nominal_power"] = m.nominal_power
                ch["max_water_capacity"] = m.max_water_capacity
                ch["max_fabric_capacity"] = m.max_fabric_capacity
                ch["avg_hto_calories"] = m.avg_hto_calories
                ch["db_temperature"] = (
                    round(m.temperature, 2) if m.temperature is not None else None
                )
                reading_at = m.last_valid_reading_at
                ch["db_last_valid_reading_at"] = (
                    timezone.localtime(reading_at).isoformat() if reading_at else None
                )
                stale = is_signal_stale(m, now=now)
                ch["is_stale"] = stale
                ch["db_status"] = (
                    STATUS_NO_SIGNAL if stale else get_machine_display_status(m, now=now)
                )
                if stale:
                    issues.append("DB_STALE")

            if not ctrl["ok"]:
                issues.append("CONTROLLER_DOWN")
            elif ch["live_value"] is None:
                issues.append("LIVE_NULL")

            if ctrl.get("ai_mismatch"):
                issues.append("AI_MISMATCH")

            ch["issues"] = issues


def _build_summary(controllers: List[dict]) -> dict:
    channels = [ch for c in controllers for ch in c.get("channels") or []]
    return {
        "controllers_ok": sum(1 for c in controllers if c.get("ok")),
        "controllers_fail": sum(1 for c in controllers if not c.get("ok")),
        "channels_total": len(channels),
        "channels_live": sum(1 for ch in channels if ch.get("live_value") is not None),
        "channels_null": sum(1 for ch in channels if ch.get("live_value") is None),
        "unmapped": sum(1 for ch in channels if not ch.get("mapped")),
        "stale": sum(1 for ch in channels if ch.get("is_stale")),
    }


def _fetch_fresh() -> dict:
    now = timezone.now()
    devices = load_active_devices_config()

    futures = {_poll_pool.submit(_poll_controller, dev): dev for dev in devices}

    # Tunggu maksimal BATCH_DEADLINE_SEC untuk SEMUA controller sekaligus.
    # Future yang belum selesai saat deadline habis TIDAK ditunggu lagi —
    # dibiarkan berjalan di background pool, tidak menahan thread ini.
    done, not_done = futures_wait(futures.keys(), timeout=BATCH_DEADLINE_SEC)

    by_name: Dict[str, dict] = {}
    for fut in done:
        dev = futures[fut]
        try:
            by_name[dev["name"]] = fut.result()
        except Exception as e:
            by_name[dev["name"]] = _timeout_result(dev) | {"error": f"Exception: {e}"}
    for fut in not_done:
        dev = futures[fut]
        by_name[dev["name"]] = _timeout_result(dev)

    controllers = [by_name[d["name"]] for d in devices if d["name"] in by_name]

    _enrich_with_db(controllers, now)

    return {
        "polled_at": timezone.localtime(now).isoformat(),
        "modbus_timeout_sec": MODBUS_TIMEOUT_SEC,
        "cache_ttl_sec": CACHE_TTL_SEC,
        "controllers": controllers,
        "summary": _build_summary(controllers),
    }


def _get_payload(force: bool = False) -> dict:
    """Single-flight + TTL cache agar refresh bersamaan tidak spam Modbus."""
    global _inflight_event

    now_mono = time.monotonic()
    with _cache_lock:
        payload = _cache["payload"]
        age = now_mono - float(_cache["fetched_at"] or 0)
        if payload is not None and not force and age < CACHE_TTL_SEC:
            out = dict(payload)
            out["cache_age_ms"] = int(age * 1000)
            out["from_cache"] = True
            return out

    # Single-flight: satu thread yang fetch, yang lain menunggu
    leader = False
    with _inflight_lock:
        if _inflight_event is None:
            _inflight_event = threading.Event()
            leader = True
        wait_event = _inflight_event

    if leader:
        try:
            fresh = _fetch_fresh()
            with _cache_lock:
                _cache["payload"] = fresh
                _cache["fetched_at"] = time.monotonic()
            out = dict(fresh)
            out["cache_age_ms"] = 0
            out["from_cache"] = False
            return out
        finally:
            with _inflight_lock:
                wait_event.set()
                _inflight_event = None
    else:
        # Dibatasi sedikit di atas BATCH_DEADLINE_SEC (bukan 30s) agar request
        # follower tidak ikut menahan thread Waitress lama-lama kalau leader
        # ternyata lambat/macet — cukup untuk satu siklus fetch + enrich DB.
        wait_event.wait(timeout=BATCH_DEADLINE_SEC + 2.0)
        with _cache_lock:
            payload = _cache["payload"]
            age = time.monotonic() - float(_cache["fetched_at"] or 0)
        if payload is None:
            raise HttpError(503, "JUMO live poll gagal / timeout")
        out = dict(payload)
        out["cache_age_ms"] = int(age * 1000)
        out["from_cache"] = True
        return out


@jumo_live_router.get("/")
def jumo_live_snapshot(request, force: bool = False):
    """
    Snapshot live semua controller JUMO (Modbus TCP).
    Query: force=true untuk bypass cache TTL (tetap single-flight).
    """
    _require_login(request)
    return _get_payload(force=bool(force))
