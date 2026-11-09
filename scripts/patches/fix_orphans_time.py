import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from datetime import timedelta

# Fix orphaned DyeingIdentities
orphans = DyeingIdentity.objects.filter(dyeing_process__isnull=True)
count = 0
relinked_count = 0
for o in orphans:
    if o.start_time_snapshot:
        o.start_time_snapshot += timedelta(hours=7)
        o.save(update_fields=['start_time_snapshot'])
        count += 1
        
        # Try to relink right away
        match = DyeingProcess.objects.filter(
            machine=o.machine,
            start_time__range=(
                o.start_time_snapshot - timedelta(minutes=15),
                o.start_time_snapshot + timedelta(minutes=15)
            )
        ).first()
        if match:
            o.dyeing_process = match
            o.save(update_fields=['dyeing_process'])
            relinked_count += 1

print(f"Fixed {count} orphans' times, successfully relinked {relinked_count} of them.")
