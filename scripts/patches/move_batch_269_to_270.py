import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity, DyeingProcess
from django.db import transaction

# Target: Pindahkan ID 676 dari Batch #269 ke Batch #270 (JR_02)
target_id = 676

print("=" * 70)
print(f"  PINDAH BATCH UNTUK ID={target_id} (JR_02)")
print("=" * 70)

try:
    ident = DyeingIdentity.objects.get(id=target_id)
except DyeingIdentity.DoesNotExist:
    print(f"ID={target_id} tidak ditemukan!")
    exit()

print(f"Current snapshot: {ident.start_time_snapshot.strftime('%Y-%m-%d %H:%M UTC')}")
if ident.dyeing_process:
    print(f"Current Batch   : #{ident.dyeing_process.batch_number} (ID process: {ident.dyeing_process.id})")
else:
    print("Current Batch   : None (Orphan)")

try:
    batch_270 = DyeingProcess.objects.get(machine=ident.machine, batch_number=270)
    print(f"\nTarget Batch    : #{batch_270.batch_number} (ID process: {batch_270.id})")
    print(f"Target start_time: {batch_270.start_time.strftime('%Y-%m-%d %H:%M UTC')}")
except DyeingProcess.DoesNotExist:
    print("Batch #270 tidak ditemukan untuk mesin ini!")
    exit()

with transaction.atomic():
    # 1. Update batch-nya langsung ke #270
    ident.dyeing_process = batch_270
    # 2. Update snapshot-nya agar menyesuaikan dengan batch #270 (agar tidak lepas lagi)
    ident.start_time_snapshot = batch_270.start_time
    ident.save(update_fields=['dyeing_process', 'start_time_snapshot'])

    # (Opsional) Tandai batch #269 sebagai tidak valid karena itu batch prematur (cuma 5 menit)
    try:
        batch_269 = DyeingProcess.objects.get(machine=ident.machine, batch_number=269)
        batch_269.is_valid_process = False
        batch_269.save(update_fields=['is_valid_process'])
        print("\n>> Batch #269 ditandai is_valid_process = False")
    except DyeingProcess.DoesNotExist:
        pass

print(f"\n>> BERHASIL! ID={target_id} sekarang terhubung ke Batch #270.")
