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

from monitoring.models import DyeingIdentity

qs = DyeingIdentity.objects.filter(
    dyeing_process__isnull=False,
    program__isnull=False,
    dyeing_process__is_valid_process=True,
    dyeing_process__max_temp__isnull=False,
    program__suhu_max__isnull=False
).select_related('machine', 'dyeing_process', 'program')

machine_diffs = defaultdict(list)
machine_freq = defaultdict(int)
suhu_max_diffs = defaultdict(list)

for r in qs:
    actual = r.dyeing_process.max_temp
    prog = r.program.suhu_max
    mac = r.machine.code if r.machine else "UNKNOWN"
    
    diff = actual - prog
    
    machine_diffs[mac].append(diff)
    suhu_max_diffs[prog].append(diff)
    
    # Anggap "berbeda" jika selisih absolut lebih dari 0.5 derajat
    if abs(diff) > 0.5: 
        machine_freq[mac] += 1

print("--- MESIN YANG PALING SERING BERBEDA (Freq > 0.5 derajat) ---")
sorted_freq = sorted(machine_freq.items(), key=lambda x: x[1], reverse=True)
for mac, freq in sorted_freq:
    print(f"Mesin {mac}: {freq} kali")

print("\n--- STATISTIK PERBEDAAN (Aktual - Program) PER MESIN ---")
for mac, diffs in machine_diffs.items():
    avg = sum(diffs) / len(diffs)
    std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    print(f"Mesin {mac:<5}: Avg Diff = {avg:>6.2f}°C, StdDev = {std:>6.2f}°C, Total Data = {len(diffs)}")

print("\n--- STATISTIK BERDASARKAN SUHU MAX PROGRAM ---")
for prog_suhu, diffs in sorted(suhu_max_diffs.items()):
    avg = sum(diffs) / len(diffs)
    std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    print(f"Suhu Program {prog_suhu:>5}°C: Avg Diff = {avg:>6.2f}°C, StdDev = {std:>6.2f}°C, Total Data = {len(diffs)}")
