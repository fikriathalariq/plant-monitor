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

for day in range(25, 32):
    d = date(2026, 8, day)
    c = DyeingIdentity.objects.filter(created_at__date=d).count()
    print(f'Aug {day}: {c} identities created')
