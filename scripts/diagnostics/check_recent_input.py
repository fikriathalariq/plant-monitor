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
from datetime import datetime, timezone

# Check the exact record inputted at 10:06:43
# machine=17, start_time_snapshot=2026-08-29T23:53:00+00:00
target_time = datetime(2026, 8, 29, 23, 53, 0, tzinfo=timezone.utc)
records = DyeingIdentity.objects.filter(machine_id=17, start_time_snapshot=target_time)

print(f'Records found for Machine 17 at 2026-08-29 23:53 UTC: {records.count()}')
for r in records:
    print(f'- ID: {r.id}, Created at: {r.created_at}, Orphan: {r.dyeing_process_id is None}')
