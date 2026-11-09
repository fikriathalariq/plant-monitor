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

machine = Machine.objects.filter(code='JR_03').first()

processes = DyeingProcess.objects.filter(
    machine=machine,
    start_time__gte='2026-03-01T00:00:00+07:00',
    max_temp__gte=125.0,
    max_temp__lte=150.0,
    is_valid_process=True,
    duration_effective__gte=30.0,
    real_heating_duration__isnull=False
).order_by('real_heating_duration')

for p in processes[:15]:
    h = p.real_heating_duration or 0
    s = p.steady_duration or 0
    c = p.cooling_duration or 0
    total_phase = h + s + c
    eff_dur = p.duration_effective or 0
    print(f"Batch: {p.batch_number}, Heat: {h}, Hold: {s}, Cool: {c}, Total: {total_phase}, Eff: {eff_dur}")
