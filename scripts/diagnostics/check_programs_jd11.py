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

machine = Machine.objects.filter(code__iexact='JD_11').first()

if not machine:
    print("Machine JD_11 not found!")
    exit(1)

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False
).select_related('identity', 'identity__program')

sebelum_programs = set()
mulai_programs = set()

cutoff_date = datetime.strptime('2026-03-03 00:00:00', '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.timezone('Asia/Jakarta'))

for p in processes:
    if not p.start_time: continue
    
    prog_name = None
    try:
        if hasattr(p, 'identity') and p.identity and p.identity.program:
            prog_name = p.identity.program.nama
    except:
        pass
        
    if not prog_name:
        prog_name = "UNLINKED/NO_PROGRAM"
        
    if p.start_time < cutoff_date:
        sebelum_programs.add(prog_name)
    else:
        mulai_programs.add(prog_name)

print("Program Sebelum 3 Maret 2026:")
for p in sorted(sebelum_programs):
    print("-", p)

print("\nProgram Mulai 3 Maret 2026:")
for p in sorted(mulai_programs):
    print("-", p)

print("\nProgram yang ada di KEDUANYA:")
irisan = sebelum_programs.intersection(mulai_programs)
for p in sorted(irisan):
    print("-", p)
