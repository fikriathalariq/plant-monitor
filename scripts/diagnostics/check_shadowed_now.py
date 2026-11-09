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
from django.utils import timezone
from datetime import timedelta, datetime, timezone as tz

now = timezone.now()
target = now - timedelta(minutes=1)
target_min = target.replace(second=0, microsecond=0)

shadowed_codes = list(MachineMinuteLog.objects.filter(timestamp=target_min, data_quality="SHADOWED").values_list("machine__code", flat=True))

print("=== SHADOWED machines at", target_min.strftime("%H:%M"), "===")
print("Count:", len(shadowed_codes))
print("Sample:", shadowed_codes[:5])
