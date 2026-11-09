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

text = text.replace('last_status=machine_status,  # Use mapped status for log display (legacy field, data_quality=data_qual)', 'last_status=machine_status,  # Use mapped status for log display (legacy field)')

text = text.replace('                                    kalman_grad_x=new_state.kalman_grad_x,\n                                )', '                                    kalman_grad_x=new_state.kalman_grad_x,\n                                    data_quality=data_qual,\n                                )', 1)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
