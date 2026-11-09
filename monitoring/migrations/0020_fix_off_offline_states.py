"""
Data migration to fix OFF/OFFLINE thermal states after distinction clarification
"""
from django.db import migrations


def fix_thermal_states(apps, schema_editor):
    """
    Update thermal_state from OFF to OFFLINE for records with invalid temperature.
    
    Invalid temperature conditions:
    - temperature is None
    - temperature == "-"  
    - temperature <= 0
    """
    MachineMinuteLog = apps.get_model('monitoring', 'MachineMinuteLog')
    
    # Find all logs where temperature is invalid but thermal_state is not OFFLINE
    invalid_temp_logs = MachineMinuteLog.objects.filter(
        thermal_state='OFF'
    ).exclude(
        temperature__gt=0  # Keep only those with temp <= 0 or None or "-"
    )
    
    count = invalid_temp_logs.update(thermal_state='OFFLINE')
    print(f"Updated {count} invalid temp logs from OFF to OFFLINE")
    
    # Now re-sync Machine.last_thermal_status from latest log
    Machine = apps.get_model('monitoring', 'Machine')
    machines = Machine.objects.all()
    updated_machines = 0
    
    for machine in machines:
        latest_log = (
            MachineMinuteLog.objects
            .filter(machine=machine)
            .order_by('-timestamp')
            .first()
        )
        
        if latest_log and latest_log.thermal_state:
            machine.last_thermal_status = latest_log.thermal_state
            machine.save(update_fields=['last_thermal_status'])
            updated_machines += 1
    
    print(f"Re-synced thermal status for {updated_machines} machines")


def reverse_fix(apps, schema_editor):
    """
    Reverse: change all OFFLINE back to OFF
    """
    MachineMinuteLog = apps.get_model('monitoring', 'MachineMinuteLog')
    MachineMinuteLog.objects.filter(thermal_state='OFFLINE').update(thermal_state='OFF')


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0019_sync_initial_thermal_status'),
    ]

    operations = [
        migrations.RunPython(fix_thermal_states, reverse_fix),
    ]
