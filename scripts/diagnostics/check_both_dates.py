import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime, timedelta
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.utils import timezone
from monitoring.models import DyeingProcess
from django.db.models import Count

tz = timezone.get_current_timezone()

periods = [
    {
        "name": "Tanggal 30 (30 Agu 06:00 - 31 Agu 06:00)",
        "start": timezone.make_aware(datetime(2026, 8, 30, 6, 0, 0), tz),
        "end": timezone.make_aware(datetime(2026, 8, 31, 6, 0, 0), tz)
    },
    {
        "name": "Tanggal 31 (31 Agu 06:00 - 1 Sep 06:00)",
        "start": timezone.make_aware(datetime(2026, 8, 31, 6, 0, 0), tz),
        "end": timezone.make_aware(datetime(2026, 9, 1, 6, 0, 0), tz)
    }
]

out = ["# Laporan Pengecekan Ulang Kelengkapan Identity (Tanggal 30 & 31 Agustus 2026)\n"]

for p in periods:
    qs = DyeingProcess.objects.filter(start_time__gte=p["start"], start_time__lt=p["end"]).select_related('machine', 'machine__group').annotate(id_count=Count('identity'))
    
    groups = defaultdict(lambda: {"total": 0, "filled": 0, "kosong": 0, "machines": defaultdict(lambda: {"total": 0, "filled": 0, "kosong": 0})})
    
    for process in qs:
        group_name = process.machine.group.name if process.machine and process.machine.group else "Unknown Group"
        machine_code = process.machine.code if process.machine else "Unknown Machine"
        
        has_identity = process.id_count > 0
        
        groups[group_name]["total"] += 1
        groups[group_name]["machines"][machine_code]["total"] += 1
        
        if has_identity:
            groups[group_name]["filled"] += 1
            groups[group_name]["machines"][machine_code]["filled"] += 1
        else:
            groups[group_name]["kosong"] += 1
            groups[group_name]["machines"][machine_code]["kosong"] += 1
            
    total_filled = sum(g["filled"] for g in groups.values())
    total_kosong = sum(g["kosong"] for g in groups.values())
    total = qs.count()
    
    out.append(f"## {p['name']}\n")
    out.append(f"**Total Keseluruhan Proses:** {total}\n")
    out.append(f"- **Sudah diinput (Ada Identity):** {total_filled}")
    out.append(f"- **Belum diinput (Kosong):** {total_kosong}\n")
    
    out.append("### Rincian Per Machine Group\n")
    out.append("| Machine Group | Total Proses | Sudah Diinput | Kosong |")
    out.append("|---|---|---|---|")
    for gname, stats in groups.items():
        out.append(f"| {gname} | {stats['total']} | {stats['filled']} | {stats['kosong']} |")
    
    out.append("\n### Rincian Mesin yang Masih Kosong\n")
    out.append("| Mesin | Group | Kosong | Total |")
    out.append("|---|---|---|---|")
    for gname, stats in groups.items():
        for mname, mstats in stats["machines"].items():
             if mstats["kosong"] > 0:
                 out.append(f"| {mname} | {gname} | **{mstats['kosong']}** | {mstats['total']} |")
    out.append("\n---\n")
    
    print(f"{p['name']} -> Total: {total}, Filled: {total_filled}, Kosong: {total_kosong}")

with open(r"C:\Users\HP\.gemini\antigravity\brain\45ce1ea6-0aa1-4b47-83d3-a04c35bc92ee\identity_completeness_30_31.md", "w") as f:
    f.write("\n".join(out))
