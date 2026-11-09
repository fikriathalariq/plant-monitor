import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import Machine
for m in Machine.objects.filter(is_active=True).values('code', 'valid_min', 'valid_max', 'temperature'):
    print(m['code'], '|', 'temp:', m['temperature'], '| valid_min:', m['valid_min'], '| valid_max:', m['valid_max'])
