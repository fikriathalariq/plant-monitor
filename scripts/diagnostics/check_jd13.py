import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code__iexact='JD_13').first()
if not machine:
    machine = Machine.objects.filter(code__icontains='JD').first()
    print(f"JD_13 not found, found: {machine.code if machine else 'None'}")

if machine:
    print(f"Machine found: {machine.code}")
    count = DyeingProcess.objects.filter(machine=machine).count()
    print(f"Total processes: {count}")
    
    # Check max temp range
    p_high = DyeingProcess.objects.filter(machine=machine).order_by('-max_temp').first()
    p_low = DyeingProcess.objects.filter(machine=machine, max_temp__gt=0).order_by('max_temp').first()
    print(f"Max Temp Range: {p_low.max_temp if p_low else 'N/A'} to {p_high.max_temp if p_high else 'N/A'}")
