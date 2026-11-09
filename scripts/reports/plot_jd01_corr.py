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
import matplotlib.pyplot as plt
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code__iexact='JD_01').first()

start_date = datetime(2026, 6, 29, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

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
    
    # Filter anomalies/outliers if they exist, but generally include all
    if total_phase > 0 and p.avg_steam_pressure > 0:
        pressures.append(p.avg_steam_pressure)
        total_phases.append(total_phase)

plt.figure(figsize=(10, 6))
plt.scatter(pressures, total_phases, alpha=0.6, c='blue', edgecolors='w', s=60)
plt.title('Korelasi Total Fase vs Tekanan Steam (JD_01)\nData: 29 Juni 2026 - Sekarang')
plt.xlabel('Avg Steam Pressure (Bar)')
plt.ylabel('Total Fase (Menit)')
plt.grid(True, linestyle='--', alpha=0.7)

# Add trendline
if len(pressures) > 1:
    z = np.polyfit(pressures, total_phases, 1)
    p = np.poly1d(z)
    plt.plot(pressures, p(pressures), "r--", alpha=0.8, linewidth=2, label='Trendline')
    plt.legend()

save_path = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b\jd01_corr_29june.png"
plt.tight_layout()
plt.savefig(save_path, dpi=150)
print(f"Plot saved to {save_path}")
print(f"Total data points: {len(pressures)}")
