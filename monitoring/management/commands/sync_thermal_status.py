from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Machine, MachineMinuteLog
from monitoring.utils.gradient_processor import get_machine_status


class Command(BaseCommand):
    help = "Sync Machine status from latest thermal_state in logs."

    def handle(self, *args, **options):
        machines = Machine.objects.filter(is_active=True, operation_mode="AUTO")
        updated = 0
        now = timezone.now()
        offline_threshold = now - timedelta(hours=2)
        
        for m in machines:
            log = MachineMinuteLog.objects.filter(
                machine=m,
                thermal_state__isnull=False
            ).exclude(thermal_state='').order_by('-timestamp').first()
            
            if log and log.timestamp >= offline_threshold:
                # Recent data: use thermal_state from log
                new_thermal_status = log.thermal_state
            else:
                # Old or no data: set to OFFLINE
                new_thermal_status = "OFFLINE"
            
            # Auto-derive last_status from thermal_state
            new_status = get_machine_status(new_thermal_status)
            
            if m.last_thermal_status != new_thermal_status or m.last_status != new_status:
                old_thermal = m.last_thermal_status
                old_status = m.last_status
                m.last_thermal_status = new_thermal_status
                m.last_status = new_status
                m.save(update_fields=['last_thermal_status', 'last_status'])
                self.stdout.write(
                    f"{m.code}: thermal={old_thermal}→{new_thermal_status}, "
                    f"status={old_status}→{new_status}"
                )
                updated += 1
        
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} machines."))
