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

from monitoring.models import DyeingProcess

p = DyeingProcess.objects.filter(machine__code='JR_03', batch_number='342').first()
if p:
    print(f"Heat (real): {p.real_heating_duration}")
    print(f"Hold: {p.steady_duration}")
    print(f"Cool: {p.cooling_duration}")
    print(f"duration_effective: {p.duration_effective}")
