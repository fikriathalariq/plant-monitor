"""
Management command to re-sync all machines from their latest MachineMinuteLog
"""
from django.core.management.base import BaseCommand
from monitoring.models import Machine, MachineMinuteLog


class Command(BaseCommand):
    help = 'Re-sync all machines last_thermal_status and temperature_gradient from latest log'

    def handle(self, *args, **options):
        machines = Machine.objects.all()
        synced_count = 0
        error_count = 0
        
        self.stdout.write("Starting machine sync from latest logs...")
        
        for machine in machines:
            try:
                # Get latest log
                latest_log = (
                    MachineMinuteLog.objects
                    .filter(machine=machine)
                    .order_by('-timestamp')
                    .first()
                )
                
                if latest_log:
                    # Sync from latest log
                    machine.last_thermal_status = latest_log.thermal_state or 'OFFLINE'
                    machine.temperature_gradient = latest_log.gradient
                    machine.save(update_fields=['last_thermal_status', 'temperature_gradient'])
                    synced_count += 1
                    
                    self.stdout.write(
                        f"  {machine.code}: thermal={latest_log.thermal_state}, "
                        f"gradient={latest_log.gradient}"
                    )
                else:
                    # No logs, set to OFFLINE
                    machine.last_thermal_status = 'OFFLINE'
                    machine.temperature_gradient = None
                    machine.save(update_fields=['last_thermal_status', 'temperature_gradient'])
                    synced_count += 1
                    self.stdout.write(f"  {machine.code}: No logs, set to OFFLINE")
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  Error syncing {machine.code}: {e}")
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted! Synced: {synced_count}, Errors: {error_count}"
            )
        )
