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
from django.db.models import Count

latest = MachineMinuteLog.objects.order_by('-timestamp').values('timestamp', 'data_quality').first()
print('Latest in DB:', latest)
print('Now UTC:', timezone.now().strftime('%H:%M:%S'))
