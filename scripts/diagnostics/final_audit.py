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
from django.db.models import Count
from django.utils import timezone

for i in range(12):
    latest = MachineMinuteLog.objects.order_by('-timestamp').values('timestamp').first()
    now = timezone.now()
    if latest:
        ts = latest['timestamp']
        gap = (now - ts).total_seconds()
        print("Check", i+1, "Latest:", ts.strftime("%H:%M"), "Gap:", int(gap), "s, Now:", now.strftime("%H:%M:%S"))
        
        dist = MachineMinuteLog.objects.filter(timestamp=ts).values('data_quality').annotate(cnt=Count('id'))
        for d in dist:
            print("  ", d['data_quality'], ":", d['cnt'])
    time.sleep(10)
