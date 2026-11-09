import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
machine = Machine.objects.filter(code__iexact='JD_10').first()

processes = DyeingProcess.objects.filter(
    machine=machine,
    is_valid_process=True,
    start_time__gte=start_date
).select_related('identity', 'identity__program')

programs_data = {}

for p in processes:
    prog_name = "N/A"
    try:
        if p.identity and p.identity.program:
            prog_name = p.identity.program.nama or "N/A"
    except:
        pass
        
    if prog_name not in programs_data:
        programs_data[prog_name] = {'total': 0, 'healthy_steam': 0}
        
    programs_data[prog_name]['total'] += 1
    
    if p.avg_steam_pressure and p.avg_steam_pressure > 3.8:
        programs_data[prog_name]['healthy_steam'] += 1

# Sort by total processes descending
sorted_programs = sorted(programs_data.items(), key=lambda x: x[1]['total'], reverse=True)

print("| Program | Total Proses | Total Proses (Steam > 3.8 Bar) | Persentase Steam Sehat |")
print("| :--- | :---: | :---: | :---: |")
for name, counts in sorted_programs:
    pct = (counts['healthy_steam'] / counts['total'] * 100) if counts['total'] > 0 else 0
    print(f"| {name} | {counts['total']} | {counts['healthy_steam']} | {pct:.1f}% |")
