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

sampling_fix_old = '''                    else:
                        if is_valid_reading:
                            minute_buffer[m.code].update({
                                'temperature': current_temp,
                                'timestamp': now,
                                'has_good_reading': True,
                            })
                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({'temperature': current_temp, 'timestamp': now})
                            else:
                                pass # PRE-BUFFER SHIELD ACTIVE! Do not update timestamp.'''

sampling_fix_new = '''                    else:
                        if is_valid_reading:
                            minute_buffer[m.code].update({
                                'machine': m,
                                'temperature': current_temp,
                                'operation_mode': m.operation_mode,
                                'manual_status': m.manual_status,
                                'timestamp': now,
                                'has_good_reading': True,
                            })
                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'temperature': current_temp,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status,
                                    'timestamp': now
                                })
                            else:
                                # PRE-BUFFER SHIELD ACTIVE! 
                                # Do not update temperature/timestamp, but DO update machine state
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status
                                })'''

text = text.replace(sampling_fix_old, sampling_fix_new)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
