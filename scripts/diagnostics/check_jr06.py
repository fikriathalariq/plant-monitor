import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from django.db.models import Count, Max, Min

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()

from monitoring.models import Machine, MachineMinuteLog, DyeingProcess

def main():
    try:
        machine = Machine.objects.get(code='JR_06')
        print(f"Machine Found: {machine.name} (Code: {machine.code})")
        
        # Check logs
        log_count = MachineMinuteLog.objects.filter(machine=machine).count()
        print(f"Total MachineMinuteLog: {log_count}")
        
        if log_count > 0:
            agg = MachineMinuteLog.objects.filter(machine=machine).aggregate(
                min_time=Min('timestamp'),
                max_time=Max('timestamp'),
                min_temp=Min('temperature'),
                max_temp=Max('temperature')
            )
            print(f"Log time range: {agg['min_time']} to {agg['max_time']}")
            print(f"Temperature range: {agg['min_temp']} to {agg['max_temp']}")
            
            # Show a few recent logs
            recent_logs = MachineMinuteLog.objects.filter(machine=machine).order_by('-timestamp')[:5]
            print("\nRecent 5 logs:")
            for log in recent_logs:
                print(f" - {log.timestamp}: Temp={log.temperature}, Filtered={log.filtered_temp}, Grad={log.gradient}, State={log.thermal_state}")
                
            # Let's count by thermal_state
            states = MachineMinuteLog.objects.filter(machine=machine).values('thermal_state').annotate(cnt=Count('id'))
            print("\nThermal States distribution:")
            for s in states:
                print(f" - {s['thermal_state']}: {s['cnt']}")
                
        # Check processes
        process_count = DyeingProcess.objects.filter(machine=machine).count()
        print(f"\nTotal DyeingProcess: {process_count}")
        
        if process_count > 0:
            recent_processes = DyeingProcess.objects.filter(machine=machine).order_by('-start_time')[:5]
            print("Recent 5 processes:")
            for p in recent_processes:
                print(f" - Batch {p.batch_number}: {p.start_time} to {p.end_time}, Complete={p.is_complete}")
        
    except Machine.DoesNotExist:
        print("Machine JR_06 not found.")

if __name__ == "__main__":
    main()
