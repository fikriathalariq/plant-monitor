"""
Management command to check for duplicate/overlapping data in MachineMinuteLog.
Useful for diagnosing batch detection issues.

Usage:
    python manage.py check_duplicate_logs --machine JD_01
    python manage.py check_duplicate_logs --machine JD_01 --start-date 2025-12-16 --end-date 2025-12-17
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from monitoring.models import Machine, MachineMinuteLog
from datetime import datetime
from django.utils import timezone


class Command(BaseCommand):
    help = 'Check for duplicate timestamps in MachineMinuteLog'

    def add_arguments(self, parser):
        parser.add_argument(
            '--machine',
            type=str,
            required=True,
            help='Machine code to check (e.g., JD_01)',
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

    def handle(self, *args, **options):
        machine_code = options['machine']
        start_date_str = options.get('start_date')
        end_date_str = options.get('end_date')

        # Get machine
        try:
            machine = Machine.objects.get(code=machine_code)
        except Machine.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Machine {machine_code} not found'))
            return

        # Build filters
        filters = {'machine': machine}
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            filters['timestamp__gte'] = timezone.make_aware(start_date)
        
        if end_date_str:
            from datetime import timedelta
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            filters['timestamp__lt'] = timezone.make_aware(end_date)

        # Header
        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('DUPLICATE TIMESTAMP CHECK'))
        self.stdout.write(self.style.WARNING('='*70))
        self.stdout.write(f'Machine: {machine.code} ({machine.name})')
        if start_date_str:
            self.stdout.write(f'Start Date: {start_date_str}')
        if end_date_str:
            self.stdout.write(f'End Date: {end_date_str}')
        self.stdout.write('='*70 + '\n')

        # Find duplicates
        duplicates = MachineMinuteLog.objects.filter(**filters).values('timestamp').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('timestamp')

        total_logs = MachineMinuteLog.objects.filter(**filters).count()

        if not duplicates.exists():
            self.stdout.write(self.style.SUCCESS(f'✓ No duplicates found! ({total_logs:,} total logs)'))
            return

        # Report duplicates
        duplicate_count = duplicates.count()
        self.stdout.write(
            self.style.ERROR(f'⚠️  Found {duplicate_count} timestamps with duplicates:')
        )
        self.stdout.write('')

        for dup in duplicates[:50]:  # Show max 50
            timestamp = dup['timestamp']
            count = dup['count']
            
            # Get the actual duplicate records
            records = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp=timestamp
            ).values('id', 'temperature', 'filtered_temp', 'thermal_state')

            self.stdout.write(
                f"  {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {count} records:"
            )
            
            for rec in records:
                self.stdout.write(
                    f"    ID: {rec['id']}, Temp: {rec['temperature']}, "
                    f"Filtered: {rec['filtered_temp']}, State: {rec['thermal_state']}"
                )
            self.stdout.write('')

        if duplicate_count > 50:
            self.stdout.write(f'  ... and {duplicate_count - 50} more duplicates')

        # Summary
        total_duplicate_records = sum(d['count'] for d in duplicates)
        self.stdout.write('\n' + self.style.WARNING('='*70))
        self.stdout.write(self.style.WARNING('SUMMARY'))
        self.stdout.write(self.style.WARNING('='*70))
        self.stdout.write(f'Total Logs: {total_logs:,}')
        self.stdout.write(f'Unique Timestamps with Duplicates: {duplicate_count}')
        self.stdout.write(f'Total Duplicate Records: {total_duplicate_records:,}')
        
        # Recommendation
        self.stdout.write('\n' + self.style.WARNING('RECOMMENDATION:'))
        self.stdout.write('If duplicates exist, you should:')
        self.stdout.write('1. Identify the source (multiple imports? processing errors?)')
        self.stdout.write('2. Delete duplicate records')
        self.stdout.write('3. Re-run batch detection with --reprocess')
        
        # Show command to delete duplicates
        self.stdout.write('\n' + self.style.WARNING('TO DELETE DUPLICATES:'))
        self.stdout.write('Create a management command to keep only the first record per timestamp.')
        self.stdout.write(self.style.WARNING('='*70 + '\n'))
