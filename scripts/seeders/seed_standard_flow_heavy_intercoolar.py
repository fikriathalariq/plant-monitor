"""
Script Seeder untuk Standard Flow Process & Master Kain
Berdasarkan Dokumen Fisik Ketiga:
- Artikel: HEAVY INTERCOOLAR
- Resep: DTST-5 ( NS ) WV 60 - DC
- Order: 43 - 014 B.170 "Order CML" TES BULK (ORDER POLA / PT. POLA MANUNGGAL SEJATI)
- Kode Proses: S101
- Kode Resin: P
- HQ: 101-P (NON WR)
- Greige: GREIGE LUAR
"""

import os
import sys
import datetime
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.db import transaction
from django.contrib.auth.models import User
from monitoring.models import (
    MasterKain,
    StandardFlowProcess, FlowProcessGreige, FlowProcessCreeping,
    FlowProcessDryer, FlowProcessPreset, FlowProcessCelup,
    FlowProcessDryerFinal, FlowProcessFinalSet, ObatAntistatic, ObatSoftener
)

def run_seed():
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    with transaction.atomic():
        print("1. Menyiapkan Master Kain (HEAVY INTERCOOLAR)...")
        kain, kain_created = MasterKain.objects.get_or_create(
            nama_kain="HEAVY INTERCOOLAR",
            defaults={
                "tanggal_order": datetime.date(2025, 11, 21),
                "tanggal_greige": datetime.date(2025, 11, 21),
                "tanggal_finish": datetime.date(2025, 11, 21),
                "status": "AKTIF",
                "lebar_greige": Decimal("164.00"),
                "pick_greige": Decimal("74.00"),
                "pcs_length_yd": Decimal("130.00"),
                "keterangan": "PT. POLA MANUNGGAL SEJATI / CV SUROTEX\nORDER: POLA\nNO ORDER: 43 - 014 B.170 \"Order CML\" TES BULK\nRESEP: DTST-5 ( NS ) WV 60 - DC\nHQ: 101-P (NON WR)\nGREIGE LUAR",
                "created_by": user
            }
        )
        print(f"   -> Master Kain: {kain.nama_kain} (ID: {kain.id}, Baru: {kain_created})")

        print("2. Menyiapkan Header Standard Flow Process...")
        flow, flow_created = StandardFlowProcess.objects.get_or_create(
            master_kain=kain,
            versi="v20251121",
            defaults={
                "tanggal_pembuatan_form": datetime.date(2025, 11, 21),
                "status": "AKTIF",
                "hasil_lebar": Decimal("152.00"),
                "hasil_pick": Decimal("86.00"),
                "hasil_gramasi": Decimal("228.00"),
                "created_by": user
            }
        )
        print(f"   -> StandardFlowProcess (ID: {flow.id}, Baru: {flow_created})")

        # Hapus child lama jika ada agar sinkron bersih
        flow.flowprocessgreige_set.all().delete()
        flow.flowprocesscreeping_set.all().delete()
        flow.flowprocessdryer_set.all().delete()
        flow.flowprocesspreset_set.all().delete()
        flow.flowprocesswr_set.all().delete()
        flow.flowprocesscelup_set.all().delete()
        flow.flowprocessdryerfinal_set.all().delete()
        flow.flowprocessfinalset_set.all().delete()

        print("3. Mengisi 7 Alur Child Proses...")

        # 1. GREIGE
        FlowProcessGreige.objects.create(
            master_flow=flow,
            urutan=1,
            mesin="GREIGE",
            panjang_std=Decimal("130.00"),
            lebar=Decimal("164.00"),
            pick_greige=Decimal("74.00"),
            gramasi=Decimal("181.00"),
            catatan_koreksi='NO ORDER : 43 - 014 B.170 "Order CML" TES BULK | RESEP : DTST-5 ( NS ) WV 60 - DC | HQ : 101-P (NON WR) | GREIGE LUAR'
        )
        print("   -> [1/7] Greige OK")

        # 2. JET RELAX (Creeping)
        FlowProcessCreeping.objects.create(
            master_flow=flow,
            urutan=2,
            mesin="HISAKA",
            program="133",
            temperatur=Decimal("130.00"),
            waktu=Decimal("30.00"),
            tekanan_pompa=Decimal("40.00"),
            volume_air=Decimal("2800.00"),
            isi_per_tube="6 roll / 780y",
            isi_per_batch="12 roll / 1200m",
            resep="Nozzle: 90 mm / 4 mm | Resep: AIR SAJA",
            hasil_lebar=Decimal("152.00"),
            hasil_pick=Decimal("92.00"),
            hasil_gramasi=Decimal("244.00")
        )
        print("   -> [2/7] Jet Relax (Creeping) OK")

        # 3. DRYER (Centrifugal)
        FlowProcessDryer.objects.create(
            master_flow=flow,
            urutan=3,
            mesin="CENTRIFUGAL",
            silinder_dry=False,
            scutcher=False
        )
        print("   -> [3/7] Dryer (Centrifugal) OK")

        # 4. PRESET
        FlowProcessPreset.objects.create(
            master_flow=flow,
            urutan=4,
            mesin="MONFONGS",
            temperatur=Decimal("200.00"),
            speed=Decimal("50.00"),
            set_lebar=Decimal("151.00"),
            blower=Decimal("60.00"),
            over_feed=Decimal("1.00"),
            hasil_lebar=Decimal("152.00"),
            hasil_pick=Decimal("88.00"),
            hasil_gramasi=Decimal("230.00")
        )
        print("   -> [4/7] Preset OK")

        # 5. DYEING (CELUP)
        FlowProcessCelup.objects.create(
            master_flow=flow,
            urutan=5,
            mesin="HISAKA",
            program="16",
            temperatur=Decimal("130.00"),
            waktu=Decimal("30.00"),
            nozzle=Decimal("90.00"),
            tekanan_pompa=Decimal("40.00"),
            isi_per_tube="6 roll / 780y",
            isi_per_batch="12 roll / 1200m",
            resep="Nozzle: 90 mm/4 mm | WARNA ABU SMA TUA",
            hasil_lebar=Decimal("150.00"),
            hasil_pick=Decimal("90.00"),
            hasil_gramasi=Decimal("240.00")
        )
        print("   -> [5/7] Celup (Dyeing - Hisaka) OK")

        # 6. RESIN (DRYER FINAL) + OBAT
        dryer_final = FlowProcessDryerFinal.objects.create(
            master_flow=flow,
            urutan=6,
            mesin="SSD 2",
            silinder_dry=False,
            centrifugal=False,
            hasil_lebar=Decimal("149.00"),
            hasil_pick=Decimal("86.00"),
            hasil_gramasi=Decimal("235.00")
        )
        ObatAntistatic.objects.create(
            dryer_final=dryer_final,
            nama="DAISTAT",
            persentase="0.25%"
        )
        ObatSoftener.objects.create(
            dryer_final=dryer_final,
            nama="ELTEX",
            persentase="0.25%"
        )
        print("   -> [6/7] Resin (SSD 2 + Daistat 0.25% & Eltex 0.25%) OK")

        # 7. FINAL SET
        FlowProcessFinalSet.objects.create(
            master_flow=flow,
            urutan=7,
            mesin="SPT 2",
            temperatur=Decimal("165.00"),
            speed=Decimal("40.00"),
            set_lebar=Decimal("151.00"),
            blower=Decimal("50.00"),
            over_feed=Decimal("1.00"),
            hasil_lebar=Decimal("152.00"),
            hasil_pick=Decimal("86.00"),
            hasil_gramasi=Decimal("228.00")
        )
        print("   -> [7/7] Final Set OK")

    print(f"\nSUCCESS: Data Heavy Intercoolar berhasil diinjeksi ke Database!")
    print(f"URL Admin Master Kain: /admin/monitoring/masterkain/{kain.id}/change/")
    print(f"URL Admin Standard Flow: /admin/monitoring/standardflowprocess/{flow.id}/change/")
    print(f"URL Cetak PDF: /standard-flow/{flow.id}/cetak/")

if __name__ == "__main__":
    run_seed()
