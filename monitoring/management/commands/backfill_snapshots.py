from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import MachineStatusSnapshot, Machine, MachineMinuteLog
from datetime import timedelta
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill snapshot data from existing MachineMinuteLog entries"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to backfill (default: 7)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=1,
            help='Snapshot interval in minutes (default: 1 = every minute)'
        )

    def handle(self, *args, **options):
        days = options['days']
        interval = options['interval']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"BACKFILLING SNAPSHOTS")
        self.stdout.write(f"{'='*60}\n")
        self.stdout.write(f"Days to backfill: {days}")
        self.stdout.write(f"Snapshot interval: {interval} minute(s)")
        
        # Calculate date range
        end_time = timezone.now()
        start_time = end_time - timedelta(days=days)
        
        self.stdout.write(f"Date range: {start_time} to {end_time}\n")
        
        # Get all active machines
        machines = list(Machine.objects.filter(is_active=True))
        self.stdout.write(f"Active machines: {len(machines)}\n")
        
        if not machines:
            self.stdout.write(self.style.ERROR("No active machines found!"))
            return
        
        # Get all unique timestamps from logs in the date range
        self.stdout.write("Finding all unique timestamps from logs...")
        
        timestamps = set()
        for machine in machines:
            logs = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__range=(start_time, end_time)
            ).values_list('timestamp', flat=True)
            
            for ts in logs:
                # Round to minute
                ts_minute = ts.replace(second=0, microsecond=0)
                # Apply interval filter
                if interval > 1 and ts_minute.minute % interval != 0:
                    continue
                timestamps.add(ts_minute)
        
        timestamps = sorted(timestamps)
        self.stdout.write(f"Found {len(timestamps)} unique timestamps\n")
        
        if not timestamps:
            self.stdout.write(self.style.WARNING(
                "No log timestamps found in the specified range!"
            ))
            return
        
        # Process each timestamp
        created_count = 0
        updated_count = 0
        error_count = 0
        
        self.stdout.write("Creating snapshots...")
        
        for i, timestamp in enumerate(timestamps, 1):
            try:
                with transaction.atomic():
                    # Build snapshot data for this timestamp
                    snapshot_data = {}
                    
                    # Get energy source data for this timestamp
                    steam_log = MachineMinuteLog.objects.filter(
                        machine__code='Steam_Pr',
                        timestamp=timestamp
                    ).first()
                    
                    hto_log = MachineMinuteLog.objects.filter(
                        machine__code='Oil_Temp',
                        timestamp=timestamp
                    ).first()
                    
                    steam_value = steam_log.temperature if steam_log and steam_log.temperature is not None else None
                    hto_value = hto_log.temperature if hto_log and hto_log.temperature is not None else None
                    
                    for machine in machines:
                        # Find the log for this timestamp
                        log = MachineMinuteLog.objects.filter(
                            machine=machine,
                            timestamp=timestamp
                        ).first()
                        
                        if log:
                            # Determine status and detail
                            if machine.operation_mode == "MANUAL":
                                status = log.last_status or "Unknown"
                                detail = log.last_status or ""  # Manual uses status for detail
                            else:  # AUTO
                                status = log.last_status or "Unknown"
                                detail = log.thermal_state or ""
                            
                            snapshot_data[machine.code] = {
                                "status": status,
                                "detail": detail,
                                "mode": machine.operation_mode,
                                # Energy data
                                "temperature": log.temperature,
                                "filtered_temp": log.filtered_temp,
                                "gradient": log.gradient,
                                "thermal_state": log.thermal_state or ""
                            }
                        else:
                            # No log for this machine at this time
                            snapshot_data[machine.code] = {
                                "status": "-",
                                "detail": "-",
                                "mode": machine.operation_mode,
                                # No energy data
                                "temperature": None,
                                "filtered_temp": None,
                                "gradient": None,
                                "thermal_state": ""
                            }
                    
                    # Add global energy source data
                    snapshot_data["_energy_sources"] = {
                        "steam_pr": steam_value,
                        "oil_temp": hto_value
                    }
                    
                    # Create or update snapshot
                    snapshot, created = MachineStatusSnapshot.objects.update_or_create(
                        timestamp=timestamp,
                        defaults={"snapshot_data": snapshot_data}
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    
                    # Progress indicator
                    if i % 100 == 0 or i == len(timestamps):
                        self.stdout.write(
                            f"  Progress: {i}/{len(timestamps)} "
                            f"(Created: {created_count}, Updated: {updated_count})"
                        )
                        
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  Error at {timestamp}: {e}")
                )
        
        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("BACKFILL COMPLETE!"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"Created:  {created_count}")
        self.stdout.write(f"Updated:  {updated_count}")
        self.stdout.write(f"Errors:   {error_count}")
        self.stdout.write(f"{'='*60}\n")
