"""
monitoring/management/commands/jumo_realtime.py

Polling JUMO Modbus secara realtime dan update tabel Machine.
Konfigurasi device (IP, address, channel mapping) diambil dari DB
melalui monitoring.services.jumo_config — bukan hardcoded.

Interval refresh config: CONFIG_REFRESH_INTERVAL detik (default 30s).
Koneksi TCP ke setiap device bersifat persistent (tidak buka-tutup tiap siklus).
"""

import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from pymodbus.client import ModbusTcpClient

from monitoring.models import Machine
from monitoring.services.jumo_config import (
    JUMO_PORT,
    load_active_devices_config,
    read_all_ai_safe,
    sanitize_values,
)
from monitoring.utils.signal_freshness import (
    STALE_AFTER_FAILURES,
    STALE_THRESHOLD_SECONDS,
    STATUS_NO_SIGNAL,
)

# ─── Konstanta ────────────────────────────────────────────────────────────────
INTERVAL_SEC = 10.0             # Interval polling Modbus (detik)
CONFIG_REFRESH_INTERVAL = 30.0  # Interval refresh konfigurasi dari DB (detik)


def get_or_create_client(dev: dict, clients: dict) -> ModbusTcpClient:
    """
    Kembalikan koneksi ModbusTcpClient yang persist antar-loop.
    Buat koneksi baru hanya jika:
      - Belum ada untuk device ini, atau
      - IP/port-nya berubah sejak koneksi terakhir dibuat.
    Cek is_socket_open() sebelum connect() untuk hindari double-connect.
    """
    name = dev["name"]
    stored = clients.get(name)

    # Invalidate jika IP atau port berubah
    if stored is not None:
        if stored["ip"] != dev["ip"] or stored["port"] != dev.get("port", JUMO_PORT):
            try:
                stored["client"].close()
            except Exception:
                pass
            stored = None
            del clients[name]

    if stored is None:
        client = ModbusTcpClient(dev["ip"], port=dev.get("port", JUMO_PORT))
        clients[name] = {"client": client, "ip": dev["ip"], "port": dev.get("port", JUMO_PORT)}
        stored = clients[name]

    client = stored["client"]

    # Hanya connect() jika socket belum terbuka — hindari double-connect
    if not client.is_socket_open():
        client.connect()

    return client


class Command(BaseCommand):
    help = "Realtime update dari JUMO ke tabel Machine (mode AUTO saja) - NO DATA LOSS LOGIC"

    def _load_config(self) -> list:
        """
        Muat konfigurasi device dari DB melalui service layer.
        Dipanggil hanya setiap CONFIG_REFRESH_INTERVAL detik, bukan setiap siklus.
        Fungsi ini sengaja tidak membungkus exception — biarkan caller yang handle
        sehingga error load config bisa di-log dan polling lanjut dengan config lama.
        """
        config = load_active_devices_config()
        return config

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "Start jumo_realtime (Dynamic DB Config + Persistent TCP). Tekan CTRL+C untuk berhenti."
        ))

        last_temps = {}
        consecutive_failures = {}  # {machine_code: int}

        devices_config = []         # Konfigurasi device di memori
        last_fetch_time = 0.0       # Timestamp float dari time.time()
        clients = {}                # {device_name: {"client": ..., "ip": ..., "port": ...}}

        try:
            while True:
                loop_start = timezone.now()
                now_ts = time.time()
                ts_str = timezone.localtime(loop_start).strftime("%H:%M:%S")

                # ─── 1. REFRESH CONFIG (setiap 30 detik) ─────────────────────
                if now_ts - last_fetch_time > CONFIG_REFRESH_INTERVAL:
                    try:
                        new_config = self._load_config()
                        devices_config = new_config
                        last_fetch_time = now_ts  # hanya update jika berhasil

                        # Invalidate client device yang sudah tidak aktif/terhapus
                        valid_names = {d["name"] for d in devices_config}
                        for name in list(clients.keys()):
                            if name not in valid_names:
                                try:
                                    clients[name]["client"].close()
                                except Exception:
                                    pass
                                del clients[name]
                                self.stdout.write(f"  [Config] Device '{name}' dihapus dari pool koneksi.")

                        self.stdout.write(self.style.SUCCESS(
                            f"\n[{ts_str}] Config JUMO direfresh: {len(devices_config)} device aktif."
                        ))
                    except Exception as e:
                        # SENGAJA tidak update last_fetch_time agar retry di siklus berikutnya
                        self.stderr.write(self.style.ERROR(
                            f"[{ts_str}] GAGAL refresh config dari DB: {e}. "
                            "Melanjutkan dengan config di memori."
                        ))

                self.stdout.write(f"\n[{ts_str}] Polling JUMO...")

                # ─── 2. AMBIL STATE MACHINE DARI DB ──────────────────────────
                try:
                    auto_machines = {
                        m.code: m for m in Machine.objects.filter(
                            is_active=True, operation_mode="AUTO"
                        )
                    }
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"[{ts_str}] GAGAL query auto_machines: {e}. Retry di siklus berikutnya."
                    ))
                    elapsed = (timezone.now() - loop_start).total_seconds()
                    time.sleep(max(0.0, INTERVAL_SEC - elapsed))
                    continue

                machines_to_update = []

                # ─── 3. LOOP SEMUA DEVICE ─────────────────────────────────────
                for dev in devices_config:
                    label = f"{dev['name']} ({dev['ip']})"
                    dev_values = None
                    connection_error = False

                    # Per-device exception: satu device error tidak menghentikan device lain
                    client = ModbusTcpClient(dev["ip"], port=dev.get("port", JUMO_PORT))
                    try:
                        if client.connect():
                            raw_values, err = read_all_ai_safe(client, dev, label)
                            if err:
                                self.stderr.write(f"  {label}: ERROR {err}")
                                connection_error = True
                            else:
                                dev_values = sanitize_values(raw_values)
                        else:
                            self.stderr.write(f"  {label}: Gagal connect")
                            connection_error = True

                    except Exception as e:
                        self.stderr.write(f"  {label}: Exception per-device: {e}")
                        connection_error = True
                    finally:
                        try:
                            client.close()
                        except Exception:
                            pass

                    # ─── Log nilai yang berhasil dibaca ───────────────────────
                    if dev_values:
                        val_strs = [f"{v:.2f}" if v is not None else "-" for v in dev_values]
                        self.stdout.write(f"  {label}: {' | '.join(val_strs)}")

                    # ─── Proses data per channel ──────────────────────────────
                    chan_names = dev.get("channels", [])
                    for i, ch_name in enumerate(chan_names):
                        if not ch_name:
                            continue  # Slot channel kosong (tidak di-mapping ke Machine)

                        machine = auto_machines.get(ch_name)
                        if not machine:
                            continue  # Machine tidak aktif atau bukan mode AUTO

                        val = None
                        if not connection_error and dev_values and i < len(dev_values):
                            val = dev_values[i]

                        # ── Pembacaan valid ────────────────────────────────────
                        if val is not None:
                            consecutive_failures[ch_name] = 0
                            last_temps[ch_name] = (val, loop_start)

                            machine.temperature = val
                            machine.last_update = loop_start
                            machine.last_valid_reading_at = loop_start
                            machines_to_update.append(machine)
                            continue

                        # ── Pembacaan gagal/invalid ───────────────────────────
                        fails = consecutive_failures.get(ch_name, 0) + 1
                        consecutive_failures[ch_name] = fails

                        reading_at = machine.last_valid_reading_at
                        age_sec = (
                            (loop_start - reading_at).total_seconds()
                            if reading_at is not None else None
                        )
                        is_stale = (
                            fails >= STALE_AFTER_FAILURES
                            or (age_sec is not None and age_sec > STALE_THRESHOLD_SECONDS)
                        )

                        if not is_stale:
                            continue

                        # Tandai No Signal (suhu lama tetap; hanya ubah status)
                        changed = False
                        old_thermal = machine.last_thermal_status or "OFFLINE"
                        old_status = machine.last_status or "Offline"

                        if old_thermal != "OFFLINE":
                            machine.previous_display_status = old_thermal
                            machine.status_changed_at = loop_start
                            changed = True
                        elif old_status not in ("Offline", STATUS_NO_SIGNAL, "OFFLINE"):
                            machine.previous_display_status = old_status
                            machine.status_changed_at = loop_start
                            changed = True

                        if machine.last_thermal_status != "OFFLINE":
                            machine.last_thermal_status = "OFFLINE"
                            changed = True

                        if machine.last_status != STATUS_NO_SIGNAL:
                            machine.last_status = STATUS_NO_SIGNAL
                            changed = True

                        if changed:
                            machines_to_update.append(machine)
                            age_label = f"{age_sec:.0f}s" if age_sec is not None else "n/a"
                            self.stderr.write(
                                f"    > No Signal {ch_name}: failures={fails}, age={age_label}"
                            )

                # ─── 4. BULK UPDATE ───────────────────────────────────────────
                if machines_to_update:
                    by_id = {m.pk: m for m in machines_to_update}
                    unique = list(by_id.values())
                    try:
                        count = Machine.objects.bulk_update(
                            unique,
                            [
                                "temperature",
                                "last_update",
                                "last_valid_reading_at",
                                "last_status",
                                "last_thermal_status",
                                "previous_display_status",
                                "status_changed_at",
                            ],
                        )
                        self.stdout.write(f"  -> DB updated: {count} records.")
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"  -> GAGAL bulk_update: {e}"))
                else:
                    self.stdout.write("  -> Tidak ada perubahan DB pada siklus ini.")

                # ─── 5. SLEEP ─────────────────────────────────────────────────
                elapsed = (timezone.now() - loop_start).total_seconds()
                sleep_time = max(0.0, INTERVAL_SEC - elapsed)

                current_sec = timezone.now().second
                if 58 <= current_sec <= 59 or current_sec <= 1:
                    sleep_time += 2.5

                time.sleep(sleep_time)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Dihentikan user (CTRL+C)."))
        finally:
            # Tutup semua socket TCP saat script berhenti
            self.stdout.write("Menutup semua koneksi Modbus...")
            for name, stored in clients.items():
                try:
                    stored["client"].close()
                except Exception:
                    pass
            self.stdout.write(self.style.SUCCESS("Semua koneksi ditutup. Selesai."))