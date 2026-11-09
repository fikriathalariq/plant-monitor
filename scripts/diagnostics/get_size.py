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

from monitoring.models import MachineMinuteLog
from django.db import connection

# Get size of the MachineMinuteLog table
with connection.cursor() as cursor:
    cursor.execute("SELECT pg_total_relation_size('monitoring_machineminutelog');")
    size_bytes = cursor.fetchone()[0]

    cursor.execute("SELECT count(*) FROM monitoring_machineminutelog;")
    count = cursor.fetchone()[0]

print(f"Total MachineMinuteLog Records: {count}")
print(f"Table Size (bytes): {size_bytes}")
if count > 0:
    print(f"Average Size Per Record (bytes): {size_bytes / count:.2f}")

