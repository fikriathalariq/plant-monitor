import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity
from collections import defaultdict

# Only get identities that have both nomor_order and batch filled
qs = DyeingIdentity.objects.exclude(nomor_order__exact='').exclude(batch__exact='').select_related('machine', 'machine__group', 'dyeing_process')

# Group by (nomor_order, batch)
groups = defaultdict(list)
for identity in qs:
    no_order = identity.nomor_order.strip()
    batch = identity.batch.strip()
    if not no_order or not batch:
        continue
    
    group_name = identity.machine.group.name if identity.machine and identity.machine.group else "Unknown"
    groups[(no_order, batch)].append({
        'id': identity.id,
        'machine': identity.machine.code if identity.machine else "Unknown",
        'group': group_name,
        'time': identity.created_at.strftime('%Y-%m-%d %H:%M') if identity.created_at else "-",
        'jenis': identity.jenis_proses or "-"
    })

# Find intersections
results = []
for (no_order, batch), items in groups.items():
    groups_present = set(item['group'] for item in items)
    if "Jet Dyeing Gedung Processing" in groups_present and "Jet Relax Gedung Processing" in groups_present:
        results.append((no_order, batch, items))

out = ["# Laporan Kesamaan Nomor Order dan Batch Antar Grup Mesin\n"]

if not results:
    out.append("Tidak ditemukan Nomor Order dan Batch yang sama antara Jet Dyeing dan Jet Relax Gedung Processing.\n")
    print("MATCHES_FOUND: 0")
else:
    out.append(f"Ditemukan **{len(results)} pasang** Nomor Order & Batch yang diproses di kedua grup mesin (Jet Dyeing & Jet Relax).\n")
    print(f"MATCHES_FOUND: {len(results)}")
    
    for no_order, batch, items in results:
        out.append(f"### Nomor Order: {no_order} | Batch: {batch}")
        out.append("| ID Identity | Mesin | Group Mesin | Jenis Proses | Waktu Input |")
        out.append("|---|---|---|---|---|")
        # Sort items by time
        items_sorted = sorted(items, key=lambda x: x['time'])
        for item in items_sorted:
            # Highlight the matching groups
            if item['group'] in ["Jet Dyeing Gedung Processing", "Jet Relax Gedung Processing"]:
                out.append(f"| {item['id']} | {item['machine']} | **{item['group']}** | {item['jenis']} | {item['time']} |")
            else:
                out.append(f"| {item['id']} | {item['machine']} | {item['group']} | {item['jenis']} | {item['time']} |")
        out.append("\n")

with open(r"C:\Users\HP\.gemini\antigravity\brain\45ce1ea6-0aa1-4b47-83d3-a04c35bc92ee\matching_order_batch.md", "w") as f:
    f.write("\n".join(out))
