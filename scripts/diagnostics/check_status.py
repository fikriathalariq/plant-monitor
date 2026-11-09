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
from datetime import timedelta

now = timezone.now()
# check data_quality distribution in last 30 min
cutoff = now - timedelta(minutes=30)
from django.db.models import Count
dist = MachineMinuteLog.objects.filter(timestamp__gte=cutoff).values('data_quality').annotate(cnt=Count('id'))
for d in dist:
    print(d['data_quality'], ':', d['cnt'])

print('---')
# check latest timestamp
latest = MachineMinuteLog.objects.order_by('-timestamp').first()
print('Latest log:', latest.timestamp if latest else 'None')
print('Now:', now)
if latest:
    print('Delta:', (now - latest.timestamp).total_seconds(), 'seconds')
