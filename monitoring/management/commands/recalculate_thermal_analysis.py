"""
Management command to recalculate thermal analysis for Machine Minute Logs in bulk.
Optimized for processing large datasets (100k+ rows) efficiently.

Usage:
    # Recalculate ALL data
    python manage.py recalculate_thermal_analysis
    
    # Recalculate for specific machine
    python manage.py recalculate_thermal_analysis --machine ZET_01
    
    # Recalculate for date range
    python manage.py recalculate_thermal_analysis --start-date 2025-11-01 --end-date 2025-11-30
    
    # Recalculate for multiple machines
    python manage.py recalculate_thermal_analysis --machine ZET_01 --machine ZET_02
    
    # Dry run (show what would be processed)
    python manage.py recalculate_thermal_analysis --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from monitoring.models import Machine, MachineMinuteLog
from monitoring.utils.gradient_processor import GradientProcessor, FilterState, ProcessingConfig


class Command(BaseCommand):
    help = 'Recalculate thermal analysis (gradient, thermal_state) for Machine Minute Logs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--machine',
            action='append',
            help='Machine code(s) to process (can specify multiple times)',
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=20000,
            help='Number of records to process per batch (default: 20000)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing',
        )

    def handle(self, *args, **options):
        machine_codes = options.get('machine')
        start_date_str = options.get('start_date')
        end_date_str = options.get('end_date')
        batch_size = options.get('batch_size')
        dry_run = options.get('dry_run')

        # Build queryset filters
        filters = {}
        
        if machine_codes:
            machines = Machine.objects.filter(code__in=machine_codes)
            if not machines.exists():
                self.stdout.write(self.style.ERROR(f'No machines found with codes: {machine_codes}'))
                return
            filters['machine__in'] = machines
            machine_names = ', '.join([m.code for m in machines])
        else:
            machines = Machine.objects.filter(is_active=True)
            machine_names = 'ALL active machines'

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date)
                filters['timestamp__gte'] = start_date
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid start-date format. Use YYYY-MM-DD'))
                return

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date) + timedelta(days=1)
                filters['timestamp__lt'] = end_date
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid end-date format. Use YYYY-MM-DD'))
                return

        # Get total count
        total_count = MachineMinuteLog.objects.filter(**filters).count()

        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('THERMAL ANALYSIS RECALCULATION'))
        self.stdout.write(self.style.WARNING('='*70))
        self.stdout.write(f'Machines: {machine_names}')
        if start_date_str:
            self.stdout.write(f'Start Date: {start_date_str}')
        if end_date_str:
            self.stdout.write(f'End Date: {end_date_str}')
        self.stdout.write(f'Total Records: {total_count:,}')
        self.stdout.write(f'Batch Size: {batch_size:,}')
        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        if dry_run:
            self.stdout.write(self.style.SUCCESS('DRY RUN - No changes will be made'))
            return

        # Process each machine separately to maintain filter state continuity
        config = ProcessingConfig()
        total_processed = 0

        for machine in machines:
            self.stdout.write(f'\n{self.style.HTTP_INFO("►")} Processing: {machine.code} ({machine.name})')
            
            # Get logs for this machine
            machine_filters = {'machine': machine}
            if 'timestamp__gte' in filters:
                machine_filters['timestamp__gte'] = filters['timestamp__gte']
            if 'timestamp__lt' in filters:
                machine_filters['timestamp__lt'] = filters['timestamp__lt']
            
            logs = MachineMinuteLog.objects.filter(**machine_filters).order_by('timestamp')
            count = logs.count()
            
            if count == 0:
                self.stdout.write(f'  └─ No logs found, skipping')
                continue
            
            self.stdout.write(f'  ├─ Found {count:,} logs')
            
            # Process in batches
            processor = GradientProcessor(config)
            
            # IMPORTANT: Single filter state for entire machine - NOT reset between batches!
            # This ensures filter continuity (EWMA, Kalman) across all records
            state = FilterState()  # Fresh state for this machine
            prev_timestamp = None
            
            processed = 0
            
            # NO BULK - Individual save() per record
            chunk_size_iterator = 10000  # Large chunk for fast DB read
            
            # Use iterator for memory efficiency
            for log in logs.iterator(chunk_size=chunk_size_iterator):
                # Calculate dt
                if prev_timestamp:
                    dt_minutes = (log.timestamp - prev_timestamp).total_seconds() / 60.0
                    dt_minutes = max(0.5, min(dt_minutes, 10.0))
                else:
                    dt_minutes = 1.0
                
                # Process - state is updated and carried forward to next record
                filtered, gradient, thermal_state, state = processor.process_single(
                    raw_temp=log.temperature,
                    state=state,
                    dt_minutes=dt_minutes
                )
                
                # Update log object
                log.filtered_temp = filtered
                log.gradient = round(gradient, 4) if gradient is not None else None
                log.thermal_state = thermal_state
                log.ewma_temp = state.ewma_temp
                log.kalman_x = state.kalman_x
                log.kalman_p = state.kalman_p
                log.ewma_gradient = state.ewma_gradient
                log.kalman_grad_x = state.kalman_grad_x
                
                # Individual save (NO BULK)
                log.save(update_fields=[
                    'filtered_temp', 'gradient', 'thermal_state',
                    'ewma_temp', 'kalman_x', 'kalman_p',
                    'ewma_gradient', 'kalman_grad_x'
                ])
                
                prev_timestamp = log.timestamp
                processed += 1
                total_processed += 1
                
                # Progress update every 100 records
                if processed % 100 == 0:
                    percent = (processed / count) * 100
                    self.stdout.write(
                        f'  ├─ Progress: {processed:,}/{count:,} ({percent:.1f}%) - '
                        f'Total processed: {total_processed:,}',
                        ending='\r'
                    )
                    self.stdout.flush()

            
            self.stdout.write(f'  └─ ✓ Completed: {processed:,} logs processed' + ' '*20)

        # Summary
        self.stdout.write(f'\n{self.style.SUCCESS("="*70)}')
        self.stdout.write(self.style.SUCCESS(f'✓ COMPLETED: {total_processed:,} records recalculated'))
        self.stdout.write(
            '\nSnapshot History (timeline) membaca langsung dari MachineMinuteLog — '
            'cukup restart Waitress + refresh halaman.\n'
            'Untuk halaman pivot lama yang pakai MachineStatusSnapshot, jalankan:\n'
            '  python manage.py backfill_snapshots --days 30\n'
        )
        self.stdout.write(self.style.SUCCESS("="*70 + '\n'))
