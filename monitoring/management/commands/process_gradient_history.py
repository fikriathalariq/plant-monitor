"""
Management command to process historical temperature data and calculate gradients.

Usage:
    python manage.py process_gradient_history
    python manage.py process_gradient_history --machine=ZET_01
    python manage.py process_gradient_history --since=2024-12-01
    python manage.py process_gradient_history --reprocess
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta

from monitoring.models import Machine, MachineMinuteLog
from monitoring.utils.gradient_processor import (
    GradientProcessor,
    FilterState,
    ProcessingConfig,
)


class Command(BaseCommand):
    help = "Process historical temperature data to calculate filtered gradients and thermal states."

    def add_arguments(self, parser):
        parser.add_argument(
            '--machine',
            type=str,
            help='Process only specific machine code (e.g., ZET_01)',
        )
        parser.add_argument(
            '--since',
            type=str,
            help='Process data since date (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Process last N hours of data (default: 24)',
        )
        parser.add_argument(
            '--reprocess',
            action='store_true',
            help='Reprocess all data even if already processed',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Batch size for database updates (default: 500)',
        )

    def handle(self, *args, **options):
        machine_code = options.get('machine')
        since_str = options.get('since')
        hours = options.get('hours')
        reprocess = options.get('reprocess')
        batch_size = options.get('batch_size')

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  GRADIENT HISTORY PROCESSOR"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # Determine time filter
        if since_str:
            try:
                since_date = datetime.strptime(since_str, "%Y-%m-%d")
                since_dt = timezone.make_aware(since_date)
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid date format: {since_str}. Use YYYY-MM-DD."))
                return
        else:
            since_dt = timezone.now() - timedelta(hours=hours)

        self.stdout.write(f"  Processing data since: {since_dt}")

        # Get machines to process
        if machine_code:
            machines = Machine.objects.filter(code=machine_code, is_active=True)
            if not machines.exists():
                self.stdout.write(self.style.ERROR(f"Machine '{machine_code}' not found."))
                return
        else:
            machines = Machine.objects.filter(is_active=True, operation_mode="AUTO")

        self.stdout.write(f"  Machines to process: {machines.count()}")
        self.stdout.write("-" * 60)

        # Initialize processor
        config = ProcessingConfig()
        processor = GradientProcessor(config)

        total_processed = 0
        total_updated = 0

        for machine in machines:
            self.stdout.write(f"\n[{machine.code}] {machine.name}")

            # Query logs
            logs_qs = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__gte=since_dt,
            ).order_by('timestamp')

            if not reprocess:
                # Only process unprocessed records
                logs_qs = logs_qs.filter(filtered_temp__isnull=True)

            logs = list(logs_qs)
            log_count = len(logs)

            if log_count == 0:
                self.stdout.write(self.style.WARNING(f"  -> No data to process"))
                continue

            self.stdout.write(f"  -> Found {log_count} records")

            # Initialize filter state
            # Try to get previous state from last processed record
            prev_record = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__lt=since_dt,
                filtered_temp__isnull=False,
            ).order_by('-timestamp').first()

            if prev_record and not reprocess:
                state = FilterState(
                    last_valid_temp=prev_record.filtered_temp,
                    ewma_temp=prev_record.ewma_temp,
                    kalman_x=prev_record.kalman_x,
                    kalman_p=prev_record.kalman_p,
                    last_thermal_state=prev_record.thermal_state or "OFF",
                    state_since_minutes=0.0,
                )
                self.stdout.write(f"  -> Resumed from previous state (T={prev_record.filtered_temp:.1f}C)")
            else:
                state = FilterState()
                self.stdout.write(f"  -> Starting fresh filter state")

            # Process each log
            prev_timestamp = None
            updates = []

            for i, log in enumerate(logs):
                # Use centralized helper for validation
                from monitoring.utils.gradient_processor import (
                    is_invalid_temperature, get_filtered_temp_for_invalid
                )
                
                # Skip filter state calculation for invalid temperature
                if is_invalid_temperature(log.temperature):
                    # Set filtered_temp to "-" if raw was "-", else None
                    log.filtered_temp = get_filtered_temp_for_invalid(log.temperature)
                    log.gradient = None
                    log.thermal_state = "OFFLINE"  # Invalid data
                    # Clear filter states - don't calculate!
                    log.ewma_temp = None
                    log.kalman_x = None
                    log.kalman_p = None
                    updates.append(log)
                    prev_timestamp = log.timestamp
                    continue
                
                # Calculate dt for valid temperature
                if prev_timestamp is not None:
                    dt_seconds = (log.timestamp - prev_timestamp).total_seconds()
                    dt_minutes = max(0.5, min(dt_seconds / 60.0, 10.0))
                else:
                    dt_minutes = 1.0

                # Process valid temperature
                filtered_temp, gradient, thermal_state, state = processor.process_single(
                    raw_temp=log.temperature,
                    state=state,
                    dt_minutes=dt_minutes,
                )

                # Prepare update
                log.filtered_temp = filtered_temp
                log.gradient = round(gradient, 4) if gradient is not None else None
                log.thermal_state = thermal_state
                log.ewma_temp = state.ewma_temp
                log.kalman_x = state.kalman_x
                log.kalman_p = state.kalman_p

                updates.append(log)
                prev_timestamp = log.timestamp

                # Batch save
                if len(updates) >= batch_size:
                    self._bulk_update(updates)
                    total_updated += len(updates)
                    updates = []
                    self.stdout.write(f"  -> Processed {i + 1}/{log_count} records...")

            # Final batch
            if updates:
                self._bulk_update(updates)
                total_updated += len(updates)

            total_processed += log_count

            # Summary for this machine
            state_counts = {}
            for log in logs:
                s = log.thermal_state or "UNKNOWN"
                state_counts[s] = state_counts.get(s, 0) + 1

            state_summary = ", ".join([f"{k}: {v}" for k, v in state_counts.items()])
            self.stdout.write(self.style.SUCCESS(f"  [OK] Completed. States: {state_summary}"))
            
            # Update Machine with final thermal_state from last log
            if logs:
                from monitoring.utils.gradient_processor import get_machine_status
                final_thermal_state = logs[-1].thermal_state
                final_status = get_machine_status(final_thermal_state)
                
                if machine.last_thermal_status != final_thermal_state:
                    machine.last_thermal_status = final_thermal_state
                    machine.last_status = final_status  # Auto-derived
                    machine.last_update = timezone.now()
                    machine.save(update_fields=['last_thermal_status', 'last_status', 'last_update'])
                    self.stdout.write(
                        f"  -> Machine updated: thermal={final_thermal_state}, "
                        f"status={final_status}"
                    )

        # Final summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"  TOTAL PROCESSED: {total_processed} records"))
        self.stdout.write(self.style.SUCCESS(f"  TOTAL UPDATED:   {total_updated} records"))
        self.stdout.write("=" * 60)

    def _bulk_update(self, logs):
        """Bulk update logs with processed data."""
        with transaction.atomic():
            MachineMinuteLog.objects.bulk_update(
                logs,
                fields=[
                    'filtered_temp',
                    'gradient',
                    'thermal_state',
                    'ewma_temp',
                    'kalman_x',
                    'kalman_p',
                ],
                batch_size=100,
            )
