"""
Management command to fix overlapping batches and re-detect correctly.
This addresses the issue where multiple batches overlap in time.

Usage:
    python manage.py fix_overlapping_batches --machine JD_01
    python manage.py fix_overlapping_batches --all
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from monitoring.models import Machine, DyeingProcess
from datetime import timedelta


class Command(BaseCommand):
    help = 'Fix overlapping batches by removing duplicates and re-detecting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--machine',
            type=str,
            help='Machine code to fix (e.g., JD_01)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fix all machines',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        machine_code = options.get('machine')
        fix_all = options.get('all')
        dry_run = options.get('dry_run')

        if not machine_code and not fix_all:
            self.stdout.write(self.style.ERROR('Please specify --machine CODE or --all'))
            return

        # Get machines to process
        if fix_all:
            machines = Machine.objects.all()
        else:
            machines = Machine.objects.filter(code=machine_code)
            if not machines.exists():
                self.stdout.write(self.style.ERROR(f'Machine {machine_code} not found'))
                return

        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('OVERLAPPING BATCH FIX UTILITY'))
        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        total_deleted = 0

        for machine in machines:
            self.stdout.write(f'\n{self.style.HTTP_INFO("►")} Checking: {machine.code} ({machine.name})')
            
            # Get all batches for this machine
            batches = DyeingProcess.objects.filter(machine=machine).order_by('start_time')
            
            if not batches.exists():
                self.stdout.write('  └─ No batches found')
                continue
            
            # Detect overlaps
            overlaps = []
            prev_batch = None
            
            for batch in batches:
                if prev_batch:
                    # Check if current batch starts before previous ends
                    if batch.start_time < prev_batch.end_time:
                        overlaps.append({
                            'prev': prev_batch,
                            'curr': batch
                        })
                prev_batch = batch
            
            if not overlaps:
                self.stdout.write(f'  └─ ✓ No overlaps found ({batches.count()} batches)')
                continue
            
            # Report overlaps
            self.stdout.write(f'  ├─ ⚠️  Found {len(overlaps)} overlap(s):')
            
            for overlap in overlaps:
                prev = overlap['prev']
                curr = overlap['curr']
                
                self.stdout.write(
                    f'  │  ├─ Batch #{prev.batch_number} ({prev.start_time.strftime("%H:%M")} → '
                    f'{prev.end_time.strftime("%H:%M")})'
                )
                self.stdout.write(
                    f'  │  └─ Batch #{curr.batch_number} ({curr.start_time.strftime("%H:%M")} → '
                    f'{curr.end_time.strftime("%H:%M")}) OVERLAPS!'
                )
            
            # Strategy: Delete ALL batches and recommend reprocess
            if dry_run:
                self.stdout.write(
                    f'  └─ [DRY RUN] Would delete {batches.count()} batches'
                )
            else:
                count = batches.count()
                batches.delete()
                total_deleted += count
                self.stdout.write(
                    f'  └─ ✓ Deleted {count} batches (ready for reprocess)'
                )

        # Summary
        self.stdout.write(f'\n{self.style.SUCCESS("="*70)}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes made'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ COMPLETED: {total_deleted} batches deleted'))
            
            if total_deleted > 0:
                self.stdout.write('\n' + self.style.WARNING('NEXT STEPS:'))
                self.stdout.write('Run batch detection to recreate batches correctly:')
                
                if machine_code:
                    self.stdout.write(
                        f'  python manage.py process_batch_history --machine {machine_code}'
                    )
                else:
                    self.stdout.write('  python manage.py process_batch_history')
                    
        self.stdout.write(self.style.SUCCESS("="*70 + '\n'))
