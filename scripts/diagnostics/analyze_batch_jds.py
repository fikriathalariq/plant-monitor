import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import pytz
from datetime import datetime
import numpy as np
from scipy.stats import gaussian_kde

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine
from django.db.models import Avg

start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
machines_to_check = ['JD_01', 'JD_03', 'JD_04', 'JD_08', 'JD_09']

def get_kde_mode(data):
    if not data: return 0
    if len(data) == 1: return data[0]
    try:
        kde = gaussian_kde(data)
        x_vals = np.linspace(min(data), max(data), 100)
        y_vals = kde.evaluate(x_vals)
        mode_val = x_vals[np.argmax(y_vals)]
        return mode_val
    except:
        return np.mean(data)

def get_baseline(data):
    if not data: return 0
    mode_val = get_kde_mode(data)
    mean_val = np.mean(data)
    if mode_val > mean_val:
        filtered = [x for x in data if mode_val - 15 <= x <= mode_val + 15]
        if filtered: return np.mean(filtered)
        return mode_val
    return mean_val

with open(r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b\batch_analysis_results.md", "w") as f:
    f.write("# Laporan Batch JD_01, JD_03, JD_04, JD_08, JD_09\n")
    for mc_code in machines_to_check:
        machine = Machine.objects.filter(code__iexact=mc_code).first()
        if not machine:
            continue
            
        f.write(f"\n## Mesin {mc_code}\n\n")
        
        processes = DyeingProcess.objects.filter(
            machine=machine,
            start_time__gte=start_date
        )
        
        prog_counts = {}
        for p in processes:
            has_identity = hasattr(p, 'identity')
            prog_name = p.identity.program.nama if has_identity and p.identity.program else "N/A"
            suhu = p.identity.program.suhu_max if has_identity and p.identity.program else 0
            if prog_name not in prog_counts:
                prog_counts[prog_name] = {'total': 0, 'sehat': 0, 'suhu': suhu}
                
            prog_counts[prog_name]['total'] += 1
            
            if p.avg_steam_pressure and p.avg_steam_pressure > 3.8:
                prog_counts[prog_name]['sehat'] += 1
                    
        f.write("### Tabel Populasi Program\n")
        f.write("| Program | Suhu Max | Total Proses | Total (Steam > 3.8) | Persentase |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")
        sorted_progs = sorted(prog_counts.items(), key=lambda x: x[1]['total'], reverse=True)
        for prog, data in sorted_progs:
            pct = (data['sehat'] / data['total'] * 100) if data['total'] > 0 else 0
            suhu_str = str(data['suhu']) if prog != "N/A" else "-"
            f.write(f"| {prog} | {suhu_str} | {data['total']} | {data['sehat']} | {pct:.1f}% |\n")

        f.write("\n### Analisis Durasi Aktual vs Ideal (Suhu >= 120°C & Steam > 3.8 Bar)\n")
        f.write("| Program | N | Heat Aktual / Ideal | Hold Aktual / Ideal | Cool Aktual / Ideal | **Total Aktual / Ideal** | Selisih Total |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        
        for prog, data in sorted_progs:
            if prog == "N/A" or data['suhu'] < 120 or data['sehat'] == 0:
                continue
                
            sample_p = DyeingProcess.objects.filter(machine=machine, start_time__gte=start_date, identity__program__nama=prog).first()
            if not sample_p or not sample_p.identity.program: continue
            
            ideal_heat = sample_p.identity.program.durasi_heating_ideal or 0
            ideal_hold = sample_p.identity.program.durasi_keeping_ideal or 0
            ideal_cool = sample_p.identity.program.durasi_cooling_ideal or 0
            ideal_total = ideal_heat + ideal_hold + ideal_cool
            
            healthy_processes = []
            for p in DyeingProcess.objects.filter(machine=machine, start_time__gte=start_date, identity__program__nama=prog):
                if p.avg_steam_pressure and p.avg_steam_pressure > 3.8:
                    healthy_processes.append(p)
                        
            heat_times = [p.real_heating_duration for p in healthy_processes if p.real_heating_duration and p.real_heating_duration > 0]
            hold_times = [p.steady_duration for p in healthy_processes if p.steady_duration and p.steady_duration > 0]
            cool_times = [p.cooling_duration for p in healthy_processes if p.cooling_duration and p.cooling_duration > 0]
            
            if not heat_times: continue
            
            base_heat = get_baseline(heat_times)
            base_hold = get_baseline(hold_times)
            base_cool = get_baseline(cool_times)
            base_total = base_heat + base_hold + base_cool
            
            diff = base_total - ideal_total
            sign = "+" if diff > 0 else ""
            
            f.write(f"| **{prog}** | {len(healthy_processes)} | {base_heat:.1f} / {ideal_heat:.1f} | {base_hold:.1f} / {ideal_hold:.1f} | {base_cool:.1f} / {ideal_cool:.1f} | **{base_total:.1f}** / {ideal_total:.1f} | {sign}{diff:.1f} Menit |\n")
        
        f.write("\n---\n")

print("Done generating report to batch_analysis_results.md")
