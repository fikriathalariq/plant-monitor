import random
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoring.models import Machine


class Command(BaseCommand):
    help = "Update dummy suhu, gradien, dan status mesin setiap 10 detik"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=10,
            help="Interval update dalam detik (default: 10)",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        self.stdout.write(self.style.SUCCESS(
            f"Start random_machines (interval {interval} detik). Tekan CTRL+C untuk berhenti."
        ))

        try:
            while True:
                now = timezone.now()
                machines = Machine.objects.filter(is_active=True, operation_mode="AUTO")

                if not machines.exists():
                    self.stdout.write(self.style.WARNING("Tidak ada mesin aktif."))
                else:
                    for m in machines:
                        # contoh range suhu (sesuaikan dengan prosesmu)
                        temp = round(random.uniform(80.0, 140.0), 1)

                        # contoh gradien suhu -1.0 s/d +2.0 °C/menit
                        grad = round(random.uniform(-1.0, 2.0), 2)

                        # contoh status acak
                        status = random.choices(
                            population=["Running", "Warning", "Stop", "Offline"],
                            weights=[0.6, 0.15, 0.15, 0.1],
                            k=1,
                        )[0]

                        # Update only temperature (last_status auto-derived by log_minute_history)
                        m.temperature = temp
                        m.last_update = now
                        m.save(update_fields=[
                            "temperature",
                            "last_update",
                        ])

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{now.astimezone().strftime('%H:%M:%S')}] "
                            f"Update {machines.count()} mesin."
                        )
                    )

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Dihentikan oleh user (CTRL+C)."))
