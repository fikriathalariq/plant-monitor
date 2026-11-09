import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import sys, os, django
from datetime import datetime, date, timedelta
sys.path.insert(0, r'c:\Users\HP\Documents\Plant-Monitor\plant-monitor')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.utils import timezone

target_date = date(2026, 8, 29)

# Get identities created on Aug 29 or with start_time_snapshot on Aug 29
identities = DyeingIdentity.objects.filter(start_time_snapshot__date=target_date)
print(f'=== Dyeing Identity Data for {target_date} ===')
print(f'Total Identities: {identities.count()}')

orphans = identities.filter(dyeing_process__isnull=True)
print(f'Orphan Identities (no process link): {orphans.count()}')

# Check DyeingProcess for Aug 29
processes = DyeingProcess.objects.filter(start_time__date=target_date)
print(f'\nTotal DyeingProcesses: {processes.count()}')

no_identity = processes.filter(identity__isnull=True)
print(f'Processes WITHOUT Identity: {no_identity.count()}')

# Print details of missing identities
if no_identity.exists():
    print('\nProcesses missing identities:')
    for p in no_identity.order_by('start_time')[:10]:
        print(f'- Process ID: {p.id}, Machine: {p.machine.name}, Start: {p.start_time}')

if orphans.exists():
    print('\nOrphan Identities:')
    for o in orphans.order_by('start_time_snapshot')[:10]:
        print(f'- Identity ID: {o.id}, Batch: {o.no_batch}, Order: {o.no_order}, Start: {o.start_time_snapshot}')

