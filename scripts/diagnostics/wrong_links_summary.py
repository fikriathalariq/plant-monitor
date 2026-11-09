import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django, statistics
from collections import defaultdict
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import DyeingIdentity

qs = list(
    DyeingIdentity.objects
    .filter(dyeing_process__isnull=False, program__isnull=False,
            dyeing_process__is_valid_process=True)
    .select_related('machine', 'dyeing_process', 'program')
)

def iqr_bounds(values, multiplier=2.5):
    if len(values) < 4:
        return None, None
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    return q1 - multiplier * iqr, q3 + multiplier * iqr

records_with_diff = []
for r in qs:
    p, b = r.program, r.dyeing_process
    diff_suhu = (b.max_temp - p.suhu_max)             if p.suhu_max and b.max_temp else None
    diff_heat = (b.heating_duration - p.durasi_heating_ideal) if p.durasi_heating_ideal and b.heating_duration else None
    diff_keep = (b.steady_duration - p.durasi_keeping_ideal)  if p.durasi_keeping_ideal and b.steady_duration else None
    diff_cool = (b.cooling_duration - p.durasi_cooling_ideal)  if p.durasi_cooling_ideal and b.cooling_duration else None
    records_with_diff.append(dict(
        rid=r.id, machine=r.machine.code, program=p.nama,
        batch_num=b.batch_number, batch_start=b.start_time,
        diff_suhu=diff_suhu, diff_heat=diff_heat, diff_keep=diff_keep, diff_cool=diff_cool,
        ideal_suhu=p.suhu_max, act_suhu=b.max_temp,
        ideal_heat=p.durasi_heating_ideal, act_heat=b.heating_duration,
        ideal_keep=p.durasi_keeping_ideal, act_keep=b.steady_duration,
        ideal_cool=p.durasi_cooling_ideal, act_cool=b.cooling_duration,
    ))

by_prog = defaultdict(list)
for r in records_with_diff:
    by_prog[r['program']].append(r)

flagged = []
for prog_name, recs in sorted(by_prog.items()):
    if len(recs) < 3:
        continue
    d_suhu = [r['diff_suhu'] for r in recs if r['diff_suhu'] is not None]
    d_heat = [r['diff_heat'] for r in recs if r['diff_heat'] is not None]
    d_keep = [r['diff_keep'] for r in recs if r['diff_keep'] is not None]
    d_cool = [r['diff_cool'] for r in recs if r['diff_cool'] is not None]
    lo_s, hi_s = iqr_bounds(d_suhu) if d_suhu else (None, None)
    lo_h, hi_h = iqr_bounds(d_heat) if d_heat else (None, None)
    lo_k, hi_k = iqr_bounds(d_keep) if d_keep else (None, None)
    lo_c, hi_c = iqr_bounds(d_cool) if d_cool else (None, None)
    for r in recs:
        f = []
        if r['diff_suhu'] is not None and lo_s is not None:
            if r['diff_suhu'] < lo_s or r['diff_suhu'] > hi_s:
                f.append('SUHU')
        if r['diff_heat'] is not None and lo_h is not None:
            if r['diff_heat'] < lo_h or r['diff_heat'] > hi_h:
                f.append('HEAT')
        if r['diff_keep'] is not None and lo_k is not None:
            if r['diff_keep'] < lo_k or r['diff_keep'] > hi_k:
                f.append('KEEP')
        if r['diff_cool'] is not None and lo_c is not None:
            if r['diff_cool'] < lo_c or r['diff_cool'] > hi_c:
                f.append('COOL')
        # Hard rule: suhu gap >25°C selalu dicurigai
        if r['diff_suhu'] is not None and abs(r['diff_suhu']) > 25 and 'SUHU' not in f:
            f.append('SUHU_HARD')
        if f:
            r['flags'] = f
            r['suspicion'] = len(f)
            flagged.append(r)

flagged_sorted = sorted(flagged, key=lambda x: -x['suspicion'])
multi = [r for r in flagged_sorted if r['suspicion'] >= 3]
two   = [r for r in flagged_sorted if r['suspicion'] == 2]
one   = [r for r in flagged_sorted if r['suspicion'] == 1]

print("=" * 70)
print("  RINGKASAN")
print("=" * 70)
print(f"Total outlier  : {len(flagged)}")
print(f"3+ flags KRITIS: {len(multi)}")
print(f"2 flags MEDIUM : {len(two)}")
print(f"1 flag RINGAN  : {len(one)}")

print("\n" + "=" * 70)
print("  3+ FLAGS — SANGAT DICURIGAI SALAH LINKED")
print("=" * 70)
for r in multi:
    bs = r['batch_start'].strftime('%Y-%m-%d %H:%M UTC')
    print()
    print(f"  ID={r['rid']:>5} | {r['machine']:8} | {r['program']:8} | Batch #{r['batch_num']:<5} | {bs}")
    print(f"  Flags: {r['flags']}")
    if r['diff_suhu'] is not None:
        print(f"    Suhu  : ideal={r['ideal_suhu']:.0f}C   aktual={r['act_suhu']:.1f}C   diff={r['diff_suhu']:+.1f}C")
    if r['diff_heat'] is not None:
        print(f"    Heat  : ideal={r['ideal_heat']:.0f}m   aktual={r['act_heat']:.0f}m    diff={r['diff_heat']:+.0f}m")
    if r['diff_keep'] is not None:
        print(f"    Keep  : ideal={r['ideal_keep']:.0f}m   aktual={r['act_keep']:.0f}m    diff={r['diff_keep']:+.0f}m")
    if r['diff_cool'] is not None:
        print(f"    Cool  : ideal={r['ideal_cool']:.0f}m   aktual={r['act_cool']:.0f}m    diff={r['diff_cool']:+.0f}m")

print()
print("=" * 70)
print("  2 FLAGS — MEDIUM (perlu dikonfirmasi)")
print("=" * 70)
print()
print(f"  {'ID':>6} | {'Mesin':8} | {'Program':8} | {'Batch':>6} | {'Batch Start':17} | Flags")
print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*6}-+-{'-'*17}-+-{'-------'}")
for r in two:
    bs = r['batch_start'].strftime('%m-%d %H:%M')
    print(f"  {r['rid']:>6} | {r['machine']:8} | {r['program']:8} | #{r['batch_num']:<5} | {bs:17} | {r['flags']}")
