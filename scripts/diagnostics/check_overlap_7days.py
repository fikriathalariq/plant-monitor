import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import timedelta, datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.utils import timezone
from monitoring.models import DyeingIdentity
from collections import defaultdict

# Setup time window: last 7 days from now
tz = timezone.get_current_timezone()
now = timezone.now()
seven_days_ago = now - timedelta(days=7)

qs = DyeingIdentity.objects.exclude(nomor_order__exact='').exclude(batch__exact='').select_related('machine', 'machine__group', 'dyeing_process')

groups = defaultdict(list)
for identity in qs:
    no_order = identity.nomor_order.strip()
    batch = identity.batch.strip()
    if not no_order or not batch:
        continue
    
    group_name = identity.machine.group.name if identity.machine and identity.machine.group else "Unknown"
    
    # Get start_time from dyeing_process, or fallback to start_time_snapshot
    start_time_obj = None
    if identity.dyeing_process and hasattr(identity.dyeing_process, 'start_time') and identity.dyeing_process.start_time:
        start_time_obj = identity.dyeing_process.start_time
    elif hasattr(identity, 'start_time_snapshot') and identity.start_time_snapshot:
        start_time_obj = identity.start_time_snapshot
        
    start_time_str = start_time_obj.strftime('%Y-%m-%d %H:%M') if start_time_obj else "-"
    
    groups[(no_order, batch)].append({
        'id': identity.id,
        'machine': identity.machine.code if identity.machine else "Unknown",
        'group': group_name,
        'time_obj': identity.created_at,
        'time': identity.created_at.strftime('%Y-%m-%d %H:%M') if identity.created_at else "-",
        'start_time': start_time_str,
        'jenis': identity.jenis_proses or "-"
    })

results = []
for (no_order, batch), items in groups.items():
    groups_present = set(item['group'] for item in items)
    if "Jet Dyeing Gedung Processing" in groups_present and "Jet Relax Gedung Processing" in groups_present:
        recent = any(item['time_obj'] and item['time_obj'] >= seven_days_ago for item in items)
        if recent:
            results.append((no_order, batch, items))

out = ["# Laporan Kesamaan Nomor Order dan Batch Antar Grup Mesin (7 Hari Terakhir)\n"]
out.append(f"**Periode Analisis:** 7 Hari Terakhir (sejak {seven_days_ago.strftime('%d %b %Y')})\n")

if not results:
    out.append("Tidak ditemukan Nomor Order dan Batch yang sama antara Jet Dyeing dan Jet Relax dalam 7 hari terakhir.\n")
    print("MATCHES_FOUND: 0")
else:
    out.append(f"Ditemukan **{len(results)} pasang** Nomor Order & Batch yang diproses di kedua grup mesin dalam kurun waktu seminggu terakhir.\n")
    print(f"MATCHES_FOUND: {len(results)}")
    
    for no_order, batch, items in results:
        out.append(f"### Nomor Order: {no_order} | Batch: {batch}")
        out.append("| ID Identity | Mesin | Group Mesin | Jenis Proses | Start Time Proses | Waktu Input (Created) |")
        out.append("|---|---|---|---|---|---|")
        items_sorted = sorted(items, key=lambda x: x['time_obj'] if x['time_obj'] else datetime.min)
        for item in items_sorted:
            if item['group'] in ["Jet Dyeing Gedung Processing", "Jet Relax Gedung Processing"]:
                out.append(f"| {item['id']} | {item['machine']} | **{item['group']}** | {item['jenis']} | **{item['start_time']}** | {item['time']} |")
            else:
                out.append(f"| {item['id']} | {item['machine']} | {item['group']} | {item['jenis']} | {item['start_time']} | {item['time']} |")
        out.append("\n")

with open(r"C:\Users\HP\.gemini\antigravity\brain\45ce1ea6-0aa1-4b47-83d3-a04c35bc92ee\matching_order_batch_7days.md", "w") as f:
    f.write("\n".join(out))
