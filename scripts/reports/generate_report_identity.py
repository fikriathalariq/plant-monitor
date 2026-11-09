import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from monitoring.models import DyeingIdentity

today = datetime(2026, 9, 1).date()
qs = DyeingIdentity.objects.filter(created_at__date=today).order_by('-created_at')

out = ["# Rekapitulasi Data DyeingIdentity Hari Ini (1 September 2026)\n"]
out.append(f"**Total Identitas yang Diinput:** {qs.count()} data.\n")
out.append("Berikut adalah rincian selengkap-lengkapnya dari data yang diinput hari ini:\n")
out.append("| ID | Mesin | Waktu Input | No Order | Kode Buyer | Artikel | Batch | Warna | Jenis Proses | Isi/Tube | Operator | Masalah | Keterangan |")
out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

for item in qs:
    _id = item.id
    mesin = item.machine.code if item.machine else "-"
    waktu = item.created_at.strftime('%H:%M:%S') if item.created_at else "-"
    no_order = item.nomor_order or "-"
    buyer = item.kode_buyer or "-"
    artikel = item.artikel_kain or "-"
    batch = item.batch or "-"
    warna = item.nomor_warna or "-"
    jenis = item.jenis_proses or "-"
    isi = item.isi_per_tube or "-"
    operator = item.operator or "-"
    masalah = item.masalah or "-"
    ket = item.keterangan or "-"
    
    out.append(f"| {_id} | {mesin} | {waktu} | {no_order} | {buyer} | {artikel} | {batch} | {warna} | {jenis} | {isi} | {operator} | {masalah} | {ket} |")

with open(r"C:\Users\HP\.gemini\antigravity\brain\45ce1ea6-0aa1-4b47-83d3-a04c35bc92ee\dyeing_identity_today.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
