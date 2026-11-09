"""
Management command to fix existing MachineMinuteLog records with invalid temperatures.

This fixes historical data where temperature was invalid ("-", None, 0, NaN) but
filter states (ewma_temp, kalman_x, etc.) were incorrectly calculated.

Usage:
    python manage.py fix_invalid_temp_data
    python manage.py fix_invalid_temp_data --dry-run
    python manage.py fix_invalid_temp_data --machine=JR_04
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from monitoring.models import MachineMinuteLog
from monitoring.utils.gradient_processor import (
    is_invalid_temperature,
    get_filtered_temp_for_invalid
)


class Command(BaseCommand):
    help = "Fix filter state for logs with invalid temperature"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )
        parser.add_argument(
            '--machine',
            type=str,
            help='Only fix logs for specific machine code (e.g., JR_04)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Batch size for bulk updates (default: 500)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        machine_code = options.get('machine')
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("  FIX INVALID TEMPERATURE FILTER STATE"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN MODE - No changes will be made"))
        
        # Build query
        queryset = MachineMinuteLog.objects.all()
        
        if machine_code:
            queryset = queryset.filter(machine__code=machine_code)
            self.stdout.write(f"  Filtering by machine: {machine_code}")
        
        self.stdout.write("-" * 70)
        
        # Get all logs with any filter state value
        # (if filter state is None, it was already cleared)
        logs_to_check = queryset.exclude(
            ewma_temp=None,
            kalman_x=None,
            kalman_p=None
        ).order_by('timestamp')
        
        total_checked = 0
        total_fixed = 0
        batch = []
        
        self.stdout.write(f"\nScanning {logs_to_check.count()} logs with filter states...")
        
        for log in logs_to_check.iterator(chunk_size=1000):
            total_checked += 1
            
            # Check if temperature is actually invalid
            if is_invalid_temperature(log.temperature):
                # This log needs fixing
                old_filtered = log.filtered_temp
                old_ewma = log.ewma_temp
                
                # Apply fix
                log.filtered_temp = get_filtered_temp_for_invalid(log.temperature)
                log.gradient = None
                log.thermal_state = "OFFLINE"  # Invalid data
                log.ewma_temp = None
                log.kalman_x = None
                log.kalman_p = None
                log.ewma_gradient = None
                log.kalman_grad_x = None
                
                if dry_run:
                    self.stdout.write(
                        f"  [{log.machine.code}] {log.timestamp} | "
                        f"temp={log.temperature!r} | "
                        f"filtered: {old_filtered} -> {log.filtered_temp} | "
                        f"ewma: {old_ewma} -> None"
                    )
                else:
                    batch.append(log)
                
                total_fixed += 1
                
                # Bulk update batch
                if not dry_run and len(batch) >= batch_size:
                    self._bulk_update(batch)
                    self.stdout.write(f"  Updated {total_fixed} records...")
                    batch = []
        
        # Update remaining batch
        if not dry_run and batch:
            self._bulk_update(batch)
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS(f"  TOTAL CHECKED: {total_checked} records"))
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"  WOULD FIX:     {total_fixed} records"))
            self.stdout.write("\n  Run without --dry-run to apply changes")
        else:
            self.stdout.write(self.style.SUCCESS(f"  TOTAL FIXED:   {total_fixed} records"))
        
        self.stdout.write("=" * 70)

    def _bulk_update(self, logs):
        """Bulk update logs with corrected data."""
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
                    'ewma_gradient',
                    'kalman_grad_x',
                ],
                batch_size=100,
            )
