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

from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType
from monitoring.models import DyeingIdentity
from datetime import date

ct = ContentType.objects.get_for_model(DyeingIdentity)
for day in range(25, 32):
    d = date(2026, 8, day)
    adds = LogEntry.objects.filter(content_type=ct, action_flag=ADDITION, action_time__date=d).count()
    changes = LogEntry.objects.filter(content_type=ct, action_flag=CHANGE, action_time__date=d).count()
    print(f'Aug {day} - Added: {adds}, Changed: {changes}')
