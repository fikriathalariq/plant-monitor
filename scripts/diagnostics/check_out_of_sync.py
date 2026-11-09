import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import sys, os, django
sys.path.insert(0, r'c:\Users\HP\Documents\Plant-Monitor\plant-monitor')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity

# Find identities with start_time_snapshot that is wildly out of sync with created_at
for i in DyeingIdentity.objects.order_by('-created_at')[:50]:
    diff = abs((i.created_at - i.start_time_snapshot).total_seconds())
    if diff > 86400 * 5: # More than 5 days difference
        print(f'ID: {i.id}, Created: {i.created_at.date()}, Snapshot: {i.start_time_snapshot.date()}, Machine: {i.machine.name}')
