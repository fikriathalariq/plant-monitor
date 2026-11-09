from django.core.management.base import BaseCommand
from monitoring.models import MachineStatusSnapshot, Machine


class Command(BaseCommand):
    help = "Check if snapshot data exists and show basic statistics"

    def handle(self, *args, **options):
        total_snapshots = MachineStatusSnapshot.objects.count()
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"SNAPSHOT DATA DIAGNOSTIC")
        self.stdout.write(f"{'='*60}\n")
        
        self.stdout.write(f"Total Snapshots in Database: {total_snapshots}")
        
        if total_snapshots == 0:
            self.stdout.write(self.style.WARNING(
                "\n⚠️  NO SNAPSHOT DATA FOUND!"
            ))
            self.stdout.write("\nPossible reasons:")
            self.stdout.write("  1. log_minute_history command is not running")
            self.stdout.write("  2. The command was recently started (wait 1 minute)")
            self.stdout.write("  3. There was an error creating snapshots")
            self.stdout.write("\nSolution:")
            self.stdout.write("  1. Check if log_minute_history is running")
            self.stdout.write("  2. Run: python manage.py backfill_snapshots")
            self.stdout.write("     (to create snapshots from existing logs)")
        else:
            # Show date range
            first = MachineStatusSnapshot.objects.order_by('timestamp').first()
            last = MachineStatusSnapshot.objects.order_by('-timestamp').first()
            
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Snapshot data exists!"
            ))
            self.stdout.write(f"\nDate Range:")
            self.stdout.write(f"  First: {first.timestamp}")
            self.stdout.write(f"  Last:  {last.timestamp}")
            
            # Check recent snapshot
            if last:
                import json
                self.stdout.write(f"\nMost Recent Snapshot:")
                self.stdout.write(f"  Timestamp: {last.timestamp}")
                self.stdout.write(f"  Machines in snapshot: {len(last.snapshot_data)}")
                
                # Show sample data
                sample_keys = list(last.snapshot_data.keys())[:3]
                self.stdout.write(f"\n  Sample data (first 3 machines):")
                for key in sample_keys:
                    data = last.snapshot_data[key]
                    self.stdout.write(f"    {key}: {json.dumps(data, indent=6)}")
        
        # Check active machines
        active_machines = Machine.objects.filter(is_active=True).count()
        self.stdout.write(f"\nActive Machines: {active_machines}")
        
        self.stdout.write(f"\n{'='*60}\n")
