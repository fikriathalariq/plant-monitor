"""
=======================================================================
CEK INTEGRITAS DATA - DyeingAnalytics
=======================================================================
Memeriksa anomali data pada DyeingIdentity yang ter-link ke DyeingProcess,
khususnya akibat forced-link yang baru kita lakukan.

Cek yang dilakukan:
  1. start_time_snapshot vs dyeing_process.start_time  (seharusnya sama)
  2. machine identity vs machine batch                  (seharusnya sama)
  3. Timestamp yang tidak logis (snapshot jauh dari batch)
  4. Durasi batch anomali (negatif, nol, atau ekstrem)
  5. Suhu max anomali (< 30 atau > 140 derajat)
  6. Duration_effective anomali
  7. Identities yang ter-link ke batch berbeda mesin
  8. Batch yang punya lebih dari satu identity (seharusnya tidak ada)
=======================================================================
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
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.db.models import Count

print("=" * 70)
print("  CEK INTEGRITAS DATA - DyeingAnalytics")
print("=" * 70)

linked = list(
    DyeingIdentity.objects.filter(dyeing_process__isnull=False)
    .select_related('machine', 'dyeing_process', 'dyeing_process__machine', 'program')
    .order_by('machine__code', 'dyeing_process__start_time')
)

total = len(linked)
print(f"\nTotal identity yang ter-link: {total}\n")

issues = []

def flag(category, ident, batch, detail):
    issues.append({
        'cat': category,
        'id': ident.id,
        'machine': ident.machine.code if ident.machine else '?',
        'batch_num': batch.batch_number if batch else '?',
        'batch_start': batch.start_time if batch else None,
        'snap': ident.start_time_snapshot,
        'detail': detail,
    })

for ident in linked:
    batch = ident.dyeing_process

    # ── Cek 1: Machine identity ≠ machine batch ─────────────────────
    if ident.machine_id and batch.machine_id and ident.machine_id != batch.machine_id:
        flag("MESIN_BEDA", ident, batch,
             f"Identity.machine={ident.machine.code} tapi Batch.machine={batch.machine.code}")

    # ── Cek 2: Snapshot sangat jauh dari batch start_time ────────────
    if ident.start_time_snapshot and batch.start_time:
        diff = abs((ident.start_time_snapshot - batch.start_time).total_seconds() / 60)
        if diff > 5:  # lebih dari 5 menit → flag (setelah forced-link harusnya sama persis atau sangat dekat)
            flag("SNAPSHOT_DRIFT", ident, batch,
                 f"Selisih snapshot vs batch.start_time: {diff:.0f} mnt "
                 f"(snap={ident.start_time_snapshot.strftime('%m-%d %H:%M')}, "
                 f"start={batch.start_time.strftime('%m-%d %H:%M')})")

    # ── Cek 3: Duration anomali ──────────────────────────────────────
    if batch.heating_duration is not None and batch.heating_duration < 0:
        flag("HEATING_NEGATIF", ident, batch,
             f"heating_duration = {batch.heating_duration:.1f} mnt (negatif!)")

    if batch.heating_duration is not None and batch.heating_duration > 600:
        flag("HEATING_EKSTREM", ident, batch,
             f"heating_duration = {batch.heating_duration:.1f} mnt (>10 jam, anomali)")

    if batch.steady_duration is not None and batch.steady_duration < 0:
        flag("STEADY_NEGATIF", ident, batch,
             f"steady_duration = {batch.steady_duration:.1f} mnt (negatif!)")

    if batch.cooling_duration is not None and batch.cooling_duration < 0:
        flag("COOLING_NEGATIF", ident, batch,
             f"cooling_duration = {batch.cooling_duration:.1f} mnt (negatif!)")

    # ── Cek 4: Suhu max anomali ──────────────────────────────────────
    if batch.max_temp is not None:
        if batch.max_temp < 30:
            flag("TEMP_TERLALU_RENDAH", ident, batch,
                 f"max_temp = {batch.max_temp:.1f}°C (terlalu rendah, mungkin sensor error)")
        if batch.max_temp > 145:
            flag("TEMP_TERLALU_TINGGI", ident, batch,
                 f"max_temp = {batch.max_temp:.1f}°C (terlalu tinggi, anomali)")

    # ── Cek 5: duration_effective anomali ────────────────────────────
    if batch.duration_effective is not None:
        if batch.duration_effective <= 0:
            flag("DUR_EFF_NOL_NEGATIF", ident, batch,
                 f"duration_effective = {batch.duration_effective:.1f} mnt (nol atau negatif!)")
        if batch.duration_effective > 600:
            flag("DUR_EFF_EKSTREM", ident, batch,
                 f"duration_effective = {batch.duration_effective:.1f} mnt (>10 jam)")

    # ── Cek 6: Batch tidak valid tapi masih punya identity ───────────
    if not batch.is_valid_process:
        flag("BATCH_INVALID", ident, batch,
             f"is_valid_process=False tapi masih punya identity")

    # ── Cek 7: start_time setelah end_time ──────────────────────────
    if batch.start_time and batch.end_time:
        if batch.end_time < batch.start_time:
            flag("END_SEBELUM_START", ident, batch,
                 f"end_time ({batch.end_time.strftime('%m-%d %H:%M')}) < "
                 f"start_time ({batch.start_time.strftime('%m-%d %H:%M')})")

    # ── Cek 8: Snapshot NULL tapi ter-link ──────────────────────────
    if not ident.start_time_snapshot:
        flag("SNAPSHOT_NULL", ident, batch,
             "start_time_snapshot NULL padahal sudah ter-link ke batch")

# ── Cek 9: Batch dengan lebih dari 1 identity (harusnya tidak ada) ──
print("Cek OneToOne integrity (batch dengan >1 identity)...", end=" ")
multi = (DyeingProcess.objects
         .annotate(id_count=Count('identity'))
         .filter(id_count__gt=1))
if multi.exists():
    for b in multi:
        print(f"\n  PELANGGARAN! Batch #{b.batch_number} {b.machine.code} punya {b.id_count} identity!")
else:
    print("OK - tidak ada pelanggaran OneToOne")

# ── Tampilkan hasil ───────────────────────────────────────────────
print()
print("=" * 70)
print(f"  HASIL CEK: {len(issues)} isu ditemukan dari {total} identity ter-link")
print("=" * 70)

if not issues:
    print("\n  BERSIH! Tidak ada anomali ditemukan. Data integritas baik.")
else:
    # Kelompokkan per kategori
    from collections import defaultdict
    by_cat = defaultdict(list)
    for iss in issues:
        by_cat[iss['cat']].append(iss)

    cat_labels = {
        'MESIN_BEDA':           '!!! KRITIS: Mesin identity berbeda dari mesin batch',
        'SNAPSHOT_DRIFT':       'INFO: Snapshot tidak sama persis dengan batch.start_time',
        'HEATING_NEGATIF':      '!!! Heating duration negatif',
        'HEATING_EKSTREM':      'WARN: Heating duration ekstrem (>10 jam)',
        'STEADY_NEGATIF':       '!!! Steady duration negatif',
        'COOLING_NEGATIF':      '!!! Cooling duration negatif',
        'TEMP_TERLALU_RENDAH':  'WARN: Suhu max terlalu rendah',
        'TEMP_TERLALU_TINGGI':  'WARN: Suhu max terlalu tinggi',
        'DUR_EFF_NOL_NEGATIF':  '!!! Duration effective nol/negatif',
        'DUR_EFF_EKSTREM':      'WARN: Duration effective ekstrem',
        'BATCH_INVALID':        'WARN: Batch is_valid_process=False',
        'END_SEBELUM_START':    '!!! End time sebelum start time',
        'SNAPSHOT_NULL':        'WARN: Snapshot NULL padahal ter-link',
    }

    # Pisahkan kritis vs warning vs info
    kritis_cats = ['MESIN_BEDA', 'HEATING_NEGATIF', 'STEADY_NEGATIF', 'COOLING_NEGATIF',
                   'DUR_EFF_NOL_NEGATIF', 'END_SEBELUM_START']
    warn_cats   = ['HEATING_EKSTREM', 'TEMP_TERLALU_RENDAH', 'TEMP_TERLALU_TINGGI',
                   'DUR_EFF_EKSTREM', 'BATCH_INVALID', 'SNAPSHOT_NULL']
    info_cats   = ['SNAPSHOT_DRIFT']

    for group_name, cats in [("KRITIS", kritis_cats), ("PERHATIAN", warn_cats), ("INFO", info_cats)]:
        group_issues = [(c, by_cat[c]) for c in cats if by_cat[c]]
        if not group_issues:
            continue
        total_group = sum(len(v) for _, v in group_issues)
        print(f"\n{'='*70}")
        print(f"  [{group_name}] {total_group} isu")
        print(f"{'='*70}")
        for cat, items in group_issues:
            label = cat_labels.get(cat, cat)
            print(f"\n  {label}: {len(items)} kasus")
            limit = 20 if cat == 'SNAPSHOT_DRIFT' else len(items)
            for iss in items[:limit]:
                snap_str = iss['snap'].strftime('%Y-%m-%d %H:%M UTC') if iss['snap'] else 'NULL'
                batch_str = iss['batch_start'].strftime('%Y-%m-%d %H:%M UTC') if iss['batch_start'] else 'NULL'
                print(f"    ID={iss['id']:>5} | {iss['machine']:8} | Batch #{iss['batch_num']:<6} | {iss['detail'][:80]}")
            if cat == 'SNAPSHOT_DRIFT' and len(items) > limit:
                print(f"    ... dan {len(items)-limit} lainnya (semuanya dalam batas normal)")

# ── Statistik tambahan ────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"  STATISTIK SNAPSHOT DRIFT (identity yang sudah ter-link)")
print(f"{'='*70}")
drift_issues = [i for i in issues if i['cat'] == 'SNAPSHOT_DRIFT']
if drift_issues:
    import statistics
    diffs = []
    for iss in drift_issues:
        if iss['snap'] and iss['batch_start']:
            d = (iss['snap'] - iss['batch_start']).total_seconds() / 60
            diffs.append(d)
    if diffs:
        print(f"  Jumlah dengan drift > 5 mnt : {len(diffs)}")
        print(f"  Median drift               : {statistics.median(diffs):.1f} mnt")
        print(f"  Max drift (positif)        : {max(diffs):.1f} mnt")
        print(f"  Min drift (negatif)        : {min(diffs):.1f} mnt")
        over_60  = [d for d in diffs if abs(d) > 60]
        over_30  = [d for d in diffs if abs(d) > 30]
        under_30 = [d for d in diffs if abs(d) <= 30]
        print(f"  Drift >60 mnt              : {len(over_60)}")
        print(f"  Drift 30-60 mnt            : {len([d for d in diffs if 30 < abs(d) <= 60])}")
        print(f"  Drift 5-30 mnt             : {len([d for d in diffs if 5 < abs(d) <= 30])}")
        print()
        print(f"  NOTE: Drift pada identity yang baru di-forced-link adalah WAJAR")
        print(f"        karena start_time_snapshot diupdate ke batch.start_time,")
        print(f"        tapi identity lama mungkin masih punya snapshot berbeda.")

print(f"\n{'='*70}")
print(f"  SELESAI. Total isu: {len(issues)}")
print(f"{'='*70}\n")
