import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import csv
from datetime import datetime
import pytz
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import Machine, MachineMinuteLog, DyeingProcess, DyeingIdentity

# Output file path
output_file = 'dyeing_process_logs_2026.csv'

def export_data():
    tz = pytz.timezone('Asia/Jakarta')
    start_date = tz.localize(datetime(2026, 5, 20))
    
    # 1. Fetch processes
    processes = DyeingProcess.objects.filter(start_time__gte=start_date).select_related('machine')
    print(f"Found {processes.count()} processes since {start_date}")
    
    if processes.count() == 0:
        return
        
    # Get all Steam_Pr logs to map easily
    steam_machine = Machine.objects.filter(code='Steam_Pr').first()
    steam_logs = {}
    if steam_machine:
        print("Fetching Steam_Pr logs...")
        for log in MachineMinuteLog.objects.filter(machine=steam_machine, timestamp__gte=start_date).values('timestamp', 'temperature'):
            # timestamp is datetime, we map by truncating to minute
            ts_min = log['timestamp'].replace(second=0, microsecond=0)
            steam_logs[ts_min] = log['temperature']
    
    # We will write row by row
    total_rows = 0
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Machine Code', 'Batch Number', 'Batch Identity', 'Temperature (C)', 'Pressure Steam (Bar)'])
        
        for idx, process in enumerate(processes):
            machine = process.machine
            start_t = process.start_time
            end_t = process.end_time or timezone.now()
            
            # Identity batch
            try:
                identity = process.identity
                batch_id = identity.batch if identity else "-"
            except Exception:
                batch_id = "-"
                
            batch_num = process.batch_number
            
            # Fetch logs for this machine within the window
            logs = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__gte=start_t,
                timestamp__lte=end_t
            ).order_by('timestamp')
            
            for log in logs:
                ts_min = log.timestamp.replace(second=0, microsecond=0)
                steam_pressure = steam_logs.get(ts_min, "")
                writer.writerow([
                    log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    machine.code,
                    batch_num,
                    batch_id,
                    log.temperature,
                    steam_pressure
                ])
                total_rows += 1
                
            if (idx + 1) % 10 == 0:
                print(f"Processed {idx + 1}/{processes.count()} batches... (Written {total_rows} rows)")
                
    print(f"Export complete! Total rows written: {total_rows}")
    print(f"File saved to {os.path.abspath(output_file)}")

if __name__ == '__main__':
    export_data()
