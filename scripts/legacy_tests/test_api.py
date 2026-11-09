import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess
from monitoring.api_report import get_process_analytics

p = DyeingProcess.objects.filter(machine__code='JR_03', batch_number='397').first()
if p:
    print(f"Process ID for Batch 397: {p.id}")
    data = get_process_analytics(None, p.id)
    print(data['timing'])
else:
    print("Batch 397 not found")
