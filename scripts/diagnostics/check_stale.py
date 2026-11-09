import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import Machine
from monitoring.utils.signal_freshness import is_signal_stale
from django.utils import timezone

now = timezone.now()
for code in ['JD_01', 'JR_02', 'Oil_Temp', 'ZET_01', 'Flat_2', 'Steamer']:
    m = Machine.objects.filter(code=code).first()
    if m:
        stale = is_signal_stale(m, now=now)
        print(f'{code}: stale={stale}, temp={m.temperature}, last_valid_reading_at={m.last_valid_reading_at}, operation_mode={m.operation_mode}')
