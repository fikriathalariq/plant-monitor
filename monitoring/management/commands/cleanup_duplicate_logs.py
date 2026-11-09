"""
Management command to clean up duplicate timestamps in MachineMinuteLog.
Keeps the record with valid temperature and deletes invalid duplicates.

Usage:
    # Dry run (show what would be deleted)
    python manage.py cleanup_duplicate_logs --machine JD_01 --dry-run
    
    # Clean specific date range
    python manage.py cleanup_duplicate_logs --machine JD_01 --start-date 2025-12-16 --end-date 2025-12-17
    
    # Clean all duplicates for machine
    python manage.py cleanup_duplicate_logs --machine JD_01
    
    # Clean all machines
    python manage.py cleanup_duplicate_logs --all
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from monitoring.models import Machine, MachineMinuteLog
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Clean up duplicate timestamps by keeping valid temperature records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--machine',
            type=str,
            help='Machine code to clean (e.g., JD_01)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clean all machines',
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        machine_code = options.get('machine')
        all_machines = options.get('all')
        start_date_str = options.get('start_date')
        end_date_str = options.get('end_date')
        dry_run = options.get('dry_run')

        if not machine_code and not all_machines:
            self.stdout.write(self.style.ERROR('Please specify --machine CODE or --all'))
            return

        # Get machines
        if all_machines:
            machines = Machine.objects.all()
        else:
            try:
                machines = [Machine.objects.get(code=machine_code)]
            except Machine.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Machine {machine_code} not found'))
                return

        # Header
        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('DUPLICATE CLEANUP UTILITY'))
        self.stdout.write(self.style.WARNING('='*70))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        self.stdout.write('='*70 + '\n')

        total_deleted = 0

        for machine in machines:
            self.stdout.write(f'\n{self.style.HTTP_INFO("►")} Processing: {machine.code} ({machine.name})')
            
            # Build filters
            filters = {'machine': machine}
            
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                filters['timestamp__gte'] = timezone.make_aware(start_date)
            
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
                filters['timestamp__lt'] = timezone.make_aware(end_date)

            # Find duplicates
            duplicates = MachineMinuteLog.objects.filter(**filters).values('timestamp').annotate(
                count=Count('id')
            ).filter(count__gt=1).order_by('timestamp')

            if not duplicates.exists():
                self.stdout.write('  └─ No duplicates found')
                continue

            self.stdout.write(f'  ├─ Found {duplicates.count()} timestamps with duplicates')
            
            deleted_count = 0
            
            for dup in duplicates:
                timestamp = dup['timestamp']
                
                # Get all records for this timestamp
                records = list(MachineMinuteLog.objects.filter(
                    machine=machine,
                    timestamp=timestamp
                ).order_by('-temperature'))  # Valid temps first (None sorts last)
                
                if len(records) < 2:
                    continue
                
                # Strategy: Keep the record with valid temperature
                # If multiple valid, keep the first one (older ID)
                # If all invalid, keep the first one
                
                records_with_temp = [r for r in records if r.temperature is not None and r.temperature > 0]
                
                if records_with_temp:
                    # Keep the first valid temperature record
                    keep_record = records_with_temp[0]
                else:
                    # All invalid, keep first record
                    keep_record = records[0]
                
                # Delete the rest
                to_delete = [r for r in records if r.id != keep_record.id]
                
                if to_delete:
                    if dry_run:
                        self.stdout.write(
                            f'  │  {timestamp.strftime("%Y-%m-%d %H:%M:%S")} - '
                            f'Would keep ID:{keep_record.id} (Temp:{keep_record.temperature}), '
                            f'delete {len(to_delete)} duplicate(s)'
                        )
                    else:
                        for rec in to_delete:
                            rec.delete()
                        deleted_count += len(to_delete)
            
            if not dry_run and deleted_count > 0:
                self.stdout.write(f'  └─ ✓ Deleted {deleted_count} duplicate records')
                total_deleted += deleted_count
            elif dry_run:
                self.stdout.write(f'  └─ Would delete {deleted_count} duplicate records')

        # Summary
        self.stdout.write(f'\n{self.style.SUCCESS("="*70)}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes made'))
            self.stdout.write(f'Would delete: {total_deleted} duplicate records')
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ COMPLETED: {total_deleted} duplicate records deleted'))
            
            if total_deleted > 0:
                self.stdout.write('\n' + self.style.WARNING('NEXT STEPS:'))
                self.stdout.write('1. Verify data looks correct')
                self.stdout.write('2. Re-run thermal analysis recalculation:')
                if machine_code:
                    self.stdout.write(f'   python manage.py recalculate_thermal_analysis --machine {machine_code}')
                self.stdout.write('3. Re-run batch detection:')
                if machine_code:
                    self.stdout.write(f'   python manage.py process_batch_history --machine {machine_code} --reprocess')
                
        self.stdout.write(self.style.SUCCESS("="*70 + '\n'))
