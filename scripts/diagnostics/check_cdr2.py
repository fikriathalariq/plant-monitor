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
    print(f'Machine: {m.code}, raw_temp: {m.temperature}')
