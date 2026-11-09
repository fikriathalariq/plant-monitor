"""
====================================================================
SIMULASI ANALISIS ORPHAN - DyeingIdentity
====================================================================
Tujuan: Menganalisis semua DyeingIdentity yang orphan (tanpa link 
ke DyeingProcess), mengklasifikasikan penyebabnya, dan mensimulasikan
forced-link ke batch terdekat.

Kategori Orphan:
  A) DUPLICATE   - Nomor order + artikel kain sama dengan identity lain
                   di mesin + waktu yang hampir sama (duplikat operator)
  B) TIME_DRIFT  - start_time_snapshot di luar rentang waktu batch 
                   terdekat (melebihi threshold)
  C) NO_BATCH    - Tidak ada DyeingProcess sama sekali untuk mesin tsb
                   di sekitar waktu identity dibuat
  D) NO_MACHINE  - machine/start_time_snapshot NULL
  E) OTHER       - Penyebab lain yang tidak teridentifikasi
====================================================================
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


import os, sys, django
from datetime import timedelta
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.utils import timezone

# ── Konfigurasi Threshold ────────────────────────────────────────
LINK_WINDOW_MINUTES = 60   # Window pencarian batch terdekat (±60 menit dari snapshot)
DUPLICATE_WINDOW_MINUTES = 90  # Window deteksi duplikat antar identities
FORCE_LINK_MAX_MINUTES = 480   # Max selisih untuk forced-link (8 jam)

print("=" * 70)
print("  SIMULASI ANALISIS ORPHAN - DyeingIdentity")
print("=" * 70)

# ── Ambil semua orphan ───────────────────────────────────────────
orphans = list(DyeingIdentity.objects.filter(
    dyeing_process__isnull=True
).select_related('machine').order_by('machine', 'start_time_snapshot'))

total_identities = DyeingIdentity.objects.count()
total_linked = DyeingIdentity.objects.filter(dyeing_process__isnull=False).count()

print(f"\n📊 STATISTIK UMUM")
print(f"   Total DyeingIdentity : {total_identities}")
print(f"   Terlink (normal)     : {total_linked}")
print(f"   Orphan               : {len(orphans)}")
print(f"   Orphan Rate          : {len(orphans)/total_identities*100:.1f}%")

# ── Step 1: Bangun lookup semua DyeingIdentity untuk deteksi duplikat ──
# Groupkan berdasarkan: machine_id + nomor_order + artikel_kain
all_identities = list(DyeingIdentity.objects.select_related('machine').all())

# Index: (machine_id, nomor_order, artikel_kain) -> list of identities
identity_index = defaultdict(list)
for ident in all_identities:
    if ident.nomor_order and ident.artikel_kain:
        key = (ident.machine_id, ident.nomor_order.strip(), ident.artikel_kain.strip())
        identity_index[key].append(ident)

# ── Step 2: Klasifikasi setiap orphan ───────────────────────────
results = []

for orphan in orphans:
    row = {
        'id': orphan.id,
        'machine': orphan.machine.code if orphan.machine else None,
        'machine_id': orphan.machine_id,
        'snapshot': orphan.start_time_snapshot,
        'nomor_order': orphan.nomor_order,
        'artikel_kain': orphan.artikel_kain,
        'created_at': orphan.created_at,
        'category': None,
        'reason': '',
        'nearest_batch': None,
        'nearest_batch_id': None,
        'nearest_batch_number': None,
        'nearest_start': None,
        'nearest_heat_start': None,
        'diff_from_start_min': None,
        'diff_from_heat_start_min': None,
        'can_force_link': False,
        'force_link_target_id': None,
        'duplicate_of_id': None,
    }

    # ── Cek D: Machine atau snapshot NULL ───────────────────────
    if not orphan.machine_id or not orphan.start_time_snapshot:
        row['category'] = 'D_NO_MACHINE'
        row['reason'] = 'machine atau start_time_snapshot adalah NULL'
        results.append(row)
        continue

    # ── Cek A: Duplikat (nomor_order + artikel kain sama, di mesin + waktu dekat) ──
    is_duplicate = False
    if orphan.nomor_order and orphan.artikel_kain:
        key = (orphan.machine_id, orphan.nomor_order.strip(), orphan.artikel_kain.strip())
        candidates = identity_index.get(key, [])
        for c in candidates:
            if c.id == orphan.id:
                continue
            if c.start_time_snapshot and orphan.start_time_snapshot:
                diff = abs((c.start_time_snapshot - orphan.start_time_snapshot).total_seconds() / 60)
                if diff <= DUPLICATE_WINDOW_MINUTES:
                    # Ini duplikat dari c
                    row['category'] = 'A_DUPLICATE'
                    row['reason'] = (
                        f"Duplikat dari Identity ID={c.id} "
                        f"(selisih {diff:.0f} menit, order={orphan.nomor_order}, artikel={orphan.artikel_kain})"
                    )
                    row['duplicate_of_id'] = c.id
                    is_duplicate = True
                    break

    # ── Cari batch terdekat untuk mesin ini ─────────────────────
    snapshot = orphan.start_time_snapshot
    
    # Ambil semua batch untuk mesin ini dalam window yang lebih lebar
    nearby_batches = DyeingProcess.objects.filter(
        machine_id=orphan.machine_id,
        start_time__range=(
            snapshot - timedelta(hours=FORCE_LINK_MAX_MINUTES//60 + 2),
            snapshot + timedelta(hours=FORCE_LINK_MAX_MINUTES//60 + 2)
        )
    ).order_by('start_time')

    # Cari yang paling dekat (berdasarkan |start_time - snapshot|)
    nearest = None
    nearest_diff = None
    for b in nearby_batches:
        diff = abs((b.start_time - snapshot).total_seconds() / 60)
        if nearest_diff is None or diff < nearest_diff:
            nearest_diff = diff
            nearest = b

    if nearest:
        row['nearest_batch'] = nearest
        row['nearest_batch_id'] = nearest.id
        row['nearest_batch_number'] = nearest.batch_number
        row['nearest_start'] = nearest.start_time
        row['nearest_heat_start'] = nearest.heating_start_time
        
        # Selisih dari start_time batch
        diff_start = (snapshot - nearest.start_time).total_seconds() / 60
        row['diff_from_start_min'] = round(diff_start, 1)
        
        # Selisih dari heating_start_time (jika ada)
        if nearest.heating_start_time:
            diff_heat = (snapshot - nearest.heating_start_time).total_seconds() / 60
            row['diff_from_heat_start_min'] = round(diff_heat, 1)

        # Apakah bisa di-forced-link?
        if abs(diff_start) <= FORCE_LINK_MAX_MINUTES:
            # Cek apakah batch ini sudah punya identity lain
            try:
                existing_identity = nearest.identity
                # Batch sudah punya identity -> tidak bisa link (kecuali dipaksa hapus)
                row['can_force_link'] = False
                row['force_link_reason'] = f"Batch #{nearest.batch_number} sudah punya Identity ID={existing_identity.id}"
            except DyeingIdentity.DoesNotExist:
                # Batch belum punya identity -> bisa link
                row['can_force_link'] = True
                row['force_link_target_id'] = nearest.id

    # ── Klasifikasi lanjutan (jika bukan duplikat) ──────────────
    if not is_duplicate:
        if nearest is None:
            row['category'] = 'C_NO_BATCH'
            row['reason'] = f"Tidak ada DyeingProcess ditemukan untuk mesin ini dalam ±{FORCE_LINK_MAX_MINUTES//60} jam"
        else:
            diff_abs = abs(row['diff_from_start_min'])
            
            if diff_abs <= LINK_WINDOW_MINUTES:
                # Seharusnya bisa ter-link tapi tidak - ada konflik atau alasan lain
                row['category'] = 'E_OTHER'
                row['reason'] = (
                    f"Selisih dengan batch terdekat hanya {diff_abs:.0f} menit "
                    f"(≤{LINK_WINDOW_MINUTES} menit), seharusnya ter-link. "
                    f"Kemungkinan batch telah di-reprocess atau konflik OneToOne"
                )
            else:
                row['category'] = 'B_TIME_DRIFT'
                row['reason'] = (
                    f"Selisih waktu {diff_abs:.0f} menit dari batch terdekat "
                    f"(melebihi window ±{LINK_WINDOW_MINUTES} menit). "
                    f"Snapshot mungkin salah timezone atau batch telah direcompute"
                )

    results.append(row)

# ── Step 3: Tampilkan Ringkasan per Kategori ─────────────────────
print(f"\n{'='*70}")
print(f"  KLASIFIKASI ORPHAN")
print(f"{'='*70}")

categories = {
    'A_DUPLICATE': [],
    'B_TIME_DRIFT': [],
    'C_NO_BATCH': [],
    'D_NO_MACHINE': [],
    'E_OTHER': [],
}

for r in results:
    cat = r['category']
    if cat in categories:
        categories[cat].append(r)

cat_labels = {
    'A_DUPLICATE': '🔴 A) DUPLIKAT (nomor order + artikel sama di waktu dekat)',
    'B_TIME_DRIFT': '🟠 B) TIME DRIFT (waktu di luar rentang batch terdekat)',
    'C_NO_BATCH': '🔵 C) NO BATCH (tidak ada batch di sekitar waktu tsb)',
    'D_NO_MACHINE': '⚫ D) NO MACHINE (mesin/timestamp NULL)',
    'E_OTHER': '🟡 E) OTHER (batch ada tapi tetap orphan)',
}

for cat, items in categories.items():
    print(f"\n{cat_labels[cat]}: {len(items)} orphan")
    if items:
        for r in items:
            snap_str = r['snapshot'].strftime('%Y-%m-%d %H:%M UTC') if r['snapshot'] else 'N/A'
            nearest_str = r['nearest_start'].strftime('%Y-%m-%d %H:%M UTC') if r['nearest_start'] else 'TIDAK ADA'
            diff_str = f"{r['diff_from_start_min']:+.0f} mnt" if r['diff_from_start_min'] is not None else 'N/A'
            heat_diff_str = f"{r['diff_from_heat_start_min']:+.0f} mnt" if r['diff_from_heat_start_min'] is not None else 'N/A'
            can_link = "✅ BISA LINK" if r['can_force_link'] else "❌"
            batch_str = f"Batch #{r['nearest_batch_number']}" if r['nearest_batch_number'] else 'N/A'
            
            print(f"  ┌─ ID={r['id']} | {r['machine']} | Snapshot: {snap_str}")
            print(f"  │  Order={r['nomor_order']!r:15s} | Artikel={r['artikel_kain']!r}")
            print(f"  │  Batch Terdekat: {batch_str} @ {nearest_str}")
            print(f"  │  Selisih dari start_time: {diff_str} | Selisih dari heat_start: {heat_diff_str}")
            print(f"  │  Force Link: {can_link}")
            print(f"  └─ Alasan: {r['reason'][:80]}")
            print()

# ── Step 4: Simulasi Forced-Link ─────────────────────────────────
print(f"\n{'='*70}")
print(f"  SIMULASI FORCED-LINK")
print(f"{'='*70}")

linkable = [r for r in results if r['can_force_link'] and r['category'] != 'A_DUPLICATE']
not_linkable_dup = [r for r in results if r['category'] == 'A_DUPLICATE']
not_linkable_no_batch = [r for r in results if r['category'] == 'C_NO_BATCH']
not_linkable_no_machine = [r for r in results if r['category'] == 'D_NO_MACHINE']
not_linkable_conflict = [r for r in results if not r['can_force_link'] and r['category'] not in ('A_DUPLICATE', 'C_NO_BATCH', 'D_NO_MACHINE')]

print(f"\n  ✅ Bisa di-forced-link                    : {len(linkable)}")
print(f"  🔴 Perlu cek manual (DUPLIKAT)            : {len(not_linkable_dup)}")
print(f"  🔵 Tidak ada batch ditemukan              : {len(not_linkable_no_batch)}")
print(f"  ⚫ NULL machine/timestamp                 : {len(not_linkable_no_machine)}")
print(f"  ⚠️  Konflik OneToOne (batch sudah punya ID): {len(not_linkable_conflict)}")

if linkable:
    print(f"\n  📋 DETAIL YANG AKAN DI-FORCED-LINK:")
    print(f"  {'ID':>6} | {'Mesin':10} | {'Snapshot (UTC)':20} | {'Diff (mnt)':>10} | {'→ Batch #':>10} | {'New TS (UTC)':20}")
    print(f"  {'-'*6}-+-{'-'*10}-+-{'-'*20}-+-{'-'*10}-+-{'-'*10}-+-{'-'*20}")
    
    for r in linkable:
        snap_str = r['snapshot'].strftime('%Y-%m-%d %H:%M') if r['snapshot'] else 'N/A'
        new_ts_str = r['nearest_start'].strftime('%Y-%m-%d %H:%M') if r['nearest_start'] else 'N/A'
        diff = r['diff_from_start_min']
        diff_str = f"{diff:+.0f}" if diff is not None else 'N/A'
        print(f"  {r['id']:>6} | {r['machine']:10} | {snap_str:20} | {diff_str:>10} | Batch #{r['nearest_batch_number']:<5} | {new_ts_str:20}")

# ── Step 5: Summary Table ─────────────────────────────────────────
print(f"\n{'='*70}")
print(f"  RINGKASAN AKHIR")
print(f"{'='*70}")
print(f"""
  Total Orphan          : {len(results)}
  ├─ Bisa Auto-Fix      : {len(linkable)} (forced-link ke batch terdekat)
  ├─ Manual (Duplikat)  : {len(not_linkable_dup)} (operator harus hapus salah satu)
  ├─ Tanpa Batch        : {len(not_linkable_no_batch)} (tidak ada batch di rentang waktu)
  ├─ Konflik OneToOne   : {len(not_linkable_conflict)} (batch sudah punya Identity lain)
  └─ NULL data          : {len(not_linkable_no_machine)} (data tidak lengkap)

  CATATAN:
  - 'Forced-link' = start_time_snapshot diubah ke start_time batch terdekat
    + dyeing_process di-set ke batch tsb
  - Threshold window link  : ±{LINK_WINDOW_MINUTES} menit
  - Max window forced-link : ±{FORCE_LINK_MAX_MINUTES} menit ({FORCE_LINK_MAX_MINUTES//60} jam)
  - Selisih waktu POSITIF  = snapshot SETELAH start batch (normal)
  - Selisih waktu NEGATIF  = snapshot SEBELUM start batch (aneh / timezone issue)
""")

print("✅ Simulasi selesai. Tidak ada data yang diubah.")
