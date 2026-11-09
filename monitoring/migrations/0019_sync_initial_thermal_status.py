"""
Data migration to sync last_thermal_status from latest MachineMinuteLog
"""
from django.db import migrations


def sync_thermal_status(apps, schema_editor):
    """
    Populate last_thermal_status for all existing machines from their latest log entry.
    """
    Machine = apps.get_model('monitoring', 'Machine')
    MachineMinuteLog = apps.get_model('monitoring', 'MachineMinuteLog')
    
    machines = Machine.objects.all()
    updated_count = 0
    
    for machine in machines:
        # Get the latest log entry for this machine
        latest_log = (
            MachineMinuteLog.objects
            .filter(machine=machine)
            .order_by('-timestamp')
            .first()
        )
        
        if latest_log and latest_log.thermal_state:
            # Update machine's last_thermal_status from the log
            machine.last_thermal_status = latest_log.thermal_state
            machine.save(update_fields=['last_thermal_status'])
            updated_count += 1
    
    print(f"Synced thermal status for {updated_count} machines")


def reverse_sync(apps, schema_editor):
    """
    Reverse: set all back to OFFLINE (default)
    """
    Machine = apps.get_model('monitoring', 'Machine')
    Machine.objects.all().update(last_thermal_status='OFFLINE')


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0018_machine_last_thermal_status_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_thermal_status, reverse_sync),
    ]
