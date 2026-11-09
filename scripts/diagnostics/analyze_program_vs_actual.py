"""
=======================================================================
ANALISIS DATA PROGRAM vs AKTUAL - DyeingAnalytics
=======================================================================
Cek kesesuaian antara:
  - Program ideal (durasi_ideal, suhu_max, durasi_heating/keeping/cooling)
  - Data aktual batch (duration_effective, max_temp, heating/steady/cooling_duration)

Deteksi:
  1. Program tanpa data ideal lengkap
  2. Data aktual yang outlier per program
  3. Distribusi durasi & suhu per program
  4. Efisiensi abnormal (< 30% atau > 150%)
  5. Batch aktual yang tampaknya salah program
  6. Missing fields kritis
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
from datetime import timedelta
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess, ProgramMaster
from django.db.models import Avg, Count, Min, Max, StdDev, Sum, F, FloatField, ExpressionWrapper, Q

print("=" * 70)
print("  ANALISIS DATA PROGRAM vs AKTUAL - DyeingAnalytics")
print("=" * 70)

# ── Query base: hanya yang linked + punya program + is_valid ─────────────
qs = DyeingIdentity.objects.filter(
    dyeing_process__isnull=False,
    program__isnull=False,
    dyeing_process__is_valid_process=True
).select_related('machine', 'dyeing_process', 'program').order_by('program__nama', 'dyeing_process__start_time')

total = qs.count()
print(f"\nTotal records di DyeingAnalytics (linked + punya program): {total}")

# ── Cek Program Master ────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  [1] KELENGKAPAN DATA PROGRAM MASTER")
print("=" * 70)

programs = ProgramMaster.objects.all().order_by('nama')
print(f"\nTotal program: {programs.count()}\n")
print(f"  {'Nama Program':25} | {'Suhu Max':>9} | {'Tot Ideal':>10} | {'Heat Ideal':>11} | {'Keep Ideal':>11} | {'Cool Ideal':>11} | {'Records':>7}")
print(f"  {'-'*25}-+-{'-'*9}-+-{'-'*10}-+-{'-'*11}-+-{'-'*11}-+-{'-'*11}-+-{'-'*7}")

program_issues = []
for p in programs:
    missing = []
    if p.suhu_max is None:      missing.append("suhu_max")
    if p.durasi_ideal is None:  missing.append("durasi_ideal")
    if p.durasi_heating_ideal is None: missing.append("heat_ideal")
    if p.durasi_keeping_ideal is None: missing.append("keep_ideal")
    if p.durasi_cooling_ideal is None: missing.append("cool_ideal")

    rec_count = qs.filter(program=p).count()

    suhu    = f"{p.suhu_max:.0f}°C"    if p.suhu_max is not None else "KOSONG"
    tot     = f"{p.durasi_ideal:.0f}m" if p.durasi_ideal is not None else "KOSONG"
    heat    = f"{p.durasi_heating_ideal:.0f}m" if p.durasi_heating_ideal is not None else "KOSONG"
    keep    = f"{p.durasi_keeping_ideal:.0f}m" if p.durasi_keeping_ideal is not None else "KOSONG"
    cool    = f"{p.durasi_cooling_ideal:.0f}m" if p.durasi_cooling_ideal is not None else "KOSONG"

    flag = " <-- DATA TIDAK LENGKAP" if missing else ""
    print(f"  {p.nama:25} | {suhu:>9} | {tot:>10} | {heat:>11} | {keep:>11} | {cool:>11} | {rec_count:>7}{flag}")

    if missing and rec_count > 0:
        program_issues.append((p, missing, rec_count))

if program_issues:
    print(f"\n  PROGRAM TIDAK LENGKAP YANG PUNYA DATA ANALYTICS ({len(program_issues)}):")
    for p, missing, count in program_issues:
        print(f"    -> {p.nama}: field kosong = {missing} | {count} records terdampak")

# ── Analisis per Program: Distribusi Aktual ───────────────────────────────
print("\n" + "=" * 70)
print("  [2] DISTRIBUSI DATA AKTUAL PER PROGRAM")
print("=" * 70)

# Agregasi per program
agg_per_program = (
    qs
    .values('program__id', 'program__nama',
            'program__durasi_ideal', 'program__suhu_max',
            'program__durasi_heating_ideal', 'program__durasi_keeping_ideal', 'program__durasi_cooling_ideal')
    .annotate(
        n=Count('id'),
        avg_dur_eff=Avg('dyeing_process__duration_effective'),
        min_dur_eff=Min('dyeing_process__duration_effective'),
        max_dur_eff=Max('dyeing_process__duration_effective'),
        avg_max_temp=Avg('dyeing_process__max_temp'),
        min_max_temp=Min('dyeing_process__max_temp'),
        max_max_temp=Max('dyeing_process__max_temp'),
        avg_heating=Avg('dyeing_process__heating_duration'),
        avg_steady=Avg('dyeing_process__steady_duration'),
        avg_cooling=Avg('dyeing_process__cooling_duration'),
        avg_real_heat=Avg('dyeing_process__real_heating_duration'),
    )
    .order_by('program__nama')
)

anomalies = []   # untuk list semua anomali spesifik

for pg in agg_per_program:
    pname = pg['program__nama']
    n     = pg['n']
    ideal = pg['program__durasi_ideal']
    suhu_max_ideal = pg['program__suhu_max']

    avg_eff = pg['avg_dur_eff']
    min_eff = pg['min_dur_eff']
    max_eff = pg['max_dur_eff']
    avg_temp = pg['avg_max_temp']
    min_temp = pg['min_max_temp']
    max_temp = pg['max_max_temp']
    avg_heat = pg['avg_heating']
    avg_ste  = pg['avg_steady']
    avg_cool = pg['avg_cooling']

    flags = []
    if ideal and avg_eff:
        eff_pct = ideal / avg_eff * 100
        if eff_pct < 50:
            flags.append(f"AVG EFISIENSI RENDAH ({eff_pct:.0f}%)")
        if eff_pct > 130:
            flags.append(f"AVG EFISIENSI TINGGI ANEH ({eff_pct:.0f}%)")
        if max_eff and max_eff > ideal * 3:
            flags.append(f"MAX DUR_EFF SANGAT BESAR ({max_eff:.0f}m vs ideal {ideal:.0f}m)")
        if min_eff and min_eff < ideal * 0.3:
            flags.append(f"MIN DUR_EFF SANGAT KECIL ({min_eff:.0f}m vs ideal {ideal:.0f}m)")

    if suhu_max_ideal and avg_temp:
        temp_diff = avg_temp - suhu_max_ideal
        if temp_diff < -20:
            flags.append(f"AVG SUHU TERLALU RENDAH (avg={avg_temp:.1f}°C, ideal={suhu_max_ideal}°C, gap={temp_diff:.1f})")
        if temp_diff > 15:
            flags.append(f"AVG SUHU MELEBIHI IDEAL (avg={avg_temp:.1f}°C, ideal={suhu_max_ideal}°C, gap=+{temp_diff:.1f})")
    if max_temp and max_temp > 145:
        flags.append(f"MAX SUHU ANOMALI ({max_temp:.1f}°C > 145°C)")
    if min_temp and min_temp < 40 and n > 2:
        flags.append(f"MIN SUHU SANGAT RENDAH ({min_temp:.1f}°C)")

    flag_str = " | ".join(flags)
    eff_str  = f"{ideal/avg_eff*100:.0f}%" if ideal and avg_eff else "-"
    avg_eff_str  = f"{avg_eff:.0f}m"  if avg_eff  else "-"
    ideal_str    = f"{ideal:.0f}m"    if ideal     else "-"
    avg_temp_str = f"{avg_temp:.1f}°C" if avg_temp else "-"
    max_temp_str = f"{max_temp:.1f}°C" if max_temp else "-"

    print(f"\n  Program: {pname} (n={n})")
    print(f"  {'Metric':25} | {'Ideal':>8} | {'Avg Aktual':>10} | {'Min':>8} | {'Max':>8} | Efisiensi")
    print(f"  {'-'*25}-+-{'-'*8}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-----------")
    print(f"  {'Durasi Efektif':25} | {ideal_str:>8} | {avg_eff_str:>10} | {f'{min_eff:.0f}m' if min_eff else '-':>8} | {f'{max_eff:.0f}m' if max_eff else '-':>8} | {eff_str}")
    print(f"  {'Max Temp':25} | {f'{suhu_max_ideal:.0f}°C' if suhu_max_ideal else '-':>8} | {avg_temp_str:>10} | {f'{min_temp:.1f}°C' if min_temp else '-':>8} | {max_temp_str:>8}")
    heat_str = f"{pg['program__durasi_heating_ideal']:.0f}m" if pg['program__durasi_heating_ideal'] else "-"
    keep_str = f"{pg['program__durasi_keeping_ideal']:.0f}m" if pg['program__durasi_keeping_ideal'] else "-"
    cool_str = f"{pg['program__durasi_cooling_ideal']:.0f}m" if pg['program__durasi_cooling_ideal'] else "-"
    print(f"  {'Heating Dur':25} | {heat_str:>8} | {f'{avg_heat:.0f}m' if avg_heat else '-':>10}")
    print(f"  {'Keeping/Steady Dur':25} | {keep_str:>8} | {f'{avg_ste:.0f}m' if avg_ste else '-':>10}")
    print(f"  {'Cooling Dur':25} | {cool_str:>8} | {f'{avg_cool:.0f}m' if avg_cool else '-':>10}")

    if flags:
        print(f"  *** ANOMALI: {' | '.join(flags)}")
        anomalies.append({'program': pname, 'n': n, 'flags': flags})

# ── Outlier individual record ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("  [3] OUTLIER INDIVIDUAL RECORD (per program, nilai ekstrem)")
print("=" * 70)

all_records = list(qs.select_related('machine', 'dyeing_process', 'program'))

# Group by program
by_program = defaultdict(list)
for r in all_records:
    by_program[r.program.nama].append(r)

outlier_records = []

for pname, records in sorted(by_program.items()):
    effs = [r.dyeing_process.duration_effective for r in records if r.dyeing_process.duration_effective]
    temps = [r.dyeing_process.max_temp for r in records if r.dyeing_process.max_temp]
    heats = [r.dyeing_process.heating_duration for r in records if r.dyeing_process.heating_duration]

    if len(effs) < 3:
        continue

    avg_eff  = statistics.mean(effs)
    std_eff  = statistics.stdev(effs) if len(effs) > 1 else 0
    avg_temp = statistics.mean(temps) if temps else None
    std_temp = statistics.stdev(temps) if len(temps) > 1 else 0

    for r in records:
        batch = r.dyeing_process
        flags = []

        # Outlier durasi efektif (z-score > 2.5)
        if batch.duration_effective and std_eff > 0:
            z = (batch.duration_effective - avg_eff) / std_eff
            if z > 2.5:
                flags.append(f"DUR_EFF OUTLIER TINGGI ({batch.duration_effective:.0f}m, avg={avg_eff:.0f}m, z={z:.1f})")
            elif z < -2.5:
                flags.append(f"DUR_EFF OUTLIER RENDAH ({batch.duration_effective:.0f}m, avg={avg_eff:.0f}m, z={z:.1f})")

        # Outlier suhu max
        if batch.max_temp and avg_temp and std_temp > 0:
            z_t = (batch.max_temp - avg_temp) / std_temp
            if z_t > 2.5:
                flags.append(f"SUHU OUTLIER TINGGI ({batch.max_temp:.1f}°C, avg={avg_temp:.1f}°C, z={z_t:.1f})")
            elif z_t < -2.5:
                flags.append(f"SUHU OUTLIER RENDAH ({batch.max_temp:.1f}°C, avg={avg_temp:.1f}°C, z={z_t:.1f})")

        # Durasi heating negatif atau nol
        if batch.heating_duration is not None and batch.heating_duration <= 0:
            flags.append(f"HEATING DUR = {batch.heating_duration:.0f}m")

        # Durasi cooling negatif
        if batch.cooling_duration is not None and batch.cooling_duration < 0:
            flags.append(f"COOLING DUR NEGATIF = {batch.cooling_duration:.0f}m")

        # Max temp sangat rendah untuk proses panas (misal Fresh/Creaping seharusnya >80°C)
        if batch.max_temp and batch.max_temp < 50:
            flags.append(f"MAX TEMP SANGAT RENDAH ({batch.max_temp:.1f}°C)")

        if flags:
            outlier_records.append({
                'id': r.id,
                'machine': r.machine.code,
                'program': pname,
                'batch_num': batch.batch_number,
                'batch_start': batch.start_time.strftime('%Y-%m-%d %H:%M UTC'),
                'flags': flags,
                'dur_eff': batch.duration_effective,
                'max_temp': batch.max_temp,
            })

print(f"\n  Total outlier individual: {len(outlier_records)}")
for o in outlier_records:
    print(f"\n  ID={o['id']:>5} | {o['machine']:8} | Batch #{o['batch_num']:<5} | {o['batch_start']}")
    print(f"         Program: {o['program']}")
    for f in o['flags']:
        print(f"         !! {f}")

# ── Cek records tanpa data kritis ─────────────────────────────────────────
print("\n" + "=" * 70)
print("  [4] RECORDS DENGAN FIELD KRITIS KOSONG (NULL)")
print("=" * 70)

null_checks = {
    'duration_effective NULL'    : qs.filter(dyeing_process__duration_effective__isnull=True).count(),
    'max_temp NULL'              : qs.filter(dyeing_process__max_temp__isnull=True).count(),
    'heating_duration NULL'      : qs.filter(dyeing_process__heating_duration__isnull=True).count(),
    'steady_duration NULL'       : qs.filter(dyeing_process__steady_duration__isnull=True).count(),
    'cooling_duration NULL'      : qs.filter(dyeing_process__cooling_duration__isnull=True).count(),
    'heating_start_time NULL'    : qs.filter(dyeing_process__heating_start_time__isnull=True).count(),
    'reached_70c_time NULL'      : qs.filter(dyeing_process__reached_70c_time__isnull=True).count(),
    'real_heating_duration NULL' : qs.filter(dyeing_process__real_heating_duration__isnull=True).count(),
}

print()
any_null = False
for field, count in null_checks.items():
    pct = count / total * 100 if total else 0
    status = "OK" if count == 0 else ("WARN" if pct < 20 else "TINGGI")
    print(f"  {field:35} : {count:>5} ({pct:.1f}%) [{status}]")
    if count > 0:
        any_null = True

# Detail reached_70c_time NULL → ini penyebab duration_effective ekstrem
null_70c = qs.filter(
    dyeing_process__reached_70c_time__isnull=True,
    dyeing_process__duration_effective__isnull=False
).values('program__nama').annotate(n=Count('id')).order_by('-n')
if null_70c:
    print(f"\n  reached_70c_time NULL tapi duration_effective ADA (per program):")
    for row in null_70c:
        print(f"    {row['program__nama']:25}: {row['n']} records")

# ── Ringkasan Akhir ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  [5] RINGKASAN ANOMALI")
print("=" * 70)
print(f"\n  Total records di-analisis        : {total}")
print(f"  Program dengan data tidak lengkap: {len(program_issues)}")
print(f"  Program dengan anomali agregat   : {len(anomalies)}")
print(f"  Record outlier individual        : {len(outlier_records)}")
print(f"  Field kritis ada yang NULL       : {'Ya' if any_null else 'Tidak'}")

if anomalies:
    print(f"\n  PROGRAM DENGAN ANOMALI:")
    for a in anomalies:
        print(f"    {a['program']} (n={a['n']}): {' | '.join(a['flags'])}")

print(f"\n{'='*70}\n")
