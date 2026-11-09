import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.utils import timezone
from monitoring.models import DyeingProcess, MachineGroup
from django.db.models import Count

tz = timezone.get_current_timezone()
start_dt = timezone.make_aware(datetime(2026, 8, 30, 6, 0, 0), tz)
end_dt = timezone.make_aware(datetime(2026, 8, 31, 6, 0, 0), tz)

qs = DyeingProcess.objects.filter(start_time__gte=start_dt, start_time__lt=end_dt).select_related('machine', 'machine__group').annotate(id_count=Count('identity'))

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

out = []
out.append(f"# Laporan Kelengkapan Identity DyeingProcess\n")
out.append(f"**Periode:** 30 Agustus 2026 06:00 - 31 Agustus 2026 06:00\n")
out.append(f"**Total Keseluruhan Proses:** {qs.count()}\n")

total_filled = sum(g["filled"] for g in groups.values())
total_kosong = sum(g["kosong"] for g in groups.values())

out.append(f"- **Sudah diinput (Ada Identity):** {total_filled}")
out.append(f"- **Belum diinput (Kosong):** {total_kosong}\n")

out.append("## Rincian Per Machine Group\n")
out.append("| Machine Group | Total Proses | Sudah Diinput | Kosong |")
out.append("|---|---|---|---|")

for gname, stats in groups.items():
    out.append(f"| {gname} | {stats['total']} | {stats['filled']} | {stats['kosong']} |")

out.append("\n## Rincian Per Mesin\n")
out.append("| Mesin | Group | Total Proses | Sudah Diinput | Kosong |")
out.append("|---|---|---|---|---|")

for gname, stats in groups.items():
    for mname, mstats in stats["machines"].items():
         out.append(f"| {mname} | {gname} | {mstats['total']} | {mstats['filled']} | {mstats['kosong']} |")

with open(r"C:\Users\HP\.gemini\antigravity\brain\45ce1ea6-0aa1-4b47-83d3-a04c35bc92ee\identity_completeness_report.md", "w") as f:
    f.write("\n".join(out))

print(f"Total: {qs.count()}, Filled: {total_filled}, Kosong: {total_kosong}")
for gname, stats in groups.items():
    print(f"Group {gname}: Total {stats['total']}, Filled {stats['filled']}, Kosong {stats['kosong']}")

