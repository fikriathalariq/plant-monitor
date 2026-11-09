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

# Add a debug print in the sampling loop
debug_str = '''                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({'temperature': current_temp, 'timestamp': now})
                            else:
                                pass # PRE-BUFFER SHIELD ACTIVE! Do not update timestamp.
                                
                    if m.code == "JD_08":
                        print(f"DEBUG JD_08: temp={current_temp} valid={is_valid_reading} has_good={minute_buffer[m.code].get('has_good_reading')}")'''

text = text.replace('''                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({'temperature': current_temp, 'timestamp': now})
                            else:
                                pass # PRE-BUFFER SHIELD ACTIVE! Do not update timestamp.''', debug_str)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
