import os
import sys
import argparse
import time
import importlib
import pkgutil
from waitress import serve
from plant_monitor.wsgi import application

def preload_all_modules():
    """
    Eager Module Preload: Memuat seluruh modul web, api, model, dan views ke memori
    (sys.modules) sebelum Waitress mulai menerima request. Ini menjamin proses yang
    sedang berjalan di RAM 100% kedap (immutable) terhadap perubahan file .py di disk
    saat slot lain sedang di-deploy/di-update.
    """
    import monitoring
    t0 = time.time()
    count = 0
    for _, modname, ispkg in pkgutil.walk_packages(monitoring.__path__, monitoring.__name__ + '.'):
        # Lewati management commands dan cache internal agar tidak mengeksekusi script CLI
        if 'management.commands' in modname or '__pycache__' in modname:
            continue
        try:
            importlib.import_module(modname)
            count += 1
        except Exception:
            pass
    elapsed = round(time.time() - t0, 3)
    print(f"[Preload] Berhasil memuat {count} modul Python ke RAM dalam {elapsed}s (Proses kedap perubahan disk).")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Plant Monitor Production Server (Waitress)")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", 8080)),
        help="Port lokal yang didengarkan oleh Waitress (contoh: 8081 untuk Blue, 8082 untuk Green)"
    )
    parser.add_argument(
        "--slot", "-s",
        type=str,
        default=os.environ.get("SLOT", None),
        help="Nama slot Blue-Green (blue, green, atau legacy)"
    )
    args = parser.parse_args()

    port = args.port
    slot = args.slot
    if not slot:
        if port == 8081:
            slot = "blue"
        elif port == 8082:
            slot = "green"
        else:
            slot = "legacy"

    # Set ke environment agar terbaca oleh health check endpoint
    os.environ["PLANT_MONITOR_PORT"] = str(port)
    os.environ["PLANT_MONITOR_SLOT"] = slot

    print("=======================================================")
    print(f" Plant Monitor Server — Slot: {slot.upper()} (Port: {port})")
    print(" Standar Arsitektur: High Availability (HA) & Zero-Downtime")
    print(" Akses publik via Nginx: http://IP_SERVER:8000 (atau :8002)")
    print(" Tekan Ctrl+C untuk berhenti")
    print("=======================================================")

    # Jalankan eager preloading
    preload_all_modules()

    serve(
        application,
        host='127.0.0.1',
        port=port,

        # --- Performa & Kapasitas Database ---
        # 24 threads per slot menjamin saat Blue & Green menyala bersamaan,
        # total koneksi (24 + 24 = 48) tetap sangat aman di bawah PostgreSQL max_connections=100.
        threads=24,

        # --- Proteksi Koneksi & Bot Scanner ---
        connection_limit=2000,
        channel_timeout=30,
        cleanup_interval=15,

        # --- Batas Ukuran Request ---
        max_request_header_size=65536,   # 64 KB
        max_request_body_size=104857600, # 100 MB
    )
