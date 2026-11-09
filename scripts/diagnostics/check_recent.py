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
cutoff = now - timedelta(minutes=5)
recent = MachineMinuteLog.objects.filter(timestamp__gte=cutoff).order_by('-timestamp').values('machine__code', 'timestamp', 'filtered_temp', 'data_quality')[:10]
for r in recent:
    print(r['machine__code'], '|', r['timestamp'].strftime('%H:%M'), '|', r['filtered_temp'], '|', r['data_quality'])
