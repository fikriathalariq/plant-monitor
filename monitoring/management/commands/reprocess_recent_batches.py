"""
Script to reprocess last 5 completed batches per machine.
Finds the 5th-to-last batch for each machine and reprocesses from that start time.
"""

from django.core.management.base import BaseCommand
from monitoring.models import Machine, DyeingProcess
from django.utils import timezone


class Command(BaseCommand):
    help = "Reprocess last 5 completed batches per machine using validated batch detection"

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("  REPROCESS LAST 5 BATCHES PER MACHINE")
        self.stdout.write("=" * 60)
        
        # Get all AUTO machines only (MANUAL machines don't have batches)
        machines = Machine.objects.filter(operation_mode="AUTO")
        
        reprocess_times = {}
        
        for machine in machines:
            self.stdout.write(f"\n[{machine.code}] Analyzing batches...")
            
            # Get last 5 completed batches
            completed_batches = list(DyeingProcess.objects.filter(
                machine=machine,
                is_complete=True
            ).order_by('-start_time')[:5])
            
            batch_count = len(completed_batches)
            
            if batch_count == 0:
                self.stdout.write(f"  → No completed batches found. Skipping.")
                continue
            
            if batch_count < 5:
                self.stdout.write(
                    self.style.WARNING(
                        f"  → Only {batch_count} completed batches found (expected 5)"
                    )
                )
            
            # Get the 5th last batch (or oldest available)
            fifth_last = completed_batches[-1]  # Last item in list
            reprocess_times[machine.code] = fifth_last.start_time
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"  → Found {batch_count} batches. Oldest: Batch #{fifth_last.batch_number} "
                    f"at {fifth_last.start_time.strftime('%Y-%m-%d %H:%M')}"
                )
            )
        
        if not reprocess_times:
            self.stdout.write(
                self.style.WARNING("\nNo machines with batches to reprocess. Exiting.")
            )
            return
        
        # Display reprocessing plan
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  REPROCESSING PLAN")
        self.stdout.write("=" * 60)
        
        for machine_code, start_time in reprocess_times.items():
            self.stdout.write(
                f"{machine_code:10} → from {start_time.strftime('%Y-%m-%d %H:%M')}"
            )
        
        # Confirm before proceeding
        self.stdout.write("\n" + self.style.WARNING("⚠ WARNING: This will delete and regenerate batches!"))
        confirm = input("\nProceed with reprocessing? (yes/no): ")
        
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR("Aborted by user."))
            return
        
        # Execute reprocessing for each machine
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("  EXECUTING REPROCESSING")
        self.stdout.write("=" * 60)
        
        for machine in machines:
            if machine.code not in reprocess_times:
                continue
            
            start_time = reprocess_times[machine.code]
            start_date_str = start_time.strftime('%Y-%m-%d')
            
            self.stdout.write(f"\n[{machine.code}] Reprocessing from {start_date_str}...")
            
            # Import and call process_batch_history command
            from monitoring.management.commands.process_batch_history import Command as ProcessCommand
            
            process_cmd = ProcessCommand()
            process_cmd.stdout = self.stdout
            process_cmd.style = self.style
            
            # Call with --reprocess flag and date range
            process_cmd.handle(
                machine=machine.code,
                reprocess=True,
                start_date=start_date_str,
                end_date=None  # Up to now
            )
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("  ✓ REPROCESSING COMPLETE"))
        self.stdout.write("=" * 60)
        
        # Show summary of new batches
        self.stdout.write("\nNew batch counts:")
        for machine in machines:
            if machine.code not in reprocess_times:
                continue
            
            start_time = reprocess_times[machine.code]
            new_batch_count = DyeingProcess.objects.filter(
                machine=machine,
                start_time__gte=start_time
            ).count()
            
            self.stdout.write(f"  {machine.code:10} → {new_batch_count} batches")
