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

SEARCH_WINDOW_HOURS = 24
LINK_WINDOW_MINUTES = 60

print("=" * 70)
print("  ANALISIS MENDALAM: ORPHAN SKIPPED (SELISIH JAUH / NO BATCH)")
print("=" * 70)

orphans = list(
    DyeingIdentity.objects.filter(dyeing_process__isnull=True)
    .select_related('machine')
    .order_by('machine__code', 'start_time_snapshot')
)

print(f"\nTotal orphan saat ini: {len(orphans)}\n")

far_orphans = []

for orphan in orphans:
    if not orphan.machine_id or not orphan.start_time_snapshot:
        continue
    snapshot = orphan.start_time_snapshot

    nearby = DyeingProcess.objects.filter(
        machine_id=orphan.machine_id,
        start_time__range=(
            snapshot - timedelta(hours=SEARCH_WINDOW_HOURS),
            snapshot + timedelta(hours=SEARCH_WINDOW_HOURS)
        )
    ).order_by('start_time')

    candidates = []
    for b in nearby:
        diff_min = (snapshot - b.start_time).total_seconds() / 60
        diff_abs = abs(diff_min)
        try:
            existing = b.identity
            has_identity = True
            existing_id = existing.id
        except DyeingIdentity.DoesNotExist:
            has_identity = False
            existing_id = None
        candidates.append((diff_abs, diff_min, b, has_identity, existing_id))

    candidates.sort(key=lambda x: x[0])
    nearest = candidates[0] if candidates else None

    # Hanya proses yang selisihnya > LINK_WINDOW_MINUTES atau tidak ada batch sama sekali
    if nearest is None or nearest[0] > LINK_WINDOW_MINUTES:
        far_orphans.append((orphan, snapshot, candidates, nearest))

print(f"Jumlah orphan dengan selisih jauh / no batch: {len(far_orphans)}\n")
print("-" * 70)

for (orphan, snapshot, candidates, nearest) in far_orphans:
    snap_str = snapshot.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[ORPHAN ID={orphan.id}]")
    print(f"  Mesin        : {orphan.machine.code}")
    print(f"  Snapshot     : {snap_str}")
    print(f"  Nomor Order  : {repr(orphan.nomor_order)}")
    print(f"  Artikel Kain : {repr(orphan.artikel_kain)}")
    print(f"  Jenis Proses : {repr(orphan.jenis_proses)}")
    print(f"  Dibuat       : {orphan.created_at.strftime('%Y-%m-%d %H:%M UTC')}")

    if nearest is None:
        print(f"  Batch terdekat: TIDAK ADA dalam {SEARCH_WINDOW_HOURS} jam")
    else:
        diff_abs, diff_min, b, has_id, existing_id = nearest
        arah = "SETELAH batch" if diff_min > 0 else "SEBELUM batch"
        print(f"\n  Batch Terdekat:")
        print(f"    Batch #{b.batch_number}")
        print(f"    start_time  : {b.start_time.strftime('%Y-%m-%d %H:%M UTC')}")
        if b.heating_start_time:
            print(f"    heating_start: {b.heating_start_time.strftime('%Y-%m-%d %H:%M UTC')}")
        if b.end_time:
            print(f"    end_time    : {b.end_time.strftime('%Y-%m-%d %H:%M UTC')}")
            # Cek apakah snapshot berada DALAM rentang batch
            if b.start_time <= snapshot <= b.end_time:
                print(f"    *** SNAPSHOT BERADA DALAM DURASI BATCH INI ***")
        print(f"    Snapshot adalah {diff_abs:.0f} menit ({diff_abs/60:.1f} jam) {arah}")
        id_status = f"YA, diblok oleh Identity ID={existing_id}" if has_id else "TIDAK (slot kosong)"
        print(f"    Punya identity: {id_status}")

    print(f"\n  TOP 5 KANDIDAT BATCH (dalam {SEARCH_WINDOW_HOURS} jam):")
    if candidates:
        for i, (da, dm, cb, hi, eid) in enumerate(candidates[:5]):
            sign = "+" if dm > 0 else "-"
            if hi:
                id_info = f"diblok Identity ID={eid}"
            else:
                id_info = "KOSONG - bisa dilink"
            ht = cb.heating_start_time.strftime("%H:%M") if cb.heating_start_time else "N/A"
            et = cb.end_time.strftime("%m-%d %H:%M") if cb.end_time else "ongoing"
            print(f"    [{i+1}] Batch #{cb.batch_number:<5} | start={cb.start_time.strftime('%m-%d %H:%M')} | heat={ht} | end={et} | diff={sign}{da:.0f}mnt | {id_info}")
    else:
        print("    Tidak ada kandidat batch ditemukan.")

    print()
    print("-" * 70)

print()
print("KESIMPULAN:")
print(f"  Total orphan selisih jauh : {len(far_orphans)}")
can_force = [(o, s, c, n) for o, s, c, n in far_orphans if n and not n[3]]
blocked   = [(o, s, c, n) for o, s, c, n in far_orphans if n and n[3]]
no_batch  = [(o, s, c, n) for o, s, c, n in far_orphans if n is None]
print(f"  -> Slot kosong tapi jauh  : {len(can_force)} (bisa link jika perlebar threshold)")
print(f"  -> Slot sudah diblok      : {len(blocked)} (perlu manual)")
print(f"  -> Tidak ada batch        : {len(no_batch)} (tidak ada kandidat)")
