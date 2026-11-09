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

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

machines = Machine.objects.all().order_by('code')

results = []

for machine in machines:
    processes = DyeingProcess.objects.filter(
        machine=machine,
        max_temp__gte=125.0,
        max_temp__lte=150.0,
        is_valid_process=True,
        start_time__gte=start_date,
        avg_steam_pressure__gt=3.8,
        real_heating_duration__isnull=False
    )
    
    raw_phases = []
    
    for p in processes:
        h = p.real_heating_duration or 0
        s = p.steady_duration or 0
        c = p.cooling_duration or 0
        total_phase = h + s + c
        if total_phase > 0:
            raw_phases.append(total_phase)
            
    if len(raw_phases) < 5:
        # Not enough data for meaningful IQR
        continue
        
    raw_phases_arr = np.array(raw_phases)
    
    q1 = np.percentile(raw_phases_arr, 25)
    q3 = np.percentile(raw_phases_arr, 75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    clean_phases = raw_phases_arr[(raw_phases_arr >= lower_bound) & (raw_phases_arr <= upper_bound)]
    
    outliers_removed = len(raw_phases_arr) - len(clean_phases)
    
    if len(clean_phases) > 0:
        mean_val = np.mean(clean_phases)
        median_val = np.median(clean_phases)
        min_val = np.min(clean_phases)
        max_val = np.max(clean_phases)
        std_val = np.std(clean_phases)
        
        results.append({
            'code': machine.code,
            'clean_count': len(clean_phases),
            'outliers': outliers_removed,
            'mean': mean_val,
            'median': median_val,
            'min': min_val,
            'max': max_val,
            'std': std_val
        })

print("| Mesin | Jml Data (Bersih) | Outliers Dibuang | Rata-rata (Menit) | Median | Min | Max | Std Dev |")
print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
for res in results:
    print(f"| **{res['code']}** | {res['clean_count']} | {res['outliers']} | **{res['mean']:.1f}** | {res['median']:.1f} | {res['min']:.1f} | {res['max']:.1f} | {res['std']:.1f} |")
