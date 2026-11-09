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

# Cari data_quality usage di seluruh kode
print("=== Semua penggunaan 'data_quality' dalam query ===")
for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if 'data_quality' in line and ('filter' in line or 'order' in line or 'annotate' in line or 'values' in line):
                print(f"  {filepath}:{i+1}: {line.rstrip()}")
    except FileNotFoundError:
        pass

# Cari thermal_state filter (hanya yang buat query DB, bukan Python logic)
print("\n=== Semua query filter berdasarkan thermal_state ===")
for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if 'thermal_state' in line and ('filter' in line or 'Q(' in line):
                print(f"  {filepath}:{i+1}: {line.rstrip()}")
    except FileNotFoundError:
        pass

# Cek index di migrations - kapan dibuat?
print("\n=== Index dibuat di migration mana? ===")
import os
for fname in sorted(os.listdir('monitoring/migrations')):
    if fname.endswith('.py'):
        fpath = f'monitoring/migrations/{fname}'
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'monitoring__machine_f2f068_idx' in content or 'idx_log_machine_ts_dq' in content or 'idx_log_machine_ts_desc' in content or 'monitoring__thermal_484794_idx' in content:
            print(f"  {fname}: contains index definitions")
