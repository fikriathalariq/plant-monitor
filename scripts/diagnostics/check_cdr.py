import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from monitoring.models import Machine, MachineMinuteLog

for code in ['CDR_PRC_02', 'CDR_PRC_03']:
    m = Machine.objects.filter(code=code).first()
    if m:
        print(f'Machine: {m.code}, status: {m.last_status}, thermal: {m.last_thermal_status}, temp: {m.temperature}, updated: {m.last_update}, active: {m.is_active}')
        log = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp').first()
        if log:
            print(f'  Last Log: {log.timestamp}, raw: {log.raw_temperature}, temp: {log.temperature}, filtered: {log.filtered_temp}, thermal_state: {log.thermal_state}')
        else:
            print('  No logs.')
    else:
        print(f'{code} not found')
