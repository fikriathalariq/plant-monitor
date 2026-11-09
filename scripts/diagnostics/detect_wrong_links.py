"""
=======================================================================
DETEKSI SALAH LINKED - DyeingIdentity
=======================================================================
Logika: Jika identity ter-linked ke batch yang BENAR, maka:
  - max_temp aktual ≈ suhu_max program (±toleransi wajar ~15°C)
  - heating_duration aktual ≈ durasi_heating_ideal (±toleransi wajar)
  - steady_duration aktual ≈ durasi_keeping_ideal (±toleransi wajar)
  - cooling_duration aktual ≈ durasi_cooling_ideal (±toleransi wajar)

Jika selisihnya SANGAT BESAR (outlier berat), kemungkinan salah linked.

Metode: Hitung selisih aktual vs ideal untuk setiap field,
        lalu cari outlier menggunakan IQR (lebih robust dari z-score
        karena tidak terpengaruh distribusi tidak normal).
=======================================================================
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, sys, django, statistics
from collections import defaultdict
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess, ProgramMaster
from django.db.models import Avg

print("=" * 70)
print("  DETEKSI SALAH LINKED — Suhu & Durasi vs Program Ideal")
print("=" * 70)

# ── Ambil semua records yang linked + punya program + batch valid ──────
qs = list(
    DyeingIdentity.objects
    .filter(dyeing_process__isnull=False, program__isnull=False,
            dyeing_process__is_valid_process=True)
    .select_related('machine', 'dyeing_process', 'program')
)
print(f"\nTotal records: {len(qs)}\n")

# ── Hitung selisih per record ──────────────────────────────────────────
records_with_diff = []

for r in qs:
    p  = r.program
    b  = r.dyeing_process

    # Suhu: selisih max_temp aktual vs suhu_max ideal
    diff_suhu = None
    if p.suhu_max is not None and b.max_temp is not None:
        diff_suhu = b.max_temp - p.suhu_max          # positif = lebih panas dari ideal

    # Heating: selisih heating_duration aktual vs durasi_heating_ideal
    diff_heat = None
    if p.durasi_heating_ideal is not None and b.heating_duration is not None:
        diff_heat = b.heating_duration - p.durasi_heating_ideal

    # Keeping/Steady: selisih steady_duration vs durasi_keeping_ideal
    diff_keep = None
    if p.durasi_keeping_ideal is not None and b.steady_duration is not None:
        diff_keep = b.steady_duration - p.durasi_keeping_ideal

    # Cooling: selisih cooling_duration vs durasi_cooling_ideal
    diff_cool = None
    if p.durasi_cooling_ideal is not None and b.cooling_duration is not None:
        diff_cool = b.cooling_duration - p.durasi_cooling_ideal

    records_with_diff.append({
        'id'          : r.id,
        'machine'     : r.machine.code,
        'program'     : p.nama,
        'program_id'  : p.id,
        'batch_num'   : b.batch_number,
        'batch_start' : b.start_time,
        'snap'        : r.start_time_snapshot,
        # Ideal
        'ideal_suhu'  : p.suhu_max,
        'ideal_heat'  : p.durasi_heating_ideal,
        'ideal_keep'  : p.durasi_keeping_ideal,
        'ideal_cool'  : p.durasi_cooling_ideal,
        # Aktual
        'act_suhu'    : b.max_temp,
        'act_heat'    : b.heating_duration,
        'act_keep'    : b.steady_duration,
        'act_cool'    : b.cooling_duration,
        # Selisih (aktual - ideal)
        'diff_suhu'   : diff_suhu,
        'diff_heat'   : diff_heat,
        'diff_keep'   : diff_keep,
        'diff_cool'   : diff_cool,
        'obj'         : r,
    })

# ── Fungsi IQR outlier ─────────────────────────────────────────────────
def iqr_bounds(values, multiplier=2.5):
    """Return (lower, upper) fence pakai IQR method."""
    if len(values) < 4:
        return None, None
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    return q1 - multiplier * iqr, q3 + multiplier * iqr

# ── Deteksi outlier per program ────────────────────────────────────────
# Group per program
by_prog = defaultdict(list)
for r in records_with_diff:
    by_prog[r['program']].append(r)

flagged = []   # records yang dicurigai salah linked

print(f"{'='*70}")
print(f"  HASIL PER PROGRAM")
print(f"{'='*70}")

for prog_name, recs in sorted(by_prog.items()):
    n = len(recs)
    if n < 3:
        continue  # skip program dengan < 3 data, tidak cukup untuk statistik

    # Kumpulkan nilai selisih yang tidak None
    d_suhu = [r['diff_suhu'] for r in recs if r['diff_suhu'] is not None]
    d_heat = [r['diff_heat'] for r in recs if r['diff_heat'] is not None]
    d_keep = [r['diff_keep'] for r in recs if r['diff_keep'] is not None]
    d_cool = [r['diff_cool'] for r in recs if r['diff_cool'] is not None]

    # Statistik ringkas
    def stats_str(vals, unit='m'):
        if not vals: return "N/A"
        avg = statistics.mean(vals)
        med = statistics.median(vals)
        mn  = min(vals)
        mx  = max(vals)
        sd  = statistics.stdev(vals) if len(vals) > 1 else 0
        return f"avg={avg:+.0f}{unit} | med={med:+.0f}{unit} | min={mn:+.0f}{unit} | max={mx:+.0f}{unit} | sd={sd:.0f}{unit}"

    # IQR bounds per field
    lo_suhu, hi_suhu = iqr_bounds(d_suhu) if d_suhu else (None, None)
    lo_heat, hi_heat = iqr_bounds(d_heat) if d_heat else (None, None)
    lo_keep, hi_keep = iqr_bounds(d_keep) if d_keep else (None, None)
    lo_cool, hi_cool = iqr_bounds(d_cool) if d_cool else (None, None)

    # Cek apakah ada outlier
    prog_outliers = []
    for r in recs:
        rec_flags = []

        if r['diff_suhu'] is not None and lo_suhu is not None:
            if r['diff_suhu'] < lo_suhu or r['diff_suhu'] > hi_suhu:
                rec_flags.append(
                    f"SUHU: aktual={r['act_suhu']:.0f}°C, ideal={r['ideal_suhu']:.0f}°C, "
                    f"selisih={r['diff_suhu']:+.0f}°C [batas: {lo_suhu:.0f}..{hi_suhu:.0f}]"
                )

        if r['diff_heat'] is not None and lo_heat is not None:
            if r['diff_heat'] < lo_heat or r['diff_heat'] > hi_heat:
                rec_flags.append(
                    f"HEATING: aktual={r['act_heat']:.0f}m, ideal={r['ideal_heat']:.0f}m, "
                    f"selisih={r['diff_heat']:+.0f}m [batas: {lo_heat:.0f}..{hi_heat:.0f}]"
                )

        if r['diff_keep'] is not None and lo_keep is not None:
            if r['diff_keep'] < lo_keep or r['diff_keep'] > hi_keep:
                rec_flags.append(
                    f"KEEPING: aktual={r['act_keep']:.0f}m, ideal={r['ideal_keep']:.0f}m, "
                    f"selisih={r['diff_keep']:+.0f}m [batas: {lo_keep:.0f}..{hi_keep:.0f}]"
                )

        if r['diff_cool'] is not None and lo_cool is not None:
            if r['diff_cool'] < lo_cool or r['diff_cool'] > hi_cool:
                rec_flags.append(
                    f"COOLING: aktual={r['act_cool']:.0f}m, ideal={r['ideal_cool']:.0f}m, "
                    f"selisih={r['diff_cool']:+.0f}m [batas: {lo_cool:.0f}..{hi_cool:.0f}]"
                )

        # Cek absolut: suhu aktual vs ideal sangat jauh (>25°C) — hard rule
        if r['diff_suhu'] is not None and abs(r['diff_suhu']) > 25:
            suhu_flag = f"SUHU JAUH: aktual={r['act_suhu']:.0f}°C, ideal={r['ideal_suhu']:.0f}°C, gap={r['diff_suhu']:+.0f}°C"
            if suhu_flag not in str(rec_flags):
                rec_flags.append(suhu_flag)

        if rec_flags:
            # Hitung skor kecurigaan: semakin banyak flag, semakin mencurigakan
            suspicion = len(rec_flags)
            r['flags'] = rec_flags
            r['suspicion'] = suspicion
            prog_outliers.append(r)
            flagged.append(r)

    if prog_outliers:
        print(f"\n  Program: {prog_name} (n={n})")
        print(f"  Selisih (aktual-ideal) | Suhu   : {stats_str(d_suhu, '°C')}")
        print(f"                         | Heating: {stats_str(d_heat)}")
        print(f"                         | Keeping: {stats_str(d_keep)}")
        print(f"                         | Cooling: {stats_str(d_cool)}")
        print(f"  Outlier ditemukan: {len(prog_outliers)}")
        for r in sorted(prog_outliers, key=lambda x: -x['suspicion']):
            batch_start = r['batch_start'].strftime('%Y-%m-%d %H:%M UTC')
            snap_str    = r['snap'].strftime('%Y-%m-%d %H:%M UTC') if r['snap'] else 'N/A'
            susp_label  = ['', '⚠', '⚠⚠', '🔴'][min(r['suspicion'], 3)]
            print(f"\n    {susp_label} ID={r['id']:>5} | {r['machine']:8} | Batch #{r['batch_num']:<5} | {batch_start}")
            for f in r['flags']:
                print(f"       -> {f}")

# ── Rekap final: sorted by suspicion ─────────────────────────────────────
print(f"\n{'='*70}")
print(f"  REKAP: CANDIDATES SALAH LINKED (diurutkan dari paling mencurigakan)")
print(f"{'='*70}\n")

# Pisah berdasarkan jumlah flag (semakin banyak = semakin mencurigakan)
flagged_sorted = sorted(flagged, key=lambda x: -x['suspicion'])
multi_flag = [r for r in flagged_sorted if r['suspicion'] >= 2]
single_flag = [r for r in flagged_sorted if r['suspicion'] == 1]

print(f"  Total outlier       : {len(flagged)}")
print(f"  Multi-flag (>=2)    : {len(multi_flag)}  ← PALING DICURIGAI salah linked")
print(f"  Single-flag         : {len(single_flag)} ← outlier ringan / satu dimensi saja")

if multi_flag:
    print(f"\n  {'='*68}")
    print(f"  MULTI-FLAG (kemungkinan besar SALAH LINKED):")
    print(f"  {'='*68}")
    print(f"  {'ID':>6} | {'Mesin':8} | {'Program':8} | {'Batch #':>7} | {'Batch Start':17} | {'#Flag':>5}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*17}-+-{'-'*5}")
    for r in multi_flag:
        bs = r['batch_start'].strftime('%m-%d %H:%M')
        print(f"  {r['id']:>6} | {r['machine']:8} | {r['program']:8} | Batch #{r['batch_num']:<4} | {bs:17} | {r['suspicion']:>5}")
        for f in r['flags']:
            print(f"         -> {f}")
        print()

print(f"\n{'='*70}\n  SELESAI\n{'='*70}\n")
