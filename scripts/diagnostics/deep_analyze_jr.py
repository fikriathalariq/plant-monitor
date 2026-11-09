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
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

artifact_dir = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b"
start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
target_machines = ['JR_02', 'JR_03', 'JR_07']
machines = Machine.objects.filter(code__in=target_machines).order_by('code')

def clean_iqr(data):
    if not data:
        return []
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    return [x for x in data if lower_bound <= x <= upper_bound]

def plot_spc(ax, data, ideal_target, title):
    if not data:
        return
    cleaned_data = clean_iqr(data)
    if len(cleaned_data) < 2:
        return
    try:
        ax.hist(cleaned_data, bins=min(15, len(set(cleaned_data)) or 1), density=True, alpha=0.6, color='skyblue')
        if len(set(cleaned_data)) > 1:
            kde = stats.gaussian_kde(cleaned_data)
            x_range = np.linspace(min(cleaned_data), max(cleaned_data), 100)
            ax.plot(x_range, kde(x_range), color='blue', lw=2)
    except Exception as e:
        print(f"Error plotting {title}: {e}")
        return
    
    mean = np.mean(cleaned_data)
    median = np.median(cleaned_data)
    std = np.std(cleaned_data)
    skew = stats.skew(cleaned_data)
    
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    
    ax.axvline(ideal_target, color='red', linestyle='--', linewidth=2, label=f'Target ({ideal_target:.1f})')
    ax.axvline(mean, color='green', linestyle='-', linewidth=2, label=f'Mean ({mean:.1f})')
    ax.axvline(median, color='orange', linestyle='-.', linewidth=2, label=f'Median ({median:.1f})')
    ax.axvspan(lcl, ucl, color='yellow', alpha=0.2, label='SPC limits (±3σ)')
    ax.set_title(title)
    ax.legend(loc='upper right', fontsize='small')
    textstr = '\n'.join((f'n={len(cleaned_data)}', f'Std={std:.1f}', f'Skew={skew:.2f}'))
    props = dict(boxstyle='round', facecolor='white', alpha=0.5)
    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=10, verticalalignment='top', bbox=props)

with open(os.path.join(artifact_dir, "deep_analysis_jr_critical_formal.md"), "w", encoding='utf-8') as f:
    f.write("# Analisis Mendalam: JR_02, JR_03, dan JR_07\n\n")
    f.write("*Menganalisis seluruh program ber-suhu 120-130°C yang memiliki minimal 10 proses (N >= 10).*\n\n")
    
    f.write("## Tabel Statistik Multi-Program\n\n")
    f.write("| Mesin | Program | N | Heat Mean / Ideal | Total Mean / Ideal | Skew_H | Skew_T | Std_H | Std_T | Diagnosis Singkat |\n")
    f.write("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|\n")

    images_md = []
    
    for mc in machines:
        processes = DyeingProcess.objects.filter(
            machine=mc,
            start_time__gte=start_date,
            identity__program__suhu_max__gte=120,
            identity__program__suhu_max__lte=130,
            avg_steam_pressure__gt=3.8
        ).select_related('identity', 'identity__program')
        
        valid_processes = []
        for p in processes:
            h = p.real_heating_duration or 0
            s = p.steady_duration or 0
            c = p.cooling_duration or 0
            total_actual = h + s + c
            if total_actual < 40:
                continue
            actual_max = p.max_temp or 0
            prog = p.identity.program
            if abs(actual_max - prog.suhu_max) > 15:
                continue
            valid_processes.append(p)
            
        program_counts = {}
        for p in valid_processes:
            prog_name = p.identity.program.nama
            if prog_name not in program_counts:
                program_counts[prog_name] = {'count': 0, 'processes': [], 'ideal': {}}
            program_counts[prog_name]['count'] += 1
            program_counts[prog_name]['processes'].append(p)
            if not program_counts[prog_name]['ideal']:
                program_counts[prog_name]['ideal'] = {
                    'h': p.identity.program.durasi_heating_ideal or 0,
                    's': p.identity.program.durasi_keeping_ideal or 0,
                    'c': p.identity.program.durasi_cooling_ideal or 0,
                }
                
        for prog_name, data in sorted(program_counts.items(), key=lambda x: x[1]['count'], reverse=True):
            if data['count'] < 10:
                continue
                
            print(f"Processing {mc.code} - {prog_name} (N={data['count']})")
            h_data = []
            s_data = []
            c_data = []
            t_data = []
            for p in data['processes']:
                h = p.real_heating_duration or 0
                s = p.steady_duration or 0
                c = p.cooling_duration or 0
                h_data.append(h)
                s_data.append(s)
                c_data.append(c)
                t_data.append(h + s + c)
                
            ideal = data['ideal']
            ideal_total = ideal['h'] + ideal['s'] + ideal['c']
            
            h_cl = clean_iqr(h_data)
            t_cl = clean_iqr(t_data)
            
            mean_h = np.mean(h_cl)
            mean_t = np.mean(t_cl)
            std_h = np.std(h_cl)
            std_t = np.std(t_cl)
            skew_h = stats.skew(h_cl) if len(set(h_cl)) > 2 else 0
            skew_t = stats.skew(t_cl) if len(set(t_cl)) > 2 else 0
            
            diagnosis = "Konsisten"
            if std_h > 15 or std_t > 20:
                diagnosis = "Variansi Ekstrem (Tidak terkendali)"
            elif skew_h > 1.0 or skew_t > 1.0:
                diagnosis = "Skewness Tinggi (Outlier sistematis)"
            elif skew_h > 0.5 or skew_t > 0.5:
                diagnosis = "Variasi Menengah"
            
            f.write(f"| **{mc.code}** | {prog_name} | {len(data['processes'])} | {mean_h:.1f} / {ideal['h']:.0f} | {mean_t:.1f} / {ideal_total:.0f} | {skew_h:.2f} | {skew_t:.2f} | {std_h:.1f} | {std_t:.1f} | {diagnosis} |\n")
            
            # Create plot
            fig, axes = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle(f"Analisis SPC Mendalam {mc.code} - Program {prog_name}", fontsize=16)
            plot_spc(axes[0, 0], h_data, ideal['h'], "Distribusi Waktu Heating")
            plot_spc(axes[0, 1], s_data, ideal['s'], "Distribusi Waktu Hold")
            plot_spc(axes[1, 0], c_data, ideal['c'], "Distribusi Waktu Cooling")
            plot_spc(axes[1, 1], t_data, ideal_total, "Distribusi Waktu Total")
            
            plt.tight_layout()
            img_name = f"spc_deep_{mc.code}_{prog_name.replace(' ', '_').replace('.', '')}.png"
            img_path = os.path.join(artifact_dir, img_name)
            plt.savefig(img_path, dpi=100)
            plt.close(fig)
            
            images_md.append(f"### {mc.code} - Program {prog_name}\n![SPC {mc.code} {prog_name}](file:///{img_path.replace(chr(92), '/')})\n")
            
    f.write("\n---\n\n## Visualisasi Distribusi\n\n")
    for img in images_md:
        f.write(img)

print("Deep SPC generation completed.")
