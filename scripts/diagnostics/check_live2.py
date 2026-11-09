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
cutoff = now - timedelta(minutes=1)
recent = MachineMinuteLog.objects.filter(timestamp__gte=cutoff).order_by('-timestamp').values('machine__code', 'timestamp', 'data_quality')[:5]
for r in recent:
    print(r['machine__code'], r['timestamp'].strftime('%H:%M'), r['data_quality'])
latest = MachineMinuteLog.objects.order_by('-timestamp').values_list('timestamp', flat=True).first()
print('Latest:', latest)
print('Now:', now)
delta = (now - latest).total_seconds() if latest else None
print('Gap:', delta, 'seconds')
