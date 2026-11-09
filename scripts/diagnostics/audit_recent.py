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
from django.db.models import Count

now = timezone.now()
cutoff = now - timedelta(minutes=15)
minutes_stats = MachineMinuteLog.objects.filter(timestamp__gte=cutoff).values('timestamp', 'data_quality').annotate(cnt=Count('id')).order_by('-timestamp')

import itertools
grouped = itertools.groupby(minutes_stats, key=lambda x: x['timestamp'])
for ts, group in grouped:
    print(ts.strftime('%H:%M'), end=' | ')
    stats = []
    for g in group:
        stats.append(f"{g['data_quality']}: {g['cnt']}")
    print(", ".join(stats))

print('Current UTC time:', now.strftime('%H:%M:%S'))
