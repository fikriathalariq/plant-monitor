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

from monitoring.models import Machine, MachineGroup

boiler_group = MachineGroup.objects.filter(name__icontains='Boiler').first()
if boiler_group:
    print(f"Group: {boiler_group.name}")
    for m in boiler_group.machine_set.all():
        print(f"- {m.name} (Code: {m.code}), Current Temp/Value: {m.temperature}, Status: {m.status}, Steam: {m.average_steam_usage}")
else:
    print("Boiler group not found")
