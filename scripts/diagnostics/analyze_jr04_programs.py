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
from scipy.stats import linregress

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
machine = Machine.objects.filter(code__iexact='JD_11').first()

programs_to_check = ['P. 009', 'P. 025', 'P. 013', 'P. 019', 'P. 008', 'P. 015']

artifact_dir = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b"

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
axes = axes.flatten()

results = []

for idx, prog_name in enumerate(programs_to_check):
    processes = DyeingProcess.objects.filter(
        machine=machine,
        is_valid_process=True,
        start_time__gte=start_date,
        identity__program__nama__iexact=prog_name,
        real_heating_duration__isnull=False,
        avg_steam_pressure__gt=3.8
    ).select_related('identity', 'identity__program')
    
    pressures = []
    total_phases = []
    
    h_actuals = []
    s_actuals = []
    c_actuals = []
    
    h_ideal = 0
    s_ideal = 0
    c_ideal = 0
    
    # Grab ideal from the first available process
    if processes.exists():
        prog = processes.first().identity.program
        h_ideal = prog.durasi_heating_ideal or 0
        s_ideal = prog.durasi_keeping_ideal or 0
        c_ideal = prog.durasi_cooling_ideal or 0
        
    for p in processes:
        h = p.real_heating_duration or 0
        s = p.steady_duration or 0
        c = p.cooling_duration or 0
        total_phase = h + s + c
        press = p.avg_steam_pressure
        
        if total_phase > 0 and press > 0:
            pressures.append(press)
            total_phases.append(total_phase)
            h_actuals.append(h)
            s_actuals.append(s)
            c_actuals.append(c)
            
    # Scatter Plot
    ax = axes[idx]
    if len(pressures) > 1:
        x = np.array(pressures)
        y = np.array(total_phases)
        ax.scatter(x, y, color='blue', alpha=0.6)
        
        # Regression
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        x_line = np.linspace(min(x), max(x), 100)
        y_line = slope * x_line + intercept
        ax.plot(x_line, y_line, color='red', linewidth=2)
        
        title_str = f"{prog_name} (n={len(x)})\n"
        title_str += f"r = {r_value:.2f} | R² = {r_value**2:.2f} | y = {slope:.1f}x + {intercept:.1f}"
        ax.set_title(title_str)
        
        # Means
        mean_h = np.mean(h_actuals)
        mean_s = np.mean(s_actuals)
        mean_c = np.mean(c_actuals)
        mean_tot = np.mean(total_phases)
        
        results.append({
            'program': prog_name,
            'n': len(x),
            'h_act': mean_h, 's_act': mean_s, 'c_act': mean_c, 'tot_act': mean_tot,
            'h_id': h_ideal, 's_id': s_ideal, 'c_id': c_ideal, 'tot_id': h_ideal + s_ideal + c_ideal
        })
    else:
        ax.set_title(f"{prog_name} (Data Tidak Cukup)")
        
    ax.set_xlabel('Avg Steam Pressure (Bar)')
    ax.set_ylabel('Total Fase (Menit)')
    ax.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
save_path = os.path.join(artifact_dir, "jd11_programs_corr.png")
plt.savefig(save_path, dpi=120)
plt.close()

# Print Table
print("### Analisis Durasi Aktual vs Ideal per Program (JD_11) [STEAM SEHAT > 3.8]")
print("| Program | N | Heat Aktual / Ideal | Hold Aktual / Ideal | Cool Aktual / Ideal | **Total Aktual / Ideal** | Selisih Total |")
print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

for r in results:
    heat_str = f"{r['h_act']:.1f} / {r['h_id']}"
    hold_str = f"{r['s_act']:.1f} / {r['s_id']}"
    cool_str = f"{r['c_act']:.1f} / {r['c_id']}"
    tot_str = f"**{r['tot_act']:.1f}** / {r['tot_id']}"
    
    selisih = r['tot_act'] - r['tot_id']
    selisih_str = f"+{selisih:.1f}" if selisih > 0 else f"{selisih:.1f}"
    
    print(f"| **{r['program']}** | {r['n']} | {heat_str} | {hold_str} | {cool_str} | {tot_str} | {selisih_str} Menit |")
