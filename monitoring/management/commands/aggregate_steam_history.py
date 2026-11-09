from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from monitoring.models import MachineStatusSnapshot, MachineMinuteLog, Machine, PlantHourlySummary, PlantDailySummary
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Aggregates MachineStatusSnapshot data into PlantHourlySummary and PlantDailySummary'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days in the past to aggregate (default 30)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Aggregate ALL historical data',
        )

    def handle(self, *args, **options):
        days = options['days']
        all_data = options['all']

        self.stdout.write(self.style.SUCCESS('Starting steam data aggregation...'))

        # Determine start time
        if all_data:
            first_snapshot = MachineStatusSnapshot.objects.order_by('timestamp').first()
            if not first_snapshot:
                self.stdout.write(self.style.WARNING('No snapshots found.'))
                return
            start_time = first_snapshot.timestamp
        else:
            start_time = timezone.now() - timedelta(days=days)

        start_time = start_time.replace(minute=0, second=0, microsecond=0)
        end_time = timezone.now().replace(minute=0, second=0, microsecond=0)

        # Pre-fetch all machines for their steam usage constants
        all_machines = Machine.objects.all()
        machines_dict = {m.code: m for m in all_machines}

        # ─── AGGREGATE HOURLY ──────────────────────────────────────────────
        current_hour = start_time
        while current_hour < end_time:
            next_hour = current_hour + timedelta(hours=1)
            
            # 1. Total Steam Usage & Active Machine Count
            snapshots = MachineStatusSnapshot.objects.filter(
                timestamp__gte=current_hour,
                timestamp__lt=next_hour
            )
            
            total_steam_for_hour = 0.0
            total_active_machines = 0
            snapshot_count = snapshots.count()
            
            if snapshot_count > 0:
                for snapshot in snapshots:
                    steam_total_minute = 0.0
                    active_count = 0
                    for machine_code, snap_data in snapshot.snapshot_data.items():
                        machine = machines_dict.get(machine_code)
                        if machine and machine.average_steam_usage > 0:  # Only steam-using machines
                            is_active = False
                            if snap_data.get('mode') == 'MANUAL':
                                is_active = snap_data.get('status') == 'Running'
                            else:
                                is_active = snap_data.get('detail') in ['HEAT', 'STEADY']
                            
                            if is_active:
                                # This adds the average usage (kg/h) but since this is 1 minute snapshot, 
                                # if we just average the (kg/h) over all snapshots in the hour, we get the total for the hour!
                                steam_total_minute += machine.average_steam_usage
                                active_count += 1
                                
                    total_steam_for_hour += steam_total_minute
                    total_active_machines += active_count
                
                # Average the (kg/h) rates over the hour to get total kg used in that hour
                avg_steam_usage = total_steam_for_hour / snapshot_count
                avg_machine_count = round(total_active_machines / snapshot_count)
            else:
                avg_steam_usage = 0.0
                avg_machine_count = 0

            # 2. Avg Steam Pressure
            pressure_logs = MachineMinuteLog.objects.filter(
                machine__code="Steam_Pr",
                timestamp__gte=current_hour,
                timestamp__lt=next_hour,
                temperature__isnull=False
            )
            
            if pressure_logs.exists():
                total_pressure = sum(log.temperature for log in pressure_logs)
                avg_pressure = total_pressure / pressure_logs.count()
            else:
                avg_pressure = 0.0
            
            # Save Hourly Summary
            if avg_steam_usage > 0 or avg_pressure > 0:
                PlantHourlySummary.objects.update_or_create(
                    timestamp=current_hour,
                    defaults={
                        'total_steam_usage': round(avg_steam_usage, 2),
                        'avg_steam_pressure': round(avg_pressure, 2),
                        'machine_count': avg_machine_count
                    }
                )
                self.stdout.write(f"Aggregated {current_hour}: {round(avg_steam_usage, 2)} kg, {round(avg_pressure, 2)} bar")

            current_hour = next_hour

        # ─── AGGREGATE DAILY ───────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS('Hourly aggregation complete. Starting Daily aggregation...'))
        
        start_date = start_time.date()
        end_date = end_time.date()
        
        current_date = start_date
        while current_date <= end_date:
            hourly_logs = PlantHourlySummary.objects.filter(
                timestamp__date=current_date
            )
            
            if hourly_logs.exists():
                # For daily, we sum the hourly total usages
                daily_steam = sum(log.total_steam_usage for log in hourly_logs)
                
                daily_pressure = sum(log.avg_steam_pressure for log in hourly_logs) / hourly_logs.count()
                daily_machine = sum(log.machine_count for log in hourly_logs) / hourly_logs.count()
                
                PlantDailySummary.objects.update_or_create(
                    timestamp=current_date,
                    defaults={
                        'total_steam_usage': round(daily_steam, 2),
                        'avg_steam_pressure': round(daily_pressure, 2),
                        'machine_count': round(daily_machine)
                    }
                )
                self.stdout.write(f"Aggregated {current_date}: {round(daily_steam, 2)} kg, {round(daily_pressure, 2)} bar")
                
            current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS('Successfully aggregated all steam data!'))
