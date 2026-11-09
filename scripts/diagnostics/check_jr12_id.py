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

from monitoring.models import DyeingProcess, DyeingIdentity

p = DyeingProcess.objects.get(id=3203270)
if hasattr(p, 'identity'):
    print(f'Identity ID: {p.identity.id}, Jenis: {p.identity.jenis_proses}')
    print(f'Orphan status of 3706: {DyeingIdentity.objects.get(id=3706).dyeing_process_id}')
