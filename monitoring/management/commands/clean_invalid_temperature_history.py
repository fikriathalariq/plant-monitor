import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from monitoring.models import MachineMinuteLog, Machine

class Command(BaseCommand):
    help = "Merapikan data history (MachineMinuteLog dan Machine) yang memiliki suhu error (<= -1000 atau >= 100000)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Memulai proses cleaning suhu error ekstrim di database..."))
        
        # 1. Update MachineMinuteLog
        logs_to_update = MachineMinuteLog.objects.filter(Q(temperature__lte=-1000) | Q(temperature__gte=100000))
        logs_count = logs_to_update.count()
        self.stdout.write(f"Ditemukan {logs_count} log dengan suhu error (<= -1000 atau >= 100000).")
        
        if logs_count > 0:
            with transaction.atomic():
                updated_count = logs_to_update.update(
                    temperature=None,
                    raw_temperature=None,
                    filtered_temp=None,
                    gradient=None,
                    thermal_state="OFFLINE",
                    ewma_temp=None,
                    kalman_x=None,
                    kalman_p=None,
                    ewma_gradient=None,
                    kalman_grad_x=None
                )
            self.stdout.write(self.style.SUCCESS(f"Berhasil mengupdate {updated_count} log menjadi None."))

        # 2. Update logs with raw_temperature
        raw_logs_to_update = MachineMinuteLog.objects.filter(Q(raw_temperature__lte=-1000) | Q(raw_temperature__gte=100000))
        raw_logs_count = raw_logs_to_update.count()
        self.stdout.write(f"Ditemukan {raw_logs_count} log dengan raw_temperature error (<= -1000 atau >= 100000).")
        
        if raw_logs_count > 0:
            with transaction.atomic():
                updated_raw_count = raw_logs_to_update.update(
                    temperature=None,
                    raw_temperature=None,
                    filtered_temp=None,
                    gradient=None,
                    thermal_state="OFFLINE",
                    ewma_temp=None,
                    kalman_x=None,
                    kalman_p=None,
                    ewma_gradient=None,
                    kalman_grad_x=None
                )
            self.stdout.write(self.style.SUCCESS(f"Berhasil mengupdate {updated_raw_count} log (raw_temperature) menjadi None."))

        # 3. Update active Machines
        machines_to_update = Machine.objects.filter(Q(temperature__lte=-1000) | Q(temperature__gte=100000))
        machines_count = machines_to_update.count()
        
        if machines_count > 0:
            updated_machines = machines_to_update.update(temperature=None)
            self.stdout.write(self.style.SUCCESS(f"Berhasil mereset suhu {updated_machines} mesin aktif yang suhunya error ekstrim."))

        self.stdout.write(self.style.SUCCESS("Proses cleaning selesai!"))
