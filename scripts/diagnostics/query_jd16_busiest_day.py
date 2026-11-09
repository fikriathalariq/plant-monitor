import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime
import pytz
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingProcess, Machine

machine = Machine.objects.filter(code__iexact='JR_12').first()

if not machine:
    print("Machine JR_12 not found!")
    exit(1)

processes = DyeingProcess.objects.filter(
    machine=machine,
    max_temp__gt=120.0,
    is_valid_process=True
)

daily_counts = defaultdict(list)
local_tz = pytz.timezone('Asia/Jakarta')

for p in processes:
    if not p.start_time: continue
    
    local_start = p.start_time.astimezone(local_tz)
    day_str = local_start.strftime('%Y-%m-%d')
    
    local_end = p.end_time.astimezone(local_tz) if p.end_time else None
    
    daily_counts[day_str].append({
        'batch': p.batch_number,
        'start': local_start,
        'end': local_end
    })

if not daily_counts:
    print("No processes found.")
    exit(0)

# Find the day with maximum processes
busiest_day = max(daily_counts.keys(), key=lambda k: len(daily_counts[k]))
busiest_processes = daily_counts[busiest_day]

# Sort processes by start time
busiest_processes.sort(key=lambda x: x['start'])

first_process = busiest_processes[0]
last_process = busiest_processes[-1]

print(f"Busiest Day: {busiest_day}")
print(f"Total Processes: {len(busiest_processes)}")
print(f"First Process Start: {first_process['start'].strftime('%H:%M:%S')}")
if last_process['end']:
    print(f"Last Process End: {last_process['end'].strftime('%H:%M:%S')}")
else:
    print(f"Last Process Start: {last_process['start'].strftime('%H:%M:%S')} (End time not available)")
    
print("\nDetails:")
for p in busiest_processes:
    end_str = p['end'].strftime('%H:%M:%S') if p['end'] else "N/A"
    print(f"Batch {p['batch']}: {p['start'].strftime('%H:%M:%S')} to {end_str}")
