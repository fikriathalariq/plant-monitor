"""
====================================================================
FORCED-LINK ORPHAN - DyeingIdentity
====================================================================
Script ini mengubah data orphan yang "close" (dekat dengan batch):
  1. Mengubah start_time_snapshot → start_time batch terdekat
  2. Meng-link dyeing_process → DyeingProcess terdekat

Mode:
  --dry-run   : Tampilkan apa yang AKAN diubah (tidak ada perubahan)
  --execute   : Eksekusi perubahan ke database

Syarat forced-link:
  - machine dan start_time_snapshot tidak NULL
  - Ada DyeingProcess untuk mesin yang sama dalam ±8 jam
  - DyeingProcess target BELUM punya identity (OneToOne free)
  - Selisih waktu ≤ LINK_WINDOW_MINUTES (60 menit)
====================================================================
Usage:
  python force_link_orphans.py             (default: dry-run)
  python force_link_orphans.py --dry-run   (explicit dry-run)
  python force_link_orphans.py --execute   (EKSEKUSI LANGSUNG)
====================================================================
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


import os
import sys
import django
from datetime import timedelta, timezone as dt_timezone
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.utils import timezone
from django.db import transaction

# ── Konfigurasi ──────────────────────────────────────────────────
LINK_WINDOW_MINUTES   = 60    # Selisih max agar bisa forced-link
SEARCH_WINDOW_HOURS   = 8     # Radius pencarian batch terdekat

# ── Parse argumen ────────────────────────────────────────────────
DRY_RUN = True
if "--execute" in sys.argv:
    DRY_RUN = False
elif "--dry-run" in sys.argv or len(sys.argv) == 1:
    DRY_RUN = True

mode_label = "[DRY-RUN]" if DRY_RUN else "[EXECUTE]"

print("=" * 70)
print(f"  FORCED-LINK ORPHAN - DyeingIdentity  {mode_label}")
print("=" * 70)
if DRY_RUN:
    print("\n  *** DRY-RUN MODE: Tidak ada data yang diubah ***")
    print("  *** Jalankan dengan --execute untuk mengeksekusi ***\n")
else:
    print("\n  *** EXECUTE MODE: Data akan LANGSUNG DIUBAH ***\n")

# ── Ambil semua orphan ───────────────────────────────────────────
orphans = list(
    DyeingIdentity.objects.filter(dyeing_process__isnull=True)
    .select_related('machine')
    .order_by('machine', 'start_time_snapshot')
)

print(f"  Ditemukan {len(orphans)} orphan total.\n")

# ── Proses setiap orphan ─────────────────────────────────────────
results_ok      = []   # Berhasil forced-link
results_skip_dup   = []   # Duplikat (batch sudah punya identity lain)
results_skip_far   = []   # Selisih terlalu jauh
results_skip_null  = []   # Machine/timestamp NULL

for orphan in orphans:

    # Cek data lengkap
    if not orphan.machine_id or not orphan.start_time_snapshot:
        results_skip_null.append({'id': orphan.id, 'reason': 'machine atau snapshot NULL'})
        continue

    snapshot = orphan.start_time_snapshot

    # Cari batch terdekat dalam window waktu
    nearby = DyeingProcess.objects.filter(
        machine_id=orphan.machine_id,
        start_time__range=(
            snapshot - timedelta(hours=SEARCH_WINDOW_HOURS),
            snapshot + timedelta(hours=SEARCH_WINDOW_HOURS)
        )
    ).order_by('start_time')

    # Pilih yang paling dekat berdasarkan |start_time - snapshot|
    nearest = None
    nearest_diff_min = None
    for batch in nearby:
        diff_min = abs((batch.start_time - snapshot).total_seconds() / 60)
        if nearest_diff_min is None or diff_min < nearest_diff_min:
            nearest_diff_min = diff_min
            nearest = batch

    # Tidak ada batch ditemukan
    if nearest is None:
        results_skip_far.append({
            'id': orphan.id,
            'machine': orphan.machine.code,
            'snapshot': snapshot,
            'reason': 'Tidak ada batch dalam ±8 jam'
        })
        continue

    # Selisih terlalu jauh
    if nearest_diff_min > LINK_WINDOW_MINUTES:
        results_skip_far.append({
            'id': orphan.id,
            'machine': orphan.machine.code,
            'snapshot': snapshot,
            'nearest_start': nearest.start_time,
            'nearest_batch_number': nearest.batch_number,
            'diff_min': nearest_diff_min,
            'reason': f'Selisih {nearest_diff_min:.0f} menit > limit {LINK_WINDOW_MINUTES} menit'
        })
        continue

    # Cek apakah batch target sudah punya identity lain (OneToOne conflict)
    try:
        existing_identity = nearest.identity  # raises DoesNotExist jika kosong
        # Ada identity lain yang memblok
        results_skip_dup.append({
            'id': orphan.id,
            'machine': orphan.machine.code,
            'snapshot': snapshot,
            'nearest_batch_number': nearest.batch_number,
            'blocking_identity_id': existing_identity.id,
            'diff_min': nearest_diff_min,
            'reason': f'Batch #{nearest.batch_number} sudah punya Identity ID={existing_identity.id}'
        })
        continue
    except DyeingIdentity.DoesNotExist:
        pass  # Batch kosong, bisa di-link

    # Ini bisa di-forced-link!
    old_snapshot = snapshot
    new_snapshot  = nearest.start_time
    diff_signed   = (old_snapshot - new_snapshot).total_seconds() / 60

    results_ok.append({
        'orphan': orphan,
        'id': orphan.id,
        'machine': orphan.machine.code,
        'old_snapshot': old_snapshot,
        'new_snapshot': new_snapshot,
        'nearest': nearest,
        'batch_number': nearest.batch_number,
        'diff_signed_min': diff_signed,
    })

# ── Tampilkan Preview ────────────────────────────────────────────
print(f"  {'='*68}")
print(f"  HASIL KLASIFIKASI")
print(f"  {'='*68}")
print(f"  Bisa forced-link              : {len(results_ok)}")
print(f"  Diskip - konflik OneToOne     : {len(results_skip_dup)}")
print(f"  Diskip - selisih jauh/no batch: {len(results_skip_far)}")
print(f"  Diskip - data NULL            : {len(results_skip_null)}")

# ── Detail yang akan diubah ──────────────────────────────────────
if results_ok:
    print(f"\n  {'='*68}")
    print(f"  DETAIL FORCED-LINK {mode_label}")
    print(f"  {'='*68}")
    print(f"  {'ID':>6} | {'Mesin':8} | {'Snapshot Lama (UTC)':20} | {'Diff':>8} | {'Batch #':>8} | {'Snapshot Baru (UTC)':20}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*20}-+-{'-'*8}-+-{'-'*8}-+-{'-'*20}")

    for r in results_ok:
        old_str = r['old_snapshot'].strftime('%Y-%m-%d %H:%M')
        new_str = r['new_snapshot'].strftime('%Y-%m-%d %H:%M')
        diff_str = f"{r['diff_signed_min']:+.0f} mnt"
        print(f"  {r['id']:>6} | {r['machine']:8} | {old_str:20} | {diff_str:>8} | Batch #{r['batch_number']:<4} | {new_str:20}")

# ── Eksekusi ─────────────────────────────────────────────────────
if not DRY_RUN and results_ok:
    print(f"\n  {'='*68}")
    print(f"  MENGEKSEKUSI PERUBAHAN...")
    print(f"  {'='*68}\n")

    success_count = 0
    error_count = 0

    for r in results_ok:
            orphan = r['orphan']
            nearest = r['nearest']
            try:
                with transaction.atomic():
                    orphan.start_time_snapshot = r['new_snapshot']
                    orphan.dyeing_process = nearest
                    orphan.save(update_fields=['start_time_snapshot', 'dyeing_process'])
                success_count += 1
                print(f"  OK  ID={orphan.id} ({r['machine']}) -> Batch #{r['batch_number']} | "
                      f"snapshot: {r['old_snapshot'].strftime('%m-%d %H:%M')} -> {r['new_snapshot'].strftime('%m-%d %H:%M')}")
            except Exception as e:
                error_count += 1
                print(f"  ERR ID={orphan.id} ({r['machine']}) -> ERROR: {e}")

    print(f"\n  -----------------------------------------------")
    print(f"  Berhasil : {success_count}")
    print(f"  Gagal    : {error_count}")

    if error_count > 0:
        print(f"\n  [WARNING] Ada {error_count} error - cek log di atas")
    else:
        print(f"\n  [SUCCESS] Semua {success_count} orphan berhasil di-forced-link!")

elif DRY_RUN and results_ok:
    print(f"\n  [DRY-RUN] {len(results_ok)} orphan SIAP diubah.")
    print(f"  Jalankan dengan --execute untuk mengeksekusi.")

# ── Informasi Diskip ──────────────────────────────────────────────
if results_skip_dup:
    print(f"\n  {'='*68}")
    print(f"  DISKIP (OneToOne Conflict - Perlu Cek Manual Operator)")
    print(f"  {'='*68}")
    for r in results_skip_dup:
        snap_str = r['snapshot'].strftime('%Y-%m-%d %H:%M UTC')
        nearest_str = r.get('nearest_start', r['snapshot']).strftime('%m-%d %H:%M') if r.get('nearest_start') else 'N/A'
        print(f"  ID={r['id']:>5} | {r['machine']:8} | snap={snap_str} | diff={r['diff_min']:.0f}mnt | Batch #{r.get('nearest_batch_number','?')} diblok oleh Identity ID={r['blocking_identity_id']}")

if results_skip_far:
    print(f"\n  {'='*68}")
    print(f"  DISKIP (Selisih Terlalu Jauh / Tidak Ada Batch)")
    print(f"  {'='*68}")
    for r in results_skip_far:
        snap_str = r['snapshot'].strftime('%Y-%m-%d %H:%M UTC') if r.get('snapshot') else 'N/A'
        diff_info = f"diff={r['diff_min']:.0f}mnt" if r.get('diff_min') else ''
        print(f"  ID={r['id']:>5} | {r['machine']:8} | snap={snap_str} | {r['reason']} {diff_info}")

print(f"\n{'='*70}")
print(f"  SELESAI {mode_label}")
print(f"{'='*70}\n")
