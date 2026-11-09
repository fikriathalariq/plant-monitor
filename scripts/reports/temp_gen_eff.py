import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django, pytz
from datetime import datetime
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import DyeingProcess

start_date = datetime(2026, 8, 30, 0, 0, 0, tzinfo=pytz.timezone('Asia/Jakarta'))
end_date = datetime(2026, 8, 31, 23, 59, 59, tzinfo=pytz.timezone('Asia/Jakarta'))

procs = DyeingProcess.objects.filter(
    start_time__gte=start_date, start_time__lte=end_date,
    avg_steam_pressure__gt=3.8
).select_related('machine', 'identity', 'identity__program')

results = {}
for p in procs:
    if not hasattr(p, 'identity') or not p.identity or not p.identity.program: continue
    tot = (p.real_heating_duration or 0) + (p.steady_duration or 0) + (p.cooling_duration or 0)
    if tot < 40: continue

    key = (p.machine.code, p.identity.program.nama)
    if key not in results:
        ideal_h = p.identity.program.durasi_heating_ideal or 0
        ideal_s = p.identity.program.durasi_keeping_ideal or 0
        ideal_c = p.identity.program.durasi_cooling_ideal or 0
        results[key] = {
            'count': 0,
            'h': [], 's': [], 'c': [], 'steam': [],
            'ideal_h': ideal_h, 'ideal_s': ideal_s, 'ideal_c': ideal_c, 'ideal_t': ideal_h + ideal_s + ideal_c
        }
    
    results[key]['count'] += 1
    results[key]['h'].append(p.real_heating_duration or 0)
    results[key]['s'].append(p.steady_duration or 0)
    results[key]['c'].append(p.cooling_duration or 0)
    results[key]['steam'].append(p.avg_steam_pressure)

lines = []
lines.append('| Mesin | Program | N | Heat Akt/Idl | Hold Akt/Idl | Cool Akt/Idl | Total Akt/Idl | Efisiensi | Avg Steam | Catatan & Masalah |')
lines.append('|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|')

for (mc, prog), data in sorted(results.items(), key=lambda x: (x[0][0], x[0][1])):
    avg_h = np.mean(data['h'])
    avg_s = np.mean(data['s'])
    avg_c = np.mean(data['c'])
    avg_t = avg_h + avg_s + avg_c
    avg_steam = np.mean(data['steam'])
    
    catatan = []
    if avg_h > data['ideal_h'] + 30:
        catatan.append('Indikasi HE kotor/bermasalah (Heat lambat)')
    elif avg_h > data['ideal_h'] + 15:
        catatan.append('Heat sedikit lambat')
        
    if avg_s > data['ideal_s'] + 20:
        catatan.append('Hold over-duration')
        
    if avg_c > data['ideal_c'] + 30:
        catatan.append('Cooling lambat (Isu aliran air/chiller)')
    elif avg_c > data['ideal_c'] + 15:
        catatan.append('Cooling sedikit lambat')
        
    if avg_h <= data['ideal_h'] + 10 and avg_s <= data['ideal_s'] + 10 and avg_c <= data['ideal_c'] + 10:
        catatan.append('Performa Sangat Baik')
        
    cat_str = ', '.join(catatan) if catatan else 'Normal'
    
    count = data['count']
    ih = data['ideal_h']
    is_ = data['ideal_s']
    ic = data['ideal_c']
    it = data['ideal_t']
    
    # Calculate Efisiensi: (Ideal Total / Actual Total) * 100
    efisiensi = (it / avg_t) * 100 if avg_t > 0 else 0
    
    lines.append(f'| **{mc}** | {prog} | {count} | {avg_h:.1f} / {ih} | {avg_s:.1f} / {is_} | {avg_c:.1f} / {ic} | **{avg_t:.1f}** / {it} | **{efisiensi:.1f}%** | {avg_steam:.2f} bar | {cat_str} |')

output_path = r'C:\Users\HP\.gemini\antigravity\brain\3cd1910f-c004-4696-aeaa-1b5108d5599b\efficiency_30_31_aug.md'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('# Analisis Efisiensi Mesin (30 - 31 Agustus 2026)\n\n')
    f.write('*Kondisi: Rata-rata Steam Pressure > 3.8 bar (Steam Sehat)*\n\n')
    f.write('\n'.join(lines))
    f.write('\n\n**Kesimpulan Singkat:**\n')
    f.write('Analisis ini menunjukkan apakah suatu mesin bisa memanfaatkan steam yang melimpah secara efisien. Jika nilai Heat aktual jauh melebihi ideal padahal steam rata-rata > 3.8 bar, kemungkinan besar ada gangguan teknis pada *Heat Exchanger* mesin tersebut.\n')

print('Done')
