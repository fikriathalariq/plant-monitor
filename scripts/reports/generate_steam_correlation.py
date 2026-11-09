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
import base64
from datetime import datetime
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

artifact_dir = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b"
start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
jd03_start = datetime(2026, 6, 28, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

lumayan = ['JD_03', 'JD_09', 'JD_11', 'JD_13', 'JD_14', 'JD_15', 'JD_16', 'JR_08', 'JR_13']
machines_qs = Machine.objects.filter(code__in=lumayan).order_by('code')

def get_base64_img(img_path):
    with open(img_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

results = []

print("Generating correlation data and plots...")

for mc in machines_qs:
    mc_start = jd03_start if mc.code == 'JD_03' else start_date
    processes = DyeingProcess.objects.filter(
        machine=mc, start_time__gte=mc_start,
        identity__program__suhu_max__gte=120, identity__program__suhu_max__lte=130,
        avg_steam_pressure__isnull=False
    ).select_related('identity', 'identity__program')
    
    valid_processes = []
    for p in processes:
        tot_dur = (p.real_heating_duration or 0) + (p.steady_duration or 0) + (p.cooling_duration or 0)
        if tot_dur < 40: continue
        if p.max_temp and p.identity.program and abs(p.max_temp - p.identity.program.suhu_max) <= 15:
            valid_processes.append(p)
            
    program_counts = {}
    for p in valid_processes:
        nm = p.identity.program.nama
        if nm not in program_counts:
            ideal_hs = (p.identity.program.durasi_heating_ideal or 0) + (p.identity.program.durasi_keeping_ideal or 0)
            program_counts[nm] = {'count': 0, 'data': [], 'ideal': ideal_hs}
        
        hs_dur = (p.real_heating_duration or 0) + (p.steady_duration or 0)
        program_counts[nm]['count'] += 1
        program_counts[nm]['data'].append({'steam': p.avg_steam_pressure, 'dur': hs_dur})
            
    for prog_name, data_dict in sorted(program_counts.items(), key=lambda x: x[1]['count'], reverse=True):
        if data_dict['count'] < 15: continue
        
        # Extract X and Y
        raw_X = [d['steam'] for d in data_dict['data']]
        raw_Y = [d['dur'] for d in data_dict['data']]
        
        # Clean IQR based on Y to avoid extreme duration anomalies messing up regression
        q1 = np.percentile(raw_Y, 25)
        q3 = np.percentile(raw_Y, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        X, Y = [], []
        for x, y in zip(raw_X, raw_Y):
            if lower_bound <= y <= upper_bound:
                X.append(x)
                Y.append(y)
                
        if len(X) < 10: continue
        
        # Statistics
        slope, intercept, r_value, p_value, std_err = stats.linregress(X, Y)
        r_sq = r_value**2
        
        # Plotting
        fig, ax = plt.subplots(figsize=(9, 5))
        
        # Color mapping: Red if <= 3.8, Blue if > 3.8
        colors = ['#d9534f' if x <= 3.8 else '#5bc0de' for x in X]
        ax.scatter(X, Y, c=colors, alpha=0.7, edgecolors='k', linewidth=0.5)
        
        # Regression Line
        x_vals = np.array([min(X), max(X)])
        y_vals = intercept + slope * x_vals
        ax.plot(x_vals, y_vals, '--', color='#333333', linewidth=2, label=f'Trendline (Slope: {slope:.1f})')
        
        # Reference lines
        ax.axvline(3.8, color='orange', linestyle=':', linewidth=2, label='Batas Sehat Steam (3.8 bar)')
        ax.axhline(data_dict['ideal'], color='green', linestyle='-.', linewidth=2, label=f"Ideal H+Hold ({data_dict['ideal']}m)")
        
        ax.set_title(f"Korelasi Steam vs Durasi (Heat+Hold) - {mc.code} ({prog_name})", fontsize=14, fontweight='bold')
        ax.set_xlabel("Average Steam Pressure (barg)", fontsize=12)
        ax.set_ylabel("Heating + Hold Duration (menit)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.5)
        
        # Text box for stats
        textstr = f"N = {len(X)}\nPearson r = {r_value:.2f}\nR² = {r_sq:.2f}\np-value = {p_value:.3f}"
        props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='#ccc')
        ax.text(0.95, 0.95, textstr, transform=ax.transAxes, fontsize=11,
                verticalalignment='top', horizontalalignment='right', bbox=props)
        
        ax.legend(loc='lower left')
        plt.tight_layout()
        
        img_name = f"steam_corr_{mc.code}_{prog_name.replace(' ', '_').replace('.', '')}.png"
        img_path = os.path.join(artifact_dir, img_name)
        plt.savefig(img_path, dpi=120)
        plt.close(fig)
        
        results.append({
            'mc': mc.code,
            'prog': prog_name,
            'n': len(X),
            'r': r_value,
            'r2': r_sq,
            'p': p_value,
            'slope': slope,
            'b64': get_base64_img(img_path)
        })

print("Generating HTML report...")

html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Korelasi Steam vs Durasi</title>
    <style>
        @page { size: A4; margin: 10mm; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #fff; color: #333; margin: 0; padding: 0; }
        .page { width: 190mm; min-height: 277mm; padding: 0; margin: 0 auto; background: white; page-break-after: always; box-sizing: border-box; }
        .page:last-child { page-break-after: avoid; }
        
        /* Cover & Summary Page Styling */
        .cover-page { padding: 10mm; }
        .cover-title { font-size: 28px; font-weight: bold; margin-bottom: 10px; text-align: center; }
        .cover-subtitle { font-size: 18px; color: #666; margin-bottom: 20px; text-align: center; }
        
        .note-box { background-color: #fdf8e4; border-left: 5px solid #f0ad4e; padding: 10px 15px; margin-bottom: 20px; font-size: 13px; line-height: 1.5; }
        
        table { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
        th { background-color: #f4f4f4; font-weight: bold; text-align: center; }
        .text-center { text-align: center; }
        .text-right { text-align: right; }
        
        /* Inner Pages Styling */
        .header { display: flex; justify-content: space-between; border-bottom: 2px solid #ccc; padding-bottom: 5px; margin-bottom: 10px; font-size: 12px; color: #777; }
        .item-container { margin-bottom: 8mm; width: 100%; text-align: center; }
        img { width: 100%; height: auto; max-height: 120mm; object-fit: contain; }
    </style>
</head>
<body>
"""

# Cover Page / Summary Table
html_content += f"""
<div class="page cover-page">
    <div class="cover-title">Laporan Korelasi Steam Pressure vs Durasi Total</div>
    <div class="cover-subtitle">Grup Mesin JD_PRC & JR_PRC (Kluster Normal/Optimal)</div>
    
    <div class="note-box">
        <strong>Catatan Interpretasi Statistik:</strong><br>
        <ul>
            <li><strong>Pearson r negatif (misal -0.5):</strong> Artinya terdapat korelasi terbalik &mdash; semakin <em>rendah</em> steam pressure, semakin <em>tinggi/lama</em> durasi proses.</li>
            <li><strong>Slope negatif (misal -25.0):</strong> Estimasi bahwa setiap penurunan 1 bar steam pressure, durasi bertambah 25 menit.</li>
            <li><strong>Titik Merah vs Biru:</strong> Merah menandakan proses berjalan pada tekanan uap di bawah batas sehat (&le; 3.8 bar). Biru adalah proses sehat (&gt; 3.8 bar).</li>
            <li><strong>Korelasi Lemah (r mendekati 0 / p-value &ge; 0.05):</strong> Bukan berarti steam tidak penting, melainkan rentang suplai steam pada data tersebut sudah cukup stabil/sempit sehingga efek fluktuasinya tidak signifikan mendominasi variasi durasi.</li>
        </ul>
    </div>
    
    <h3 style="font-size: 16px; margin-bottom: 10px;">Ringkasan Statistik (Diurutkan dari korelasi terkuat)</h3>
    <table>
        <thead>
            <tr>
                <th>Mesin</th>
                <th>Program</th>
                <th>N</th>
                <th>Pearson r</th>
                <th>R&sup2;</th>
                <th>Slope (mnt/bar)</th>
                <th>p-value</th>
                <th>Signifikansi</th>
            </tr>
        </thead>
        <tbody>
"""

# Sort results by correlation strength (r value ascending, since negative correlation is expected)
sorted_results = sorted(results, key=lambda x: x['r'])

for res in sorted_results:
    sig = "Kuat" if res['p'] < 0.05 and res['r'] <= -0.3 else ("Signifikan" if res['p'] < 0.05 else "Lemah/Tidak Signifikan")
    color = "#d9534f" if sig == "Kuat" else ("#5cb85c" if sig == "Signifikan" else "#777")
    
    html_content += f"""
        <tr>
            <td class="text-center"><strong>{res['mc']}</strong></td>
            <td class="text-center">{res['prog']}</td>
            <td class="text-center">{res['n']}</td>
            <td class="text-center">{res['r']:.2f}</td>
            <td class="text-center">{res['r2']:.2f}</td>
            <td class="text-center">{res['slope']:.1f}</td>
            <td class="text-center">{res['p']:.3f}</td>
            <td class="text-center" style="color: {color}; font-weight: 500;">{sig}</td>
        </tr>
    """

html_content += """
        </tbody>
    </table>
</div>
"""

# Graph Pages (2 per page)
items_per_page = 2
for i in range(0, len(results), items_per_page):
    # Keep original machine ordering for the detailed pages
    page_items = results[i:i+items_per_page]
    page_num = (i // items_per_page) + 1
    total_pages = (len(results) - 1) // items_per_page + 1
    
    html_content += f"""
    <div class="page" style="padding: 10mm;">
        <div class="header">
            <span>Detail Grafik Scatter - Korelasi Steam vs Durasi</span>
            <span>Hal. {page_num} dari {total_pages}</span>
        </div>
    """
    
    for res in page_items:
        html_content += f"""
        <div class="item-container">
            <img src="data:image/png;base64,{res['b64']}" alt="{res['mc']}_{res['prog']}">
        </div>
        """
        
    html_content += """
    </div>
    """

html_content += "</body></html>"

with open(os.path.join(artifact_dir, "steam_correlation_report.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

print("Correlation HTML report generated successfully.")
