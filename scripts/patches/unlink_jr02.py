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

# Record paling kritis: JR_02
TARGET_IDS = [589]

print("=" * 70)
print("  UNLINK RECORD JR_02 (ID=589)")
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
        
        # Juga tandai batch-nya sebagai is_valid_process = False karena anomali
        if batch:
            batch.is_valid_process = False
            batch.save(update_fields=['is_valid_process'])
            print(f"  >> OK — Tandai Batch #{batch.batch_number} is_valid_process = False (KARENA PREMATUR/TIDAK JALAN)")

    print(f"  >> OK — dyeing_process_id: {old_process_id} -> NULL")
