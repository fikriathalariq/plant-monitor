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
import matplotlib.pyplot as plt
from scipy.stats import norm

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
artifact_dir = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b"

import math

machines = Machine.objects.all().order_by('code')

# First, collect data for all machines
all_machine_data = []

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
        continue
        
    raw_phases_arr = np.array(raw_phases)
    q1 = np.percentile(raw_phases_arr, 25)
    q3 = np.percentile(raw_phases_arr, 75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    clean_data = raw_phases_arr[(raw_phases_arr >= lower_bound) & (raw_phases_arr <= upper_bound)]
    outliers = raw_phases_arr[(raw_phases_arr < lower_bound) | (raw_phases_arr > upper_bound)]
    
    if len(clean_data) > 0:
        all_machine_data.append({
            'code': machine.code,
            'clean_data': clean_data,
            'outliers': outliers
        })

num_machines = len(all_machine_data)
cols = 4
rows = math.ceil(num_machines / cols)

fig, axes = plt.subplots(rows, cols, figsize=(20, 4 * rows))
axes = axes.flatten()

for i, m_data in enumerate(all_machine_data):
    ax = axes[i]
    code = m_data['code']
    clean_data = m_data['clean_data']
    outliers = m_data['outliers']
    
    # Plot histogram of clean data
    ax.hist(clean_data, bins=15, density=True, alpha=0.6, color='dodgerblue', label='Inliers')
    
    # Fit normal distribution to clean data
    mu, std = norm.fit(clean_data)
    xmin, xmax = ax.get_xlim()
    if len(outliers) > 0:
        xmax = max(xmax, np.max(outliers) + 10)
        xmin = min(xmin, np.min(outliers) - 10)
        
    x = np.linspace(xmin, xmax, 100)
    if std > 0:
        p = norm.pdf(x, mu, std)
        ax.plot(x, p, 'k', linewidth=1.5, label=f'μ={mu:.0f}')
    
    # Add vertical line for mean
    ax.axvline(mu, color='green', linestyle='dashed', linewidth=1.5)
    
    # Plot outliers
    if len(outliers) > 0:
        ax.scatter(outliers, np.zeros_like(outliers), color='red', marker='x', s=50, zorder=5, label='Outliers')
        
    ax.set_title(f'{code}')
    ax.legend(loc='upper right', fontsize='small')
    ax.grid(True, linestyle='--', alpha=0.5)

# Hide any unused subplots
for j in range(i + 1, len(axes)):
    fig.delaxes(axes[j])

plt.tight_layout()
save_path = os.path.join(artifact_dir, "normal_distribution_all_iqr.png")
plt.savefig(save_path, dpi=120)
plt.close()
print(f"Plot saved to {save_path}")
