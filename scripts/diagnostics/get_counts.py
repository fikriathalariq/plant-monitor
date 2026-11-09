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

from monitoring.models import Machine, MachineMinuteLog

total = Machine.objects.count()
active_auto = Machine.objects.filter(operation_mode='AUTO', is_active=True).count()
active_manual = Machine.objects.filter(operation_mode='MANUAL', is_active=True).count()

print(f"Total Machines: {total}")
print(f"Active AUTO Machines: {active_auto}")
print(f"Active MANUAL Machines: {active_manual}")
