"""
monitoring/services/jumo_config.py

Service layer terpusat untuk konfigurasi JUMO Modbus.
Semua file yang butuh informasi tentang device/channel JUMO
harus import dari sini — BUKAN dari management.commands.jumo_realtime.

Fungsi yang tersedia:
  - load_active_devices_config()   → list[dict], untuk jumo_realtime & api_jumo_live
  - get_active_polled_machine_codes() → set[str], untuk signal_freshness & check_device_health
  - get_channel_meta()             → dict[str, dict], untuk check_device_health & telegram_commands
  - regs_to_float_jumo()           → float, konversi register Modbus ke float
  - read_all_ai_safe()             → (list|None, str|None), baca semua AI dari satu device
  - sanitize_values()              → list|None, filter nilai tidak valid
"""

import struct

# Konstanta Modbus (dipindahkan dari jumo_realtime.py)
JUMO_PORT = 502
REGS_PER_AI = 2
MAX_VALID_VALUE = 100000.0


def _parse_start_addr(raw: str) -> int:
    """
    Konversi string start_addr (hex atau decimal) ke integer.
    Validasi format sudah dilakukan di model clean(), jadi di sini tidak perlu try-except.
    Tetap diberi fallback untuk keamanan ganda.
    """
    raw = (raw or "").strip()
    try:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        return int(raw)
    except ValueError:
        raise ValueError(f"Format start_addr tidak valid: '{raw}'. Harus hex (0x1006) atau decimal (4102).")


def load_active_devices_config() -> list:
    """
    Query ke DB dan kembalikan list konfigurasi device aktif.
    Format identik dengan list DEVICES lama sehingga kompatibel
    dengan semua kode yang mengiterasi DEVICES.

    Dipakai oleh: jumo_realtime.py, api_jumo_live.py
    """
    # Import di dalam fungsi untuk mencegah circular import saat app loading
    from monitoring.models import JumoDevice

    db_devices = JumoDevice.objects.filter(is_active=True).prefetch_related("channels__machine")
    result = []

    for db_dev in db_devices:
        # Bangun list channel berdasarkan index, slot yang tidak terisi akan jadi None
        channels_list = [None] * db_dev.num_ai
        for ch in db_dev.channels.all():
            if 0 <= ch.channel_index < db_dev.num_ai:
                channels_list[ch.channel_index] = ch.machine.code if ch.machine else None

        result.append({
            "name": db_dev.name,
            "ip": db_dev.ip_address,
            "port": db_dev.port,
            "start_addr": _parse_start_addr(db_dev.start_addr),
            "device_id": db_dev.device_id,
            "num_ai": db_dev.num_ai,
            "channels": channels_list,
        })

    return result


def get_active_polled_machine_codes() -> set:
    """
    Query ke DB dan kembalikan set kode mesin yang aktif dipolling.
    Mengecualikan slot channel yang tidak di-mapping (None/blank).

    Dipakai oleh: signal_freshness.py, check_device_health.py, telegram_commands.py
    """
    from monitoring.models import JumoChannel

    return set(
        JumoChannel.objects.filter(
            machine__isnull=False,
            device__is_active=True,
        ).values_list("machine__code", flat=True)
    )


def get_channel_meta() -> dict:
    """
    Kembalikan dict {machine_code → {controller, ip, channel_index}}
    untuk keperluan formatting pesan Telegram & alert.

    Format channel_index di sini dimulai dari 1 (human-readable),
    konsisten dengan perilaku fungsi _channel_meta() lama di
    check_device_health.py dan telegram_commands.py.

    Dipakai oleh: check_device_health.py, telegram_commands.py
    """
    from monitoring.models import JumoChannel

    meta = {}
    channels = JumoChannel.objects.filter(
        machine__isnull=False,
        device__is_active=True,
    ).select_related("machine", "device")

    for ch in channels:
        meta[ch.machine.code] = {
            "controller": ch.device.name,
            "ip": ch.device.ip_address,
            "channel_index": ch.channel_index + 1,  # 1-indexed untuk display
        }
    return meta


# ─── Fungsi Modbus helper (dipindahkan dari jumo_realtime.py) ─────────────────

def regs_to_float_jumo(reg_x: int, reg_x1: int) -> float:
    """Konversi 2 register Modbus (Big Endian) ke Float 32-bit."""
    b = bytes([
        (reg_x1 >> 8) & 0xFF, (reg_x1 & 0xFF),
        (reg_x >> 8) & 0xFF, (reg_x & 0xFF),
    ])
    return struct.unpack(">f", b)[0]


def read_all_ai_safe(client, dev: dict, label: str):
    """
    Baca semua Analog Input dari satu device Modbus.
    Return: (values_list, None) jika sukses, atau (None, error_msg) jika gagal.

    Dipakai oleh: jumo_realtime.py, api_jumo_live.py
    """
    try:
        result = client.read_holding_registers(
            address=dev["start_addr"],
            count=dev["num_ai"] * REGS_PER_AI,
            device_id=dev["device_id"],
        )
    except Exception as e:
        return None, f"Exception Modbus read: {e}"

    if result is None:
        return None, "Hasil baca None"

    if hasattr(result, "isError") and result.isError():
        return None, f"Respon Modbus error: {result}"

    regs = getattr(result, "registers", None)
    if not regs or len(regs) < (dev["num_ai"] * REGS_PER_AI):
        return None, f"Register kurang/kosong. Len: {len(regs) if regs else 0}"

    values = []
    try:
        for i in range(dev["num_ai"]):
            r0 = regs[2 * i]
            r1 = regs[2 * i + 1]
            values.append(regs_to_float_jumo(r0, r1))
    except Exception as e:
        return None, f"Decode float error: {e}"

    return values, None


def sanitize_values(values: list, limit: float = MAX_VALID_VALUE):
    """
    Filter nilai yang tidak valid (di luar rentang sensor wajar).
    Nilai None di-pass-through. Nilai di luar -1000 s/d limit di-set None.

    Dipakai oleh: jumo_realtime.py, api_jumo_live.py
    """
    if values is None:
        return None
    return [v if (v is not None and -1000 < v <= limit) else None for v in values]
