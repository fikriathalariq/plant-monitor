"""
Unlink 4 record kritis dari batch saat ini.
Setelah dijalankan, record menjadi orphan dan bisa di-re-link
ke batch yang benar via admin (ubah start_time_snapshot ke waktu batch yang benar).
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
from datetime import timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.db import transaction

# 4 record kritis yang akan di-unlink
TARGET_IDS = [2327, 1852, 191, 1715]

print("=" * 70)
print("  UNLINK 4 RECORD KRITIS — DyeingIdentity")
print("=" * 70)

for rid in TARGET_IDS:
    try:
        ident = DyeingIdentity.objects.select_related(
            'machine', 'dyeing_process', 'dyeing_process__machine', 'program'
        ).get(id=rid)
    except DyeingIdentity.DoesNotExist:
        print(f"\nID={rid}: TIDAK DITEMUKAN!")
        continue

    batch = ident.dyeing_process
    prog  = ident.program

    print(f"\n{'─'*70}")
    print(f"  ID={ident.id} | {ident.machine.code} | Program: {prog.nama if prog else '-'}")
    print(f"  Order   : {ident.nomor_order!r}  Artikel: {ident.artikel_kain!r}")
    print(f"  Snapshot: {ident.start_time_snapshot.strftime('%Y-%m-%d %H:%M UTC') if ident.start_time_snapshot else 'NULL'}")

    if batch:
        print(f"\n  Batch saat ini (akan di-unlink):")
        print(f"    Batch #{batch.batch_number} | mesin={batch.machine.code}")
        print(f"    start_time : {batch.start_time.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"    end_time   : {batch.end_time.strftime('%Y-%m-%d %H:%M UTC') if batch.end_time else 'N/A'}")
        if prog:
            print(f"    max_temp   : {batch.max_temp:.1f}°C (ideal: {prog.suhu_max}°C)")
            print(f"    heating_dur: {batch.heating_duration:.0f}m (ideal: {prog.durasi_heating_ideal}m)")
            print(f"    steady_dur : {batch.steady_duration:.0f}m (ideal: {prog.durasi_keeping_ideal}m)")
            print(f"    cooling_dur: {batch.cooling_duration:.0f}m (ideal: {prog.durasi_cooling_ideal}m)")

    # Tampilkan 5 batch terdekat dari snapshot untuk referensi re-link
    snap = ident.start_time_snapshot
    if snap:
        nearby = DyeingProcess.objects.filter(
            machine=ident.machine,
            start_time__range=(snap - timedelta(hours=12), snap + timedelta(hours=12))
        ).order_by('start_time')

        print(f"\n  Batch terdekat (±12 jam) untuk referensi re-link:")
        print(f"  {'Batch #':>8} | {'start_time (UTC)':17} | {'Max Temp':>9} | {'Heat':>6} | {'Keep':>6} | {'Cool':>6} | {'Identity?':12}")
        print(f"  {'─'*8}-+-{'─'*17}-+-{'─'*9}-+-{'─'*6}-+-{'─'*6}-+-{'─'*6}-+-{'─'*12}")
        for b in nearby:
            try:
                has_id = b.identity is not None
                id_info = f"ID={b.identity.id}" if has_id else "KOSONG"
            except DyeingIdentity.DoesNotExist:
                has_id = False
                id_info = "KOSONG"
            is_current = " <-- SEKARANG" if batch and b.id == batch.id else ""
            temp = f"{b.max_temp:.0f}°C" if b.max_temp else "-"
            heat = f"{b.heating_duration:.0f}m" if b.heating_duration else "-"
            keep = f"{b.steady_duration:.0f}m" if b.steady_duration else "-"
            cool = f"{b.cooling_duration:.0f}m" if b.cooling_duration else "-"
            print(f"  #{b.batch_number:>7} | {b.start_time.strftime('%m-%d %H:%M UTC'):17} | {temp:>9} | {heat:>6} | {keep:>6} | {cool:>6} | {id_info}{is_current}")

    print(f"\n  >> UNLINK ID={ident.id}...")
    with transaction.atomic():
        old_process_id = ident.dyeing_process_id
        ident.dyeing_process = None
        ident.save(update_fields=['dyeing_process'])
    print(f"  >> OK — dyeing_process_id: {old_process_id} -> NULL")
    print(f"  >> Sekarang orphan. Untuk re-link:")
    print(f"     1. Buka admin DyeingIdentity, edit ID={ident.id}")
    print(f"     2. Ubah 'start_time_snapshot' ke waktu start_time batch yang benar")
    print(f"     3. Simpan — sistem akan otomatis re-link (dalam ±15 mnt)")

print(f"\n{'='*70}")
print(f"  SELESAI — 4 record telah di-unlink menjadi orphan")
print(f"{'='*70}\n")

# Verifikasi
still_linked = DyeingIdentity.objects.filter(id__in=TARGET_IDS, dyeing_process__isnull=False).count()
now_orphan   = DyeingIdentity.objects.filter(id__in=TARGET_IDS, dyeing_process__isnull=True).count()
print(f"  Verifikasi: masih linked={still_linked}, orphan={now_orphan}")
