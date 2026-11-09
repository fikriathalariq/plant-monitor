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

target_time = datetime(2026, 8, 29, 16, 41, 0, tzinfo=timezone.utc)
records = DyeingIdentity.objects.filter(machine_id=14, start_time_snapshot=target_time)

print(f'Records found for Machine 14 at 2026-08-29 16:41 UTC: {records.count()}')
for r in records:
    print(f'- ID: {r.id}, Created at: {r.created_at}, Orphan: {r.dyeing_process_id is None}')
