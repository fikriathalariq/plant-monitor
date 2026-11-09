import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import MachineMinuteLog
from django.utils import timezone

# Poll DB sampai ada log baru di menit 09:16 atau lebih
from datetime import datetime, timezone as tz
target = datetime(2026, 9, 3, 9, 16, tzinfo=tz.utc)
for _ in range(30):
    latest = MachineMinuteLog.objects.filter(timestamp__gte=target).order_by('-timestamp').values('machine__code', 'timestamp', 'temperature', 'data_quality').first()
    if latest:
        print('FOUND:', latest)
        break
    time.sleep(5)
else:
    print('No new log found within 150 seconds')
    latest_all = MachineMinuteLog.objects.order_by('-timestamp').values('machine__code', 'timestamp', 'data_quality').first()
    print('Latest in DB:', latest_all)
