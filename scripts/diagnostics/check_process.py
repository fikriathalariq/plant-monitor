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
from django.core.exceptions import ObjectDoesNotExist

try:
    p = DyeingProcess.objects.get(id=2114032)
except ObjectDoesNotExist:
    print("Process 2114032 not found. Looking for a recent process on JR_03.")
    p = DyeingProcess.objects.filter(machine__code='JR_03').order_by('-id').first()

if p:
    print(f"ID: {p.id}, Batch: {p.batch_number}, Machine: {p.machine.code}")
    print(f"heating_duration (DB): {p.heating_duration}")
    print(f"real_heating_duration (DB): {p.real_heating_duration}")
    print(f"steady_duration (DB): {p.steady_duration}")
    print(f"cooling_duration (DB): {p.cooling_duration}")
    print(f"duration_effective (DB): {p.duration_effective}")
    print(f"start_time: {p.start_time}")
    print(f"end_time: {p.end_time}")
    
    # Calculate like api_report
    heat_dur  = p.real_heating_duration or 0
    hold_dur  = p.steady_duration or 0
    cool_dur  = p.cooling_duration or 0
    total_dur = heat_dur + hold_dur + cool_dur
    
    print(f"\nAPI Report output would be:")
    print(f"heat_actual: {round(heat_dur, 0)}")
    print(f"hold_actual: {round(hold_dur, 0)}")
    print(f"cool_actual: {round(cool_dur, 0)}")
    print(f"duration_effective (KPI): {round(p.duration_effective, 1) if p.duration_effective else None}")
else:
    print("No process found")
