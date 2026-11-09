import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import csv
from datetime import datetime, date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import ProductionPlanBatch, DyeingProcess, Machine

START_DATE = date(2026, 8, 11)
END_DATE = date(2026, 8, 21)

import re

# Fetch current batches
batches = ProductionPlanBatch.objects.filter(
    plan__shift_date__gte=START_DATE,
    plan__shift_date__lte=END_DATE
).select_related('plan', 'machine')

results = []
machine_procs = {}

for b in batches:
    m = re.search(r'Batch #(\d+)', b.label)
    if not m:
        continue
    bn = m.group(1)
    proc = DyeingProcess.objects.filter(machine=b.machine, batch_number=bn).first()
    if not proc:
        continue
    
    from django.utils import timezone
    tz = timezone.get_current_timezone()
    orig_start_dt = timezone.localtime(proc.start_time, tz)
    
    # Calculate orig_start_abs relative to 2026-08-11 06:00:00 LOCAL TIME
    base_dt = datetime(2026, 8, 11, 6, 0, 0, tzinfo=tz)
    orig_start_abs = int((orig_start_dt - base_dt).total_seconds() / 60)
    
    # Total original duration (we can use the one from the blocks since it's the original unless we overwrote it)
    # Wait, ProductionPlanBlock duration is ALREADY overwritten!
    # So I need to get the original duration from DyeingProcess!
    heat = proc.real_heating_duration or 0
    hold = proc.steady_duration or 0
    cool = proc.cooling_duration or 0
    orig_total_dur = heat + hold + cool
    orig_end_abs = orig_start_abs + orig_total_dur
    
    day_idx = (b.plan.shift_date - START_DATE).days
    current_start_abs = day_idx * 1440 + b.start_offset_minutes
    
    if b.machine.code not in machine_procs:
        machine_procs[b.machine.code] = []
        
    machine_procs[b.machine.code].append({
        'batch_label': b.label,
        'orig_start_abs': orig_start_abs,
        'orig_end_abs': orig_end_abs,
        'current_start_abs': current_start_abs,
        'orig_start_dt': orig_start_dt,
        'proc_id': proc.id,
        'shift_date': b.plan.shift_date
    })

anomalies = []

for mc, procs in machine_procs.items():
    procs.sort(key=lambda x: x['orig_start_abs'])
    
    for i, p in enumerate(procs):
        if i == 0:
            real_gap = float('inf')
        else:
            prev = procs[i-1]
            real_gap = p['orig_start_abs'] - prev['orig_end_abs']
            
        shift_diff = p['current_start_abs'] - p['orig_start_abs']
        
        if real_gap > 120 and shift_diff < -5:
            anomalies.append({
                'Mesin': mc,
                'Batch': p['batch_label'],
                'Gap_Asli_Menit': "Kosong (Batch Pertama)" if i == 0 else real_gap,
                'Dimajukan_Menit': shift_diff,
                'Waktu_Asli': p['orig_start_dt'].strftime('%Y-%m-%d %H:%M'),
                'Waktu_Sekarang': (base_dt + timedelta(minutes=p['current_start_abs'])).strftime('%Y-%m-%d %H:%M')
            })

csv_file = 'C:\\Users\\HP\\Documents\\Plant-Monitor\\plant-monitor\\anomali_maju_kosong.csv'
keys = ['Mesin', 'Batch', 'Gap_Asli_Menit', 'Dimajukan_Menit', 'Waktu_Asli', 'Waktu_Sekarang']

with open(csv_file, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=keys)
    writer.writeheader()
    writer.writerows(anomalies)
    
print(f"Total anomali ditemukan: {len(anomalies)}")
print(f"File CSV disimpan di: {csv_file}")
