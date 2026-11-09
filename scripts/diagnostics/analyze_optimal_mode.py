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
from scipy.stats import gaussian_kde

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
    
    raw_data = []
    for p in processes:
        h = p.real_heating_duration or 0
        s = p.steady_duration or 0
        c = p.cooling_duration or 0
        total_phase = h + s + c
        if total_phase > 0:
            raw_data.append((total_phase, h, s, c))
            
    if len(raw_data) < 5:
        continue
        
    # Extract total phases for filtering
    raw_phases_arr = np.array([x[0] for x in raw_data])
    
    # IQR Filtering
    q1 = np.percentile(raw_phases_arr, 25)
    q3 = np.percentile(raw_phases_arr, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # Keep only data within bounds
    clean_indices = np.where((raw_phases_arr >= lower_bound) & (raw_phases_arr <= upper_bound))[0]
    clean_data_full = [raw_data[i] for i in clean_indices]
    clean_phases = np.array([x[0] for x in clean_data_full])
    
    if len(clean_phases) > 1:
        mean_val = np.mean(clean_phases)
        std_val = np.std(clean_phases)
        
        # Calculate Mode using Kernel Density Estimation
        try:
            density = gaussian_kde(clean_phases)
            x_vals = np.linspace(min(clean_phases), max(clean_phases), 1000)
            y_vals = density(x_vals)
            mode_approx = x_vals[np.argmax(y_vals)]
        except:
            mode_approx = mean_val
            
        margin = std_val / 2 if std_val > 0 else 5
        
        if mode_approx > mean_val:
            # Mode > Mean: Use data in range around mode
            valid_subset = [x for x in clean_data_full if mode_approx - margin <= x[0] <= mode_approx + margin]
            decision = "Mode Range"
        else:
            # Mean >= Mode: Use all clean data
            valid_subset = clean_data_full
            decision = "Mean"
            
        if len(valid_subset) == 0:
            valid_subset = clean_data_full # Fallback
            
        final_total = np.mean([x[0] for x in valid_subset])
        final_h = np.mean([x[1] for x in valid_subset])
        final_s = np.mean([x[2] for x in valid_subset])
        final_c = np.mean([x[3] for x in valid_subset])
            
        results.append({
            'code': machine.code,
            'clean_count': len(clean_phases),
            'decision': decision,
            'final_h': final_h,
            'final_s': final_s,
            'final_c': final_c,
            'final_total': final_total
        })

print("| Mesin | Jml Data Bersih | Keputusan | Heat (Menit) | Hold (Menit) | Cool (Menit) | **Total Final Baseline** |")
print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
for res in results:
    print(f"| **{res['code']}** | {res['clean_count']} | {res['decision']} | {res['final_h']:.1f} | {res['final_s']:.1f} | {res['final_c']:.1f} | **{res['final_total']:.1f}** |")

