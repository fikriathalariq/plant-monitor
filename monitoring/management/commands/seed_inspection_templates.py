from django.core.management.base import BaseCommand
from monitoring.models import InspectionTemplate

DEFAULT_ITEMS = [
    {"id": "temp_abnormal", "label": "Suhu abnormal", "required": True},
    {"id": "steam_leak", "label": "Kebocoran steam", "required": True},
    {"id": "sensor_error", "label": "Sensor error", "required": True},
    {"id": "spare_worn", "label": "Spare part aus", "required": False},
    {"id": "noise_vibration", "label": "Kebocoran/getaran", "required": False},
]


class Command(BaseCommand):
    help = 'Seed default field inspection template for engineer workspace'

    def handle(self, *args, **options):
        template, created = InspectionTemplate.objects.update_or_create(
            name='Checklist Umum Mesin',
            machine_group=None,
            defaults={'items': DEFAULT_ITEMS, 'is_active': True},
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action}: {template.name}'))
