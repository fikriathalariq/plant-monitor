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
from monitoring.models import Machine
from monitoring.utils.signal_freshness import is_signal_stale
from django.utils import timezone

now = timezone.now()
stale_count = 0
not_stale = 0
for m in Machine.objects.filter(is_active=True, operation_mode="AUTO"):
    if is_signal_stale(m, now=now):
        stale_count += 1
    else:
        not_stale += 1

print("AUTO machines - stale:", stale_count, "| not_stale:", not_stale)

# Sample some stale ones
print()
for m in Machine.objects.filter(is_active=True, operation_mode="AUTO"):
    stale = is_signal_stale(m, now=now)
    print(m.code, "stale=", stale, "last_valid_reading_at=", m.last_valid_reading_at)
    if not stale:
        break
