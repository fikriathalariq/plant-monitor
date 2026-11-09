import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from django.db.models import Count, Q

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code='JR_03').first()

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False,
    identity__program__isnull=False
).select_related('identity', 'identity__program')

program_stats = {}

for p in processes:
    prog_name = p.identity.program.nama if p.identity and p.identity.program else "Unknown"
    
    if prog_name not in program_stats:
        program_stats[prog_name] = {'before': 0, 'after': 0}
        
    if p.start_time.strftime('%Y-%m') < '2026-03':
        program_stats[prog_name]['before'] += 1
    else:
        program_stats[prog_name]['after'] += 1

print("| Program | Count Sebelum Maret 2026 | Count Mulai Maret 2026 | Status |")
print("| :--- | :--- | :--- | :--- |")

for prog, stats in sorted(program_stats.items()):
    b = stats['before']
    a = stats['after']
    
    if b > 0 and a > 0:
        status = "**Bisa Dibandingkan**"
    elif b > 0:
        status = "Hanya di Sebelum Maret"
    else:
        status = "Hanya di Mulai Maret"
        
    print(f"| {prog} | {b} | {a} | {status} |")
