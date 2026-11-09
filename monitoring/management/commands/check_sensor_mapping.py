import argparse
from django.core.management.base import BaseCommand
from monitoring.models import Machine

class Command(BaseCommand):
    help = "Validasi kelengkapan Sensor Mapping sebelum pindah ke Fase 2"

    def handle(self, *args, **options):
        active_machines = Machine.objects.filter(is_active=True).prefetch_related('sensor_mappings')
        missing_auto_trigger = []

        for m in active_machines:
            if m.operation_mode == "AUTO":
                has_trigger = m.sensor_mappings.filter(role__in=["TRIGGER_OP", "TRIGGER_ENERGY"]).exists()
                if not has_trigger:
                    missing_auto_trigger.append(m.code)
            
        self.stdout.write("\n=== STATUS KESIAPAN FASE 2 (ROLE-BASED SENSOR MAPPING) ===")
        if missing_auto_trigger:
            self.stdout.write(self.style.ERROR(f"[FAIL] Ditemukan {len(missing_auto_trigger)} mesin AUTO yang BELUM di-mapping TRIGGER_OP atau TRIGGER_ENERGY."))
            self.stdout.write("Daftar: " + ", ".join(missing_auto_trigger))
            self.stdout.write("\n[WARNING] JANGAN LANJUT KE FASE 2 DULU, NANTI DASHBOARD BISA SALAH HITUNG!")
        else:
            self.stdout.write(self.style.SUCCESS("[OK] 100% Mesin AUTO sudah memiliki Trigger Operation/Energy. Siap Eksekusi Fase 2!"))
