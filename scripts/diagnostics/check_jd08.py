import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()
from monitoring.models import MachineMinuteLog

logs = MachineMinuteLog.objects.filter(machine__code="JD_08").order_by("-timestamp")[:10]
for log in logs:
    print(log.timestamp.strftime("%H:%M"), "dq=", log.data_quality, "temp=", log.temperature, "filtered=", log.filtered_temp, "status=", log.thermal_state)
