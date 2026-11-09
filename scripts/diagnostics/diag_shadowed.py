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
from monitoring.models import Machine, MachineMinuteLog
from datetime import datetime, timezone as tz
from django.db.models import Count

target = datetime(2026, 9, 3, 9, 24, tzinfo=tz.utc)

shadowed_codes = list(MachineMinuteLog.objects.filter(timestamp=target, data_quality="SHADOWED").values_list("machine__code", flat=True))
normal_codes = list(MachineMinuteLog.objects.filter(timestamp=target, data_quality="NORMAL").values_list("machine__code", flat=True))

print("=== SHADOWED machines (sample 10) ===")
for m in Machine.objects.filter(code__in=shadowed_codes[:10]):
    print(m.code, "temp=", m.temperature, "valid_min=", m.valid_min, "valid_max=", m.valid_max, "mode=", m.operation_mode)

print()
print("=== NORMAL machines (sample 5) ===")
for m in Machine.objects.filter(code__in=normal_codes[:5]):
    print(m.code, "temp=", m.temperature, "valid_min=", m.valid_min, "valid_max=", m.valid_max, "mode=", m.operation_mode)
