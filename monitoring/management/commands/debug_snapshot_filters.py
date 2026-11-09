from django.core.management.base import BaseCommand
from monitoring.models import MachineStatusSnapshot, Machine, MachineGroup
from django.utils import timezone
from datetime import datetime
import json


class Command(BaseCommand):
    help = "Debug snapshot filter issues"

    def handle(self, *args, **options):
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"SNAPSHOT FILTER DEBUG")
        self.stdout.write(f"{'='*70}\n")
        
        # 1. Check total snapshots and date range
        total = MachineStatusSnapshot.objects.count()
        self.stdout.write(f"Total Snapshots: {total}")
        
        if total == 0:
            self.stdout.write(self.style.ERROR("No snapshots found!"))
            return
        
        first = MachineStatusSnapshot.objects.order_by('timestamp').first()
        last = MachineStatusSnapshot.objects.order_by('-timestamp').first()
        
        self.stdout.write(f"\nDate Range in Database:")
        self.stdout.write(f"  First: {first.timestamp}")
        self.stdout.write(f"  Last:  {last.timestamp}")
        self.stdout.write(f"  First (date only): {first.timestamp.date()}")
        self.stdout.write(f"  Last (date only):  {last.timestamp.date()}")
        
        # 2. Check today's date (what user might be filtering)
        today = timezone.now().date()
        self.stdout.write(f"\nToday's Date: {today}")
        self.stdout.write(f"Today matches last snapshot date: {today == last.timestamp.date()}")
        
        # 3. Check snapshots for today
        start_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        end_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        
        today_snapshots = MachineStatusSnapshot.objects.filter(
            timestamp__range=(start_today, end_today)
        ).count()
        
        self.stdout.write(f"\nSnapshots for TODAY ({today}): {today_snapshots}")
        
        # 4. Sample a recent snapshot to see machine codes
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("SAMPLE SNAPSHOT DATA:")
        self.stdout.write(f"{'='*70}")
        
        sample = MachineStatusSnapshot.objects.order_by('-timestamp').first()
        if sample:
            self.stdout.write(f"\nSample Timestamp: {sample.timestamp}")
            self.stdout.write(f"Number of machines in snapshot: {len(sample.snapshot_data)}")
            
            # Show all machine codes
            machine_codes = sorted(sample.snapshot_data.keys())
            self.stdout.write(f"\nMachine codes in snapshot:")
            for code in machine_codes:
                data = sample.snapshot_data[code]
                self.stdout.write(f"  - {code}: status={data['status']}, detail={data['detail']}, mode={data['mode']}")
        
        # 5. Check active machines in database
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("ACTIVE MACHINES IN DATABASE:")
        self.stdout.write(f"{'='*70}")
        
        active_machines = Machine.objects.filter(is_active=True)
        self.stdout.write(f"\nTotal Active Machines: {active_machines.count()}")
        
        # Group by operation mode
        auto_count = active_machines.filter(operation_mode='AUTO').count()
        manual_count = active_machines.filter(operation_mode='MANUAL').count()
        
        self.stdout.write(f"  - AUTO: {auto_count}")
        self.stdout.write(f"  - MANUAL: {manual_count}")
        
        # 6. Check machine groups
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("MACHINE GROUPS:")
        self.stdout.write(f"{'='*70}")
        
        groups = MachineGroup.objects.filter(machine__is_active=True).distinct()
        self.stdout.write(f"\nTotal Groups with Active Machines: {groups.count()}")
        
        for group in groups:
            machines_in_group = Machine.objects.filter(group=group, is_active=True).count()
            self.stdout.write(f"  - {group.code} ({group.name}): {machines_in_group} machines")
        
        # 7. Test filter logic
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("TESTING DEFAULT FILTER SCENARIO:")
        self.stdout.write(f"{'='*70}")
        
        # Simulate default filters (what user sees on first load)
        date_from = today
        date_to = today
        interval = 5
        selected_groups = []  # Empty by default
        selected_machines = []  # Empty by default
        
        self.stdout.write(f"\nDefault Filters:")
        self.stdout.write(f"  date_from: {date_from}")
        self.stdout.write(f"  date_to: {date_to}")
        self.stdout.write(f"  interval: {interval}")
        self.stdout.write(f"  selected_groups: {selected_groups or 'None (empty)'}")
        self.stdout.write(f"  selected_machines: {selected_machines or 'None (empty)'}")
        
        # Get machines based on filters (simulate view logic)
        machines_query = Machine.objects.filter(is_active=True)
        if selected_groups:
            machines_query = machines_query.filter(group__code__in=selected_groups)
        if selected_machines:
            machines_query = machines_query.filter(code__in=selected_machines)
        
        machine_list = list(machines_query.order_by('group__code', 'code'))
        
        self.stdout.write(f"\nFiltered Machine List: {len(machine_list)} machines")
        if machine_list:
            self.stdout.write("  Machines:")
            for m in machine_list[:10]:  # Show first 10
                self.stdout.write(f"    - {m.code} ({m.group.code if m.group else 'No Group'})")
            if len(machine_list) > 10:
                self.stdout.write(f"    ... and {len(machine_list) - 10} more")
        
        # Query snapshots with these filters
        start_datetime = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
        
        snapshots = MachineStatusSnapshot.objects.filter(
            timestamp__range=(start_datetime, end_datetime)
        ).order_by('-timestamp')
        
        self.stdout.write(f"\nSnapshots in date range: {snapshots.count()}")
        
        # Apply interval filter
        if interval > 1:
            filtered_snapshots = [
                s for s in snapshots 
                if s.timestamp.minute % interval == 0
            ]
        else:
            filtered_snapshots = list(snapshots)
        
        self.stdout.write(f"After interval filter ({interval} min): {len(filtered_snapshots)}")
        
        # 8. DIAGNOSIS
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(self.style.WARNING("DIAGNOSIS:"))
        self.stdout.write(f"{'='*70}")
        
        if today_snapshots == 0:
            self.stdout.write(self.style.ERROR(
                f"\n❌ PROBLEM: No snapshots for today ({today})"
            ))
            self.stdout.write(f"\nThe snapshot data range is:")
            self.stdout.write(f"  {first.timestamp.date()} to {last.timestamp.date()}")
            self.stdout.write(f"\nSOLUTION:")
            self.stdout.write(f"  Change your filter date range to match the data.")
            self.stdout.write(f"  Use date_from={first.timestamp.date()} and date_to={last.timestamp.date()}")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Snapshots exist for today"
            ))
            
            if len(machine_list) == 0:
                self.stdout.write(self.style.ERROR(
                    f"\n❌ PROBLEM: Machine list is empty after filtering"
                ))
                self.stdout.write(f"\nSOLUTION:")
                self.stdout.write(f"  Make sure you select machine groups or machines in the filter.")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\n✓ Machine list OK ({len(machine_list)} machines)"
                ))
                
            if len(filtered_snapshots) == 0:
                self.stdout.write(self.style.ERROR(
                    f"\n❌ PROBLEM: No snapshots after interval filtering"
                ))
                self.stdout.write(f"\nSOLUTION:")
                self.stdout.write(f"  Change interval to 1 minute, or check data timestamps")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\n✓ Filtered snapshots OK ({len(filtered_snapshots)} snapshots)"
                ))
        
        self.stdout.write(f"\n{'='*70}\n")
