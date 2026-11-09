import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, sys, django, statistics
from collections import defaultdict
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity

qs = DyeingIdentity.objects.filter(
    dyeing_process__isnull=False,
    program__isnull=False,
    dyeing_process__is_valid_process=True,
    dyeing_process__max_temp__isnull=False,
    program__suhu_max__isnull=False
).select_related('machine', 'dyeing_process', 'program')

data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
machine_diffs = defaultdict(list)
machine_freq = defaultdict(int)

for r in qs:
    actual = r.dyeing_process.max_temp
    prog = r.program.suhu_max
    prog_name = r.program.nama
    mac = r.machine.code if r.machine else "UNKNOWN"
    
    diff = actual - prog
    if abs(diff) > 20:
        continue

    data[mac][prog][prog_name].append(diff)
    machine_diffs[mac].append(diff)
    
    if abs(diff) > 0.5:
        machine_freq[mac] += 1

html_path = r"C:\Users\HP\.gemini\antigravity\brain\3c9a3eae-d5be-44c9-b0b1-29e9f62c1f25\machine_temp_analysis_report.html"

html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Laporan Analisis Suhu Mesin</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; padding: 20px; }
        h1, h2, h3 { color: #2c3e50; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; page-break-inside: auto; }
        tr { page-break-inside: avoid; page-break-after: auto; }
        th, td { border: 1px solid #bdc3c7; padding: 8px 12px; text-align: left; }
        th { background-color: #ecf0f1; font-weight: bold; }
        .row-group { background-color: #f9f9f9; font-weight: bold; }
        .row-child { padding-left: 30px; font-size: 0.9em; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        @media print {
            body { padding: 0; font-size: 11pt; }
            table { page-break-inside: auto; }
            tr { page-break-inside: avoid; page-break-after: auto; }
            h2, h3 { page-break-after: avoid; }
            h2 { page-break-before: always; }
            h2:first-of-type { page-break-before: auto; }
            @page { margin: 1.5cm; }
            .no-print { display: none; }
        }
        .header-info { margin-bottom: 30px; border-bottom: 2px solid #34495e; padding-bottom: 10px; }
    </style>
</head>
<body>
    <button class="no-print" onclick="window.print()" style="padding: 10px 20px; font-size: 16px; margin-bottom: 20px; cursor: pointer; background-color: #3498db; color: white; border: none; border-radius: 5px;">&#128438; Cetak Laporan (Print PDF)</button>
    
    <div class="header-info">
        <h1>Laporan Analisis Suhu Aktual vs Suhu Program</h1>
        <p><strong>Tanggal Cetak:</strong> {date}</p>
        <p><strong>Keterangan:</strong> Laporan ini menyajikan selisih rata-rata suhu maksimal aktual mesin terhadap suhu target program.<br>
        <em>* Data outlier ekstrem (> 20°C) telah dibersihkan. Nilai negatif (-) berarti suhu aktual di bawah target, positif (+) berarti di atas target.</em></p>
    </div>
"""

html_content = html_content.replace("{date}", datetime.datetime.now().strftime("%d %B %Y %H:%M"))

html_content += """
    <h2>1. Top Mesin Paling Sering Menyimpang (> 0.5°C)</h2>
    <table>
        <thead>
            <tr>
                <th class="text-center" style="width: 50px;">No</th>
                <th>Kode Mesin</th>
                <th class="text-center">Frekuensi Menyimpang</th>
                <th class="text-center">Total Batch Tercatat</th>
            </tr>
        </thead>
        <tbody>
"""

for idx, (mac, freq) in enumerate(sorted(machine_freq.items(), key=lambda x: x[1], reverse=True)[:15]):
    total_data = len(machine_diffs[mac])
    html_content += f"<tr><td class='text-center'>{idx+1}</td><td>{mac}</td><td class='text-center'>{freq} kali</td><td class='text-center'>{total_data}</td></tr>\n"

html_content += """
        </tbody>
    </table>
"""

html_content += """
    <h2>2. Rincian Performa per Mesin & Program</h2>
"""

for mac in sorted(data.keys()):
    html_content += f"<h3>Mesin: {mac}</h3>\n"
    html_content += """
    <table>
        <thead>
            <tr>
                <th>Target Suhu / Program</th>
                <th class="text-right">Rata-rata Selisih (°C)</th>
                <th class="text-right">Standar Deviasi (°C)</th>
                <th class="text-center">Total Batch</th>
            </tr>
        </thead>
        <tbody>
    """
    for prog_suhu in sorted(data[mac].keys()):
        all_diffs = []
        for diffs in data[mac][prog_suhu].values():
            all_diffs.extend(diffs)
            
        suhu_avg = sum(all_diffs) / len(all_diffs)
        suhu_std = statistics.stdev(all_diffs) if len(all_diffs) > 1 else 0.0
        suhu_avg_str = f"+{suhu_avg:.2f}" if suhu_avg > 0 else f"{suhu_avg:.2f}"
        
        html_content += f"<tr class='row-group'><td>Target Suhu: {prog_suhu} °C</td><td class='text-right'>{suhu_avg_str}</td><td class='text-right'>{suhu_std:.2f}</td><td class='text-center'>{len(all_diffs)}</td></tr>\n"
        
        for prog_name in sorted(data[mac][prog_suhu].keys()):
            diffs = data[mac][prog_suhu][prog_name]
            avg = sum(diffs) / len(diffs)
            std = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
            avg_str = f"+{avg:.2f}" if avg > 0 else f"{avg:.2f}"
            html_content += f"<tr><td class='row-child'>&#8627; Program: {prog_name}</td><td class='text-right'>{avg_str}</td><td class='text-right'>{std:.2f}</td><td class='text-center'>{len(diffs)}</td></tr>\n"
            
    html_content += "</tbody></table>\n"

html_content += """
</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"HTML Report generated at {html_path}")
