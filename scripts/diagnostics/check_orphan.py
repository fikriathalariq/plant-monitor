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
from django.utils import timezone
from datetime import date

target_date = date(2026, 8, 29)
identities = DyeingIdentity.objects.filter(start_time_snapshot__date=target_date)
orphans = identities.filter(dyeing_process__isnull=True)

for o in orphans:
    # Get all fields
    data = {f.name: getattr(o, f.name) for f in o._meta.fields}
    print(data)
