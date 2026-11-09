import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()

from monitoring.models import Machine, MachineMinuteLog

machines = Machine.objects.filter(is_active=True)
updated_count = 0

for m in machines:
    latest_log = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp').first()
    if latest_log:
        current_status = latest_log.thermal_state
        # Find the most recent log where status was different
        diff_log = MachineMinuteLog.objects.filter(machine=m).exclude(thermal_state=current_status).order_by('-timestamp').first()
        
        if diff_log:
            # The status changed in the log immediately after diff_log
            first_new_log = MachineMinuteLog.objects.filter(machine=m, timestamp__gt=diff_log.timestamp).order_by('timestamp').first()
            if first_new_log:
                m.status_changed_at = first_new_log.timestamp
                m.save(update_fields=['status_changed_at'])
                updated_count += 1
        else:
            # If it never changed, just use the oldest log we have
            oldest_log = MachineMinuteLog.objects.filter(machine=m).order_by('timestamp').first()
            if oldest_log:
                m.status_changed_at = oldest_log.timestamp
                m.save(update_fields=['status_changed_at'])
                updated_count += 1

print(f"Successfully backfilled status_changed_at for {updated_count} machines.")
