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
from datetime import datetime, timezone as tz

# Tunggu menit 09:19 atau setelahnya
target_min = datetime(2026, 9, 3, 9, 19, tzinfo=tz.utc)
for _ in range(30):
    latest = MachineMinuteLog.objects.filter(timestamp__gte=target_min).order_by('-timestamp').values('machine__code', 'timestamp', 'data_quality').first()
    if latest:
        print('FOUND:', latest)
        # Distribution
        from django.db.models import Count
        dist = MachineMinuteLog.objects.filter(timestamp=latest['timestamp']).values('data_quality').annotate(cnt=Count('id'))
        for d in dist:
            print('  ', d['data_quality'], ':', d['cnt'])
        break
    time.sleep(5)
else:
    print('Timeout waiting for new log')
