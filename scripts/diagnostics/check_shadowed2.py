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
from monitoring.models import MachineMinuteLog
from django.utils import timezone
from datetime import timedelta, datetime, timezone as tz

target_min = datetime(2026, 9, 3, 9, 16, tzinfo=tz.utc)

shadowed = MachineMinuteLog.objects.filter(timestamp=target_min, data_quality='SHADOWED').values_list('machine__code', flat=True)
print('SHADOWED at 09:16:', list(shadowed))
print()
normal = MachineMinuteLog.objects.filter(timestamp=target_min, data_quality='NORMAL').values_list('machine__code', flat=True)
print('NORMAL at 09:16:', list(normal))
