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
    machine__code="JD_08",
    dyeing_process__isnull=False,
    program__isnull=False,
    dyeing_process__is_valid_process=True,
    dyeing_process__max_temp__isnull=False,
    program__suhu_max__isnull=False
).select_related('dyeing_process', 'program')

data = defaultdict(list)

for r in qs:
    actual = r.dyeing_process.max_temp
    prog_suhu = r.program.suhu_max
    prog_name = r.program.nama
    
    diff = actual - prog_suhu
    data[(prog_name, prog_suhu)].append(diff)

print("Program Name | Suhu Program | Avg Diff (°C) | StdDev (°C) | Total Batch")
print("--- | --- | --- | --- | ---")

for (prog_name, prog_suhu), diffs in sorted(data.items()):
    avg = sum(diffs) / len(diffs)
    std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    avg_str = f"+{avg:.2f}" if avg > 0 else f"{avg:.2f}"
    
    print(f"{prog_name} | {prog_suhu}°C | {avg_str} | {std:.2f} | {len(diffs)}")
