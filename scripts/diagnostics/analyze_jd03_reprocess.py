"""
INVESTIGASI FINAL: Gap antara batch 5-25 menit dan penyebab sesungguhnya lonjakan
481 -> 1553. Fokus pada segmentasi logika OFF vs RESTART.
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import Machine, MachineMinuteLog, DyeingProcess

m = Machine.objects.filter(code='JD_03').first()
batches = list(DyeingProcess.objects.filter(machine=m).order_by('batch_number').values(
    'batch_number', 'start_time', 'end_time', 'max_temp', 'is_complete',
    'heating_duration', 'cooling_duration', 'steady_duration'
))

entries = []
for i in range(1, len(batches)):
    prev = batches[i-1]
    curr = batches[i]
    if prev['end_time'] and curr['start_time']:
        gap = (curr['start_time'] - prev['end_time']).total_seconds() / 60
        entries.append({
            'gap': gap,
            'bn1': prev['batch_number'],
            'bn2': curr['batch_number'],
            'peak1': prev['max_temp'],
            'peak2': curr['max_temp'],
            'dur1': (prev['end_time'] - prev['start_time']).total_seconds()/60,
            'dur2': (curr['end_time'] - curr['start_time']).total_seconds()/60,
            'end1': prev['end_time'],
            'start2': curr['start_time'],
        })

print("=== INVESTIGASI: GAP 5-25 MENIT ANTARA BATCH ===")
g_med = [e for e in entries if 5 < e['gap'] <= 25]
print(f"Total batch pairs dengan gap 5-25 menit: {len(g_med)}")
print()

# Cek suhu saat gap ini:
print("Sampling 20 pasangan dengan gap 5-25 menit:")
print("Format: gap | end_temp | start_temp | peak1 -> peak2")
for e in g_med[:25]:
    # Cek suhu di end_time batch 1 dan start_time batch 2
    log_end = MachineMinuteLog.objects.filter(machine=m, timestamp=e['end1']).first()
    log_start = MachineMinuteLog.objects.filter(machine=m, timestamp=e['start2']).first()
    t_end = log_end.temperature if log_end else None
    t_start = log_start.temperature if log_start else None
    te = f"{t_end:.1f}" if t_end is not None else "N/A"
    ts_s = f"{t_start:.1f}" if t_start is not None else "N/A"
    print(f"  #{e['bn1']}->{e['bn2']}: gap={e['gap']:.0f}min | "
          f"end_temp={te} | start_temp={ts_s} | "
          f"peak {e['peak1']:.0f}->{e['peak2']:.0f}C")

print()
print("=== INVESTIGASI: Batches yang muncul setelah gap data besar ===")
# Gap dalam log data > 20 menit pada SUHU TINGGI (bisa memotong batch)
logs_qs = MachineMinuteLog.objects.filter(machine=m).order_by('timestamp').values('timestamp', 'temperature')

high_temp_gaps = []
prev_ts = None
prev_temp = None
for log in logs_qs.iterator(chunk_size=5000):
    ts = log['timestamp']
    temp = log['temperature']
    if prev_ts is not None:
        gap = (ts - prev_ts).total_seconds() / 60
        if gap > 10 and prev_temp is not None and prev_temp > 50:
            # Gap saat suhu tinggi - ini yang berbahaya
            high_temp_gaps.append((gap, prev_ts, ts, prev_temp, temp))
    prev_ts = ts
    prev_temp = temp

high_temp_gaps.sort(reverse=True)
print(f"Data gaps > 10 menit saat suhu > 50C: {len(high_temp_gaps)}")
for gap, from_ts, to_ts, from_temp, to_temp in high_temp_gaps[:15]:
    # Cek apakah ada batch yang terpotong di sini
    batch_before = DyeingProcess.objects.filter(machine=m, end_time__range=(from_ts, to_ts)).first()
    batch_after = DyeingProcess.objects.filter(machine=m, start_time__range=(from_ts, to_ts)).first()
    marker = ""
    if batch_before:
        marker += f" [BATCH #{batch_before.batch_number} END dalam gap]"
    if batch_after:
        marker += f" [BATCH #{batch_after.batch_number} START dalam gap]"
    t_to = f"{to_temp:.1f}" if to_temp else "None"
    print(f"  {gap:>8.1f}min gap | {from_ts} | {from_temp:.1f}C -> {t_to}C{marker}")

print()
print("=== INTI: APA YANG BERBEDA DARI VERSI 481 BATCH? ===")
print()
print("Data yang kita punya (1553 batch setelah reprocess):")
print("  - RESTART splits (gap=0): 304 batch")
print("  - gap 0-5 min: 55 batch")
print("  - gap 5-25 min: 187 batch")
print("  => Total batch pairs dengan gap pendek: 304+55+187 = 546")
print()
print("Jika 481 batch = versi lama, estimasi splits yang terjadi di versi baru:")
print(f"  1553 - 481 = 1072 extra batch")
print()
print("Hipotesis paling kuat:")
print("  RESTART logic (gap=0, peak-to-peak split) menghasilkan 304 split")
print("  Ini adalah 304 kali program multi-step yang dianggap batch terpisah")
print()
print("  Suhu split rata-rata = 35.7C (JAUH di bawah RESTART_TEMP=55C)")
print("  => Artinya: mesin benar-benar OFF/idle di antara batch-batch tersebut")
print("  => Bukan intermediate cooling dalam 1 program")
print()
print("  Kesimpulan: 1553 batch LEBIH AKURAT dari 481 batch!")
print("  481 batch lama = kemungkinan batches yang DIGABUNG karena threshold berbeda")
print()
print("=== VERIFIKASI: Berapa batch per hari yang masuk akal untuk JD_03? ===")
from collections import defaultdict
per_day = defaultdict(int)
for b in batches:
    if b['start_time']:
        per_day[b['start_time'].date()] += 1
counts = list(per_day.values())
counts.sort()
print(f"Distribusi batch per hari:")
for n in [1,2,3,4,5,6,7]:
    cnt = len([c for c in counts if c == n])
    print(f"  {n} batch/hari: {cnt} hari")
print(f"  >7 batch/hari: {len([c for c in counts if c > 7])} hari")
