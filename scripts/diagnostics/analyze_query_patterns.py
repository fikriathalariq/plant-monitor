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

# Cari semua query yang filter/order by kolom-kolom yang ada di index
import re

files_to_check = [
    'monitoring/views.py',
    'monitoring/api_dashboard.py', 
    'monitoring/api_analytics.py',
    'monitoring/management/commands/log_minute_history.py',
    'monitoring/management/commands/aggregate_steam_history.py',
    'monitoring/management/commands/aggregate_boiler_daily.py',
    'monitoring/management/commands/process_gradient_history.py',
    'monitoring/management/commands/recalculate_thermal_analysis.py',
    'monitoring/models.py',
]

# Patterns yang menunjukkan query ke MachineMinuteLog
patterns = {
    'filter(machine=, timestamp__gte)': r'MachineMinuteLog\.objects.*?filter\([^)]*timestamp[^)]*\)',
    'filter(thermal_state=)': r'filter\([^)]*thermal_state[^)]*\)',
    'filter(machine_id=)': r'filter\([^)]*machine_id[^)]*\)',
    'order_by(timestamp)': r'order_by\([^)]*timestamp[^)]*\)',
    'filter(data_quality=)': r'filter\([^)]*data_quality[^)]*\)',
}

results = {p: [] for p in patterns}

for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        for pname, pattern in patterns.items():
            matches = re.findall(pattern, content, re.DOTALL)
            for m in matches:
                results[pname].append(f"{filepath}: {m[:120].strip()}")
    except FileNotFoundError:
        pass

for pname, matches in results.items():
    print(f"\n=== Pattern: {pname} ({len(matches)} found) ===")
    for m in matches[:5]:
        print(f"  {m}")
