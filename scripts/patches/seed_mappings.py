import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

﻿import os, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import Machine, MachineSensorMapping

def seed_auto_machines():
    auto_machines = Machine.objects.filter(is_active=True, operation_mode='AUTO').order_by('code')
    print(f"Memulai seeding untuk {auto_machines.count()} mesin AUTO...\n")
    
    created_count = 0
    for m in auto_machines:
        # 1. Buat TRIGGER_OP (1:1 dengan mesin itu sendiri)
        op_mapping, created_op = MachineSensorMapping.objects.get_or_create(
            machine=m,
            role="TRIGGER_OP",
            defaults={
                'sensor_machine': m,
                'eval_method': 'THERMAL_STATE_BASED'
            }
        )
        if created_op: created_count += 1
        
        # 2. Buat TRIGGER_ENERGY (1:1 dengan mesin itu sendiri)
        en_mapping, created_en = MachineSensorMapping.objects.get_or_create(
            machine=m,
            role="TRIGGER_ENERGY",
            defaults={
                'sensor_machine': m,
                'eval_method': 'THERMAL_STATE_BASED'
            }
        )
        if created_en: created_count += 1
        
        print(f"[{m.code}] Seeding {'Berhasil' if created_op or created_en else 'Sudah Ada'}")

    print(f"\nSelesai! Berhasil membuat {created_count} record mapping baru.")
    print("Silakan jalankan python manage.py check_sensor_mapping untuk verifikasi.")

if __name__ == "__main__":
    seed_auto_machines()
