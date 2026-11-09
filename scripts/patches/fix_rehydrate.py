import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open('monitoring/management/commands/log_minute_history.py', 'r', encoding='utf-8') as f:
    text = f.read()

rehydrate_fix = '''        for m in Machine.objects.filter(is_active=True):
            if m.operation_mode != 'AUTO':
                continue
                
            last_log = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp').first()'''

text = text.replace('''        for m in Machine.objects.filter(is_active=True):
            last_log = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp').first()''', rehydrate_fix)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
