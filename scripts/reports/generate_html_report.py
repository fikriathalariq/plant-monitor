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
from scipy import stats
import base64

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

artifact_dir = r"C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b"
start_date = datetime(2026, 3, 25, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
jd03_start = datetime(2026, 6, 28, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))

machines_qs = Machine.objects.filter(group__name__in=['Jet Dyeing Gedung Processing','Jet Relax Gedung Processing']).exclude(code__in=['JD_06','JD_07','JD_JetMiniHSK']).order_by('code')

def clean_iqr(data):
    if not data: return []
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    return [x for x in data if lower_bound <= x <= upper_bound]

def get_base64_img(img_path):
    with open(img_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Laporan SPC Fleet</title>
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: Arial, sans-serif; }
        .page { page-break-after: always; margin-bottom: 20px; }
        .page:last-child { page-break-after: avoid; }
        .chart-container { text-align: center; margin-bottom: 15px; }
        img { max-width: 100%; max-height: 200mm; object-fit: contain; }
        .title { text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .subtitle { text-align: center; font-size: 16px; margin-bottom: 20px; color: #555; }
        
        .anomali-box { border: 5px solid #d9534f; padding: 15px; background-color: #fdf2f2; height: 90vh; box-sizing: border-box; }
        .anomali-badge { color: white; background-color: #d9534f; font-weight: bold; font-size: 18px; text-align: center; margin-bottom: 15px; padding: 10px; border-radius: 5px; }
        .normal-box { border: 2px solid #5cb85c; padding: 15px; height: 90vh; box-sizing: border-box; }
        .normal-badge { color: white; background-color: #5cb85c; font-weight: bold; font-size: 18px; text-align: center; margin-bottom: 15px; padding: 10px; border-radius: 5px; }
    </style>
</head>
<body>
"""

html_content += """
<div class="page" style="display: flex; flex-direction: column; justify-content: center; height: 90vh; text-align: center;">
    <h1 style="font-size:42px; margin-bottom: 10px;">Laporan Analisis SPC Mesin Dyeing</h1>
    <h3 style="font-size:24px; margin-top: 0; color: #555;">Grup Mesin JD_PRC & JR_PRC</h3>
    <br><br>
    <p style="font-size:18px;">Dicetak otomatis dengan kondisi filter:</p>
    <ul style="list-style-type:none; padding:0; font-size:18px; color:#333;">
        <li>Suhu Target: 120-130&deg;C</li>
        <li>Steam Pressure: > 3.8 bar</li>
        <li>Minimum Sampel (N) &ge; 10</li>
        <li>Pembersihan Outlier Ekstrem: IQR Method</li>
    </ul>
</div>
"""

results = []

for mc in machines_qs:
    mc_start = jd03_start if mc.code == 'JD_03' else start_date
    processes = DyeingProcess.objects.filter(
        machine=mc, start_time__gte=mc_start,
        identity__program__suhu_max__gte=120, identity__program__suhu_max__lte=130,
        avg_steam_pressure__gt=3.8
    ).select_related('identity', 'identity__program')
    
    valid_processes = []
    for p in processes:
        if (p.real_heating_duration or 0) + (p.steady_duration or 0) + (p.cooling_duration or 0) < 40: continue
        if p.max_temp and p.identity.program and abs(p.max_temp - p.identity.program.suhu_max) <= 15:
            valid_processes.append(p)
            
    program_counts = {}
    for p in valid_processes:
        nm = p.identity.program.nama
        if nm not in program_counts:
            program_counts[nm] = {'count': 0, 'h_data': [], 't_data': []}
        program_counts[nm]['count'] += 1
        h = p.real_heating_duration or 0
        t = h + (p.steady_duration or 0) + (p.cooling_duration or 0)
        program_counts[nm]['h_data'].append(h)
        program_counts[nm]['t_data'].append(t)
            
    for prog_name, data in sorted(program_counts.items(), key=lambda x: x[1]['count'], reverse=True):
        if data['count'] < 10: continue
        
        h_cl = clean_iqr(data['h_data'])
        t_cl = clean_iqr(data['t_data'])
        
        std_h = np.std(h_cl) if h_cl else 0
        std_t = np.std(t_cl) if t_cl else 0
        skew_h = stats.skew(h_cl) if len(set(h_cl)) > 2 else 0
        skew_t = stats.skew(t_cl) if len(set(t_cl)) > 2 else 0
        
        is_anomali = (std_h > 15 or std_t > 20 or abs(skew_h) > 1.0 or abs(skew_t) > 1.0)
        
        diagnosis = []
        if std_h > 15 or std_t > 20: diagnosis.append("Variansi Ekstrem")
        if abs(skew_h) > 1.0 or abs(skew_t) > 1.0: diagnosis.append("Skewness Tinggi (Outlier)")
        if not diagnosis: diagnosis = ["Terkendali / Konsisten"]
        
        img_name = f"spc_deep_full_{mc.code}_{prog_name.replace(' ', '_').replace('.', '')}.png"
        img_path = os.path.join(artifact_dir, img_name)
        
        if os.path.exists(img_path):
            img_b64 = get_base64_img(img_path)
            results.append({
                'mc': mc.code, 'prog': prog_name, 'n': data['count'],
                'is_anomali': is_anomali, 'diag': " + ".join(diagnosis),
                'b64': img_b64
            })

for res in results:
    box_class = "anomali-box" if res['is_anomali'] else "normal-box"
    badge = f"<div class='anomali-badge'>&#9888; ANOMALI: {res['diag']}</div>" if res['is_anomali'] else f"<div class='normal-badge'>&#10003; STATUS: {res['diag']}</div>"
    
    html_content += f"""
    <div class="page">
        <div class="{box_class}">
            {badge}
            <div class="title">Mesin {res['mc']} &mdash; Program {res['prog']}</div>
            <div class="subtitle">Jumlah Proses (N) = {res['n']}</div>
            <div class="chart-container">
                <img src="data:image/png;base64,{res['b64']}" alt="{res['mc']}_{res['prog']}"/>
            </div>
        </div>
    </div>
    """

html_content += "</body></html>"

with open(os.path.join(artifact_dir, "spc_presentation.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML presentation generated successfully.")
