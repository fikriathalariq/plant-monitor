import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os, sys, django
from datetime import timedelta
from collections import defaultdict
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()
from monitoring.models import DyeingIdentity, DyeingProcess

FORCE_LINK_MAX_MINUTES = 480
orphans = list(DyeingIdentity.objects.filter(dyeing_process__isnull=True).select_related('machine'))

print("=== KONFLIK ONE-TO-ONE (Batch sudah punya Identity lain) ===")
for o in orphans:
    if not o.machine_id or not o.start_time_snapshot:
        continue
    snapshot = o.start_time_snapshot
    nearby = DyeingProcess.objects.filter(
        machine_id=o.machine_id,
        start_time__range=(snapshot - timedelta(hours=10), snapshot + timedelta(hours=10))
    ).order_by('start_time')
    
    nearest = None
    nearest_diff = None
    for b in nearby:
        diff = abs((b.start_time - snapshot).total_seconds() / 60)
        if nearest_diff is None or diff < nearest_diff:
            nearest_diff = diff
            nearest = b
    
    if nearest and nearest_diff <= FORCE_LINK_MAX_MINUTES:
        try:
            existing = nearest.identity
            if existing:
                snap_str = snapshot.strftime("%m-%d %H:%M")
                existing_str = existing.nomor_order + " / " + existing.artikel_kain
                print(f"  Orphan ID={o.id} ({o.machine.code}) snap={snap_str} -> Batch #{nearest.batch_number} (diff={nearest_diff:.0f}mnt) -> BLOCK oleh Identity ID={existing.id} ({existing_str})")
        except DyeingIdentity.DoesNotExist:
            pass

print()
print("=== ANALISIS DUPLIKAT (order+artikel+mesin sama, waktu dekat) ===")
identity_index = defaultdict(list)
all_ids = list(DyeingIdentity.objects.select_related('machine').all())
for i in all_ids:
    if i.nomor_order and i.artikel_kain:
        key = (i.machine_id, i.nomor_order.strip(), i.artikel_kain.strip())
        identity_index[key].append(i)

dup_groups = {k: v for k, v in identity_index.items() if len(v) >= 2}
print(f"Total grup duplikat: {len(dup_groups)}")
print()
for key, items in list(dup_groups.items())[:25]:
    machine_code = items[0].machine.code if items[0].machine else "?"
    linked = [i for i in items if i.dyeing_process_id]
    orphan_items = [i for i in items if not i.dyeing_process_id]
    if not orphan_items:
        continue  # Semua linked, bukan masalah
    print(f"  Mesin: {machine_code} | Order: {key[1]} | Artikel: {key[2]}")
    for i in items:
        ts = i.start_time_snapshot.strftime("%Y-%m-%d %H:%M UTC") if i.start_time_snapshot else "N/A"
        status = "LINKED->Batch#" + str(i.dyeing_process.batch_number) if i.dyeing_process_id else "ORPHAN"
        print(f"    ID={i.id} | {ts} | {status}")
    print()
