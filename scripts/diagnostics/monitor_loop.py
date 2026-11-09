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

for i in range(8):
    latest = MachineMinuteLog.objects.order_by('-timestamp').values('timestamp').first()
    now = timezone.now()
    if latest:
        gap = (now - latest['timestamp']).total_seconds()
        print(f'[check {i+1}] Latest={latest[\"timestamp\"].strftime(\"%H:%M\")}, gap={gap:.0f}s, now={now.strftime(\"%H:%M:%S\")}')
    time.sleep(15)
