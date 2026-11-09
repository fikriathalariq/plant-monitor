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

from monitoring.models import DyeingProcess
from datetime import datetime, timezone, timedelta

target_time = datetime(2026, 8, 28, 23, 31, 0, tzinfo=timezone.utc)
start_range = target_time - timedelta(hours=2)
end_range = target_time + timedelta(hours=2)

processes = DyeingProcess.objects.filter(machine_id=26, start_time__range=(start_range, end_range))
# Machine JR 12 is ID 26? Let me check Machine name.
# Better to filter by name.
processes = DyeingProcess.objects.filter(machine__name='JR 12', start_time__range=(start_range, end_range))

print(f'DyeingProcesses for JR 12 around 2026-08-28 23:31 UTC:')
for p in processes:
    print(f'- ID: {p.id}, Start: {p.start_time}, Has Identity: {hasattr(p, "identity")}')
