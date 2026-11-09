"""
CLEANUP DUPLICATE ALERTS SCRIPT
================================
"""

from monitoring.models import Alert
from django.db.models import Count, Max

print("\n" + "="*60)
print("CLEANING UP DUPLICATE ALERTS")
print("="*60 + "\n")

# Find all machine + alert_type combinations that have multiple active alerts
duplicates = Alert.objects.filter(
    is_active=True
).values(
    'machine', 'alert_type'
).annotate(
    count=Count('id'),
    latest_id=Max('id')
).filter(count__gt=1)

total_duplicates = 0
total_kept = 0

for dup in duplicates:
    machine_id = dup['machine']
    alert_type = dup['alert_type']
    latest_id = dup['latest_id']
    count = dup['count']
    
    # Get machine name for logging
    from monitoring.models import Machine
    machine = Machine.objects.get(id=machine_id) if machine_id else None
    machine_name = machine.code if machine else "N/A"
    
    print(f"Found {count} active alerts for {machine_name} - {alert_type}")
    
    # Deactivate all except the latest one
    deactivated = Alert.objects.filter(
        machine_id=machine_id,
        alert_type=alert_type,
        is_active=True
    ).exclude(id=latest_id).update(is_active=False)
    
    total_duplicates += deactivated
    total_kept += 1
    
    print(f"  ✓ Kept latest alert (ID: {latest_id})")
    print(f"  ✓ Deactivated {deactivated} duplicate(s)\n")

print("="*60)
print(f"CLEANUP SUMMARY:")
print(f"  - Total duplicate alerts deactivated: {total_duplicates}")
print(f"  - Total unique alerts kept active: {total_kept}")
print("="*60 + "\n")

# Show remaining active alerts
active_alerts = Alert.objects.filter(is_active=True).select_related('machine')
print(f"Remaining active alerts: {active_alerts.count()}\n")

for alert in active_alerts:
    print(f"  - {alert.machine.code if alert.machine else 'N/A'}: {alert.get_alert_type_display()} "
          f"(Created: {alert.created_at.strftime('%Y-%m-%d %H:%M')})")

print("\n✓ Cleanup complete!\n")