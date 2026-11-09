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
from datetime import date

aug29_created = DyeingIdentity.objects.filter(created_at__date=date(2026, 8, 29))
orphans = aug29_created.filter(dyeing_process__isnull=True)

print(f'Total Identities CREATED on Aug 29: {aug29_created.count()}')
print(f'Orphans among them: {orphans.count()}')
