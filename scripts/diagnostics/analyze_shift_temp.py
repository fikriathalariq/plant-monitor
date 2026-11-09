import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import re
from datetime import date
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import ProductionPlanBatch, DyeingProcess

START_DATE = date(2026, 8, 11)
END_DATE = date(2026, 8, 21)

batches = ProductionPlanBatch.objects.filter(
    plan__shift_date__gte=START_DATE,
    plan__shift_date__lte=END_DATE
).select_related('plan', 'machine')

# Data structure: data[date][machine][shift] = count
data = defaultdict(lambda: defaultdict(lambda: {1: 0, 2: 0, 3: 0}))

for b in batches:
    # Get max temp
    m = re.search(r'Batch #(\d+)', b.label)
    if not m:
        continue
    proc = DyeingProcess.objects.filter(machine=b.machine, batch_number=m.group(1)).first()
    if not proc or not proc.max_temp or proc.max_temp <= 115:
        continue
        
    offset = b.start_offset_minutes
    # Determine shift
    if 0 <= offset < 480:
        shift = 1
    elif 480 <= offset < 960:
        shift = 2
    else:
        shift = 3
        
    shift_date = b.plan.shift_date
    mc = b.machine.code
    
    data[shift_date][mc][shift] += 1

# Generate Markdown
md = []
dates = sorted(data.keys())

for d in dates:
    md.append(f"### Tanggal Produksi: {d.strftime('%d %B %Y')}")
    md.append("| Mesin | Shift 1 (06:00 - 14:00) | Shift 2 (14:00 - 22:00) | Shift 3 (22:00 - 06:00) | Total |")
    md.append("|---|:---:|:---:|:---:|:---:|")
    
    machines = sorted(data[d].keys())
    total_s1 = 0
    total_s2 = 0
    total_s3 = 0
    total_all = 0
    
    for mc in machines:
        s1 = data[d][mc][1]
        s2 = data[d][mc][2]
        s3 = data[d][mc][3]
        tot = s1 + s2 + s3
        
        total_s1 += s1
        total_s2 += s2
        total_s3 += s3
        total_all += tot
        
        # Only show machines that have at least 1 batch > 115C this day
        if tot > 0:
            md.append(f"| **{mc}** | {s1 if s1 else '-'} | {s2 if s2 else '-'} | {s3 if s3 else '-'} | **{tot}** |")
            
    md.append(f"| **TOTAL** | **{total_s1}** | **{total_s2}** | **{total_s3}** | **{total_all}** |")
    md.append("\n---\n")

report_content = "\n".join(md)
with open('shift_analysis.md', 'w') as f:
    f.write(report_content)
    
print("Report generated at shift_analysis.md")
