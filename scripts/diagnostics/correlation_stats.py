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
import numpy as np
from scipy.stats import linregress

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

machines = Machine.objects.all().order_by('code')

print("| Mesin | Jumlah Batch | r (Korelasi) | r^2 (R-Squared) | Persamaan Regresi (y = mx + c) |")
print("| :--- | :---: | :---: | :---: | :--- |")

for machine in machines:
    processes = DyeingProcess.objects.filter(
        machine=machine,
        max_temp__gte=125.0,
        max_temp__lte=150.0,
        is_valid_process=True,
        start_time__gte=start_date,
        avg_steam_pressure__isnull=False,
        real_heating_duration__isnull=False
    )

    pressures = []
    total_phases = []

    for p in processes:
        h = p.real_heating_duration or 0
        s = p.steady_duration or 0
        c = p.cooling_duration or 0
        total_phase = h + s + c
        
        if total_phase > 0 and p.avg_steam_pressure > 0:
            pressures.append(float(p.avg_steam_pressure))
            total_phases.append(float(total_phase))

    if len(pressures) > 1:
        slope, intercept, r_value, p_value, std_err = linregress(pressures, total_phases)
        r_squared = r_value ** 2
        eq_str = f"y = {slope:.2f}x {'+' if intercept >= 0 else '-'} {abs(intercept):.2f}"
        print(f"| **{machine.code}** | {len(pressures)} | {r_value:.4f} | {r_squared:.4f} | {eq_str} |")
    else:
        print(f"| **{machine.code}** | {len(pressures)} | - | - | Tidak cukup data |")
