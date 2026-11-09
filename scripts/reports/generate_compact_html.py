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
        
        img_name = f"spc_deep_full_{mc.code}_{prog_name.replace(' ', '_').replace('.', '')}.png"
        img_path = os.path.join(artifact_dir, img_name)
        
        if os.path.exists(img_path):
            img_b64 = get_base64_img(img_path)
            results.append({
                'mc': mc.code, 'prog': prog_name, 'n': data['count'],
                'is_anomali': is_anomali,
                'b64': img_b64
            })


html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Laporan SPC Fleet (Compact)</title>
    <style>
        @page { size: A4; margin: 10mm; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #fff; color: #333; margin: 0; padding: 0; }
        .page { width: 190mm; min-height: 277mm; padding: 0; margin: 0 auto; background: white; page-break-after: always; box-sizing: border-box; }
        .page:last-child { page-break-after: avoid; }
        
        /* Cover Page Styling */
        .cover-page { display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; height: 277mm; }
        .cover-title { font-size: 32px; font-weight: bold; margin-bottom: 20px; }
        .cover-subtitle { font-size: 20px; color: #666; margin-bottom: 40px; }
        .cover-meta { font-size: 14px; text-align: left; padding: 20px; border: 1px solid #ccc; border-radius: 8px; background: #fafafa; }
        
        /* Inner Pages Styling */
        .header { display: flex; justify-content: space-between; border-bottom: 2px solid #ccc; padding-bottom: 5px; margin-bottom: 10px; font-size: 12px; color: #777; }
        
        .item-container { margin-bottom: 5mm; width: 100%; text-align: center;}
        .item-header-container { text-align: left; padding-left: 5px; margin-bottom: 2px; }
        .item-header { font-size: 14px; font-weight: bold; padding-bottom: 2px; display: inline-block; }
        
        .is-normal { border-bottom: 1px solid #ccc; color: #333; }
        .is-anomali { border-bottom: 2px solid #d9534f; color: #d9534f; }
        
        img { width: 100%; height: auto; max-height: 120mm; object-fit: contain; }
    </style>
</head>
<body>
"""

# Cover Page
html_content += f"""
<div class="page cover-page">
    <div class="cover-title">Laporan Analisis SPC<br>Armada Mesin Dyeing (Appendix)</div>
    <div class="cover-subtitle">Grup Mesin JD_PRC & JR_PRC</div>
    <div class="cover-meta">
        <strong>Filter Parameter:</strong>
        <ul style="margin-top: 5px; padding-left: 20px;">
            <li>Suhu Target: 120-130&deg;C</li>
            <li>Steam Pressure: &gt; 3.8 bar</li>
            <li>Min. Sampel (N): &ge; 10</li>
            <li>Outlier Removal: IQR Method</li>
        </ul>
        <strong>Legenda Penanda:</strong>
        <ul style="margin-top: 5px; padding-left: 20px; list-style-type: none;">
            <li><span style="color:#333;">Mesin - Program (N)</span> = Proses Normal / Konsisten</li>
            <li><span style="color:#d9534f; font-weight:bold;">&#9650; Mesin - Program (N)</span> = Anomali (Variansi Ekstrem / Skewness)</li>
        </ul>
        <div style="margin-top: 20px; text-align: right; font-style: italic;">Dicetak pada: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>
</div>
"""

# Pages
items_per_page = 2
for i in range(0, len(results), items_per_page):
    page_items = results[i:i+items_per_page]
    page_num = (i // items_per_page) + 1
    total_pages = (len(results) - 1) // items_per_page + 1
    
    html_content += f"""
    <div class="page" style="padding-top: 10mm;">
        <div class="header">
            <span>Appendix: Grafik Distribusi SPC (JD_PRC & JR_PRC)</span>
            <span>Hal. {page_num} dari {total_pages}</span>
        </div>
    """
    
    for res in page_items:
        header_class = "is-anomali" if res['is_anomali'] else "is-normal"
        prefix = "&#9650; " if res['is_anomali'] else ""
        
        html_content += f"""
        <div class="item-container">
            <div class="item-header-container">
                <div class="item-header {header_class}">
                    {prefix}{res['mc']} &mdash; {res['prog']} (N={res['n']})
                </div>
            </div>
            <img src="data:image/png;base64,{res['b64']}" alt="{res['mc']}_{res['prog']}">
        </div>
        """
        
    html_content += """
    </div>
    """

html_content += "</body></html>"

with open(os.path.join(artifact_dir, "spc_presentation_compact.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

print("Compact HTML presentation generated successfully.")
