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

data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
machine_diffs = defaultdict(list)
machine_freq = defaultdict(int)

for r in qs:
    actual = r.dyeing_process.max_temp
    prog = r.program.suhu_max
    prog_name = r.program.nama
    mac = r.machine.code if r.machine else "UNKNOWN"
    
    diff = actual - prog
    
    # Data Cleaning: Exclude differences > 20 degrees Celsius
    if abs(diff) > 20:
        continue

    data[mac][prog][prog_name].append(diff)
    machine_diffs[mac].append(diff)
    
    if abs(diff) > 0.5:
        machine_freq[mac] += 1

artifact_path = r"C:\Users\HP\.gemini\antigravity\brain\3c9a3eae-d5be-44c9-b0b1-29e9f62c1f25\machine_temp_analysis_cleaned_v2.md"

with open(artifact_path, "w", encoding="utf-8") as f:
    f.write("# Laporan Analisis Suhu Bersih per Program\n\n")
    f.write("Laporan ini menggunakan data yang telah di-cleaning (membuang selisih suhu **> 20°C**). Data dirincikan hingga ke level nama program di bawah setiap target suhu.\n\n")
    
    f.write("## 1. Peringkat Mesin (Selisih > 0.5°C, maksimal 20°C)\n")
    f.write("| Mesin | Frekuensi Beda | Total Data Bersih |\n")
    f.write("| :--- | :--- | :--- |\n")
    for mac, freq in sorted(machine_freq.items(), key=lambda x: x[1], reverse=True)[:15]:
        total_data = len(machine_diffs[mac])
        f.write(f"| **{mac}** | {freq} kali | {total_data} |\n")
    
    f.write("\n## 2. Detail Per Mesin & Anak Program\n")
    for mac in sorted(data.keys()):
        f.write(f"### Mesin {mac}\n\n")
        f.write("| Suhu / Program | Rata-rata Selisih (°C) | Standar Deviasi (°C) | Total Data |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        
        for prog_suhu in sorted(data[mac].keys()):
            # Aggregate for the whole temp group
            all_diffs = []
            for diffs in data[mac][prog_suhu].values():
                all_diffs.extend(diffs)
            
            suhu_avg = sum(all_diffs) / len(all_diffs)
            suhu_std = statistics.stdev(all_diffs) if len(all_diffs) > 1 else 0.0
            suhu_avg_str = f"+{suhu_avg:.2f}" if suhu_avg > 0 else f"{suhu_avg:.2f}"
            
            f.write(f"| **{prog_suhu} °C** | **{suhu_avg_str}** | **{suhu_std:.2f}** | **{len(all_diffs)}** |\n")
            
            # List children
            for prog_name in sorted(data[mac][prog_suhu].keys()):
                diffs = data[mac][prog_suhu][prog_name]
                avg = sum(diffs) / len(diffs)
                std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
                avg_str = f"+{avg:.2f}" if avg > 0 else f"{avg:.2f}"
                f.write(f"| &nbsp;&nbsp;&nbsp;&nbsp;↳ *{prog_name}* | {avg_str} | {std:.2f} | {len(diffs)} |\n")
                
        f.write("\n---\n\n")

print(f"Artifact created at {artifact_path}")
