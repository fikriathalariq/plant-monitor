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

debug_str = '''                                # PRE-BUFFER SHIELD ACTIVE! 
                                # Do not update temperature/timestamp, but DO update machine state
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status
                                })
                                
                    if m.code == "JD_08":
                        print(f"DEBUG JD_08: temp={current_temp} valid={is_valid_reading} has_good={minute_buffer[m.code].get('has_good_reading')}")'''

clean_str = '''                                # PRE-BUFFER SHIELD ACTIVE! 
                                # Do not update temperature/timestamp, but DO update machine state
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status
                                })'''

text = text.replace(debug_str, clean_str)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
