import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, re
# Cari di views.py mana saja query yang berpotensi pakai idx_log_machine_ts_dq (machine + timestamp + data_quality)
# dan idx_log_machine_ts_desc (machine + timestamp DESC)
files_to_check = [
    'monitoring/views.py',
    'monitoring/api_dashboard.py', 
    'monitoring/api_analytics.py',
    'monitoring/management/commands/log_minute_history.py',
    'monitoring/management/commands/aggregate_steam_history.py',
    'monitoring/management/commands/process_gradient_history.py',
    'monitoring/management/commands/recalculate_thermal_analysis.py',
    'monitoring/models.py',
]

# Yang kita cari: pattern order_by('-timestamp') setelah filter machine
print("=== Query yang filter machine + order -timestamp (kandidat idx_log_machine_ts_desc) ===")
for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Multi-line pattern: MachineMinuteLog dalam 5 baris ke order_by('-timestamp') 
        blocks = re.findall(r'MachineMinuteLog\.objects[^\n]*(?:\n[^\n]*){0,10}order_by\([^)]*-timestamp[^)]*\)', content)
        for b in blocks[:5]:
            short = b.replace('\n', ' ').strip()[:200]
            print(f"  {filepath}: {short}")
    except FileNotFoundError:
        pass

print("\n=== Query yang menyebut 'last()' atau 'first()' pada MachineMinuteLog (butuh sort) ===")
for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if ('MachineMinuteLog' in line or ('minute_log' in ''.join(lines[max(0,i-5):i]))) and \
               ('.last()' in line or '.first()' in line):
                ctx = ''.join(lines[max(0,i-3):i+1]).strip().replace('\n', ' ')[-200:]
                print(f"  {filepath}:{i+1}: ...{ctx}")
    except FileNotFoundError:
        pass

print("\n=== Query dengan filter data_quality (kode apapun) ===")
for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if 'data_quality' in line:
                print(f"  {filepath}:{i+1}: {line.rstrip()}")
    except FileNotFoundError:
        pass
