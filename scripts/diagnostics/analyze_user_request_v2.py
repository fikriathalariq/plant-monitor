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

data = defaultdict(lambda: defaultdict(list))

for r in qs:
    actual = r.dyeing_process.max_temp
    prog = r.program.suhu_max
    mac = r.machine.code if r.machine else "UNKNOWN"
    
    diff = actual - prog
    data[mac][prog].append(diff)

artifact_path = r"C:\Users\HP\.gemini\antigravity\brain\3c9a3eae-d5be-44c9-b0b1-29e9f62c1f25\machine_temp_analysis.md"

with open(artifact_path, "w", encoding="utf-8") as f:
    f.write("# Analisis Perbedaan Suhu Max per Mesin dan Suhu Program\n\n")
    f.write("Laporan ini menyajikan rata-rata perbedaan suhu (`Aktual - Program`) serta standar deviasinya untuk setiap mesin, di-breakdown berdasarkan Suhu Max Program.\n\n")
    f.write("> [!NOTE]\n> Nilai minus (-) berarti suhu aktual lebih rendah dari suhu program, sedangkan nilai plus (+) berarti suhu aktual melebihi suhu program.\n\n")
    
    for mac in sorted(data.keys()):
        f.write(f"## Mesin {mac}\n\n")
        f.write("| Suhu Program | Rata-rata Selisih (°C) | Standar Deviasi (°C) | Total Data |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        
        for prog_suhu in sorted(data[mac].keys()):
            diffs = data[mac][prog_suhu]
            avg = sum(diffs) / len(diffs)
            std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
            
            # Format to include the + sign if positive
            avg_str = f"+{avg:.2f}" if avg > 0 else f"{avg:.2f}"
            
            f.write(f"| **{prog_suhu} °C** | {avg_str} | {std:.2f} | {len(diffs)} |\n")
        
        f.write("\n---\n\n")

print(f"Artifact created at {artifact_path}")
