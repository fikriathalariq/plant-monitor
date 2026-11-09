"""
Script Seeder untuk Standard Flow Process & Master Kain
Berdasarkan Dokumen Fisik Kedua:
- Artikel: MILANO 2
- Resep: R 7544 HC
- Order: 60929 - 4 B,774 "Order SU"
- Kode Proses: 102-P (NON WR)
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
    MasterKain, MasterAnyaman, BenangLusi, BenangPakan,
    StandardFlowProcess, FlowProcessGreige, FlowProcessCreeping,
    FlowProcessDryer, FlowProcessPreset, FlowProcessCelup,
    FlowProcessDryerFinal, FlowProcessFinalSet, ObatAntistatic, ObatSoftener
)

def run_seed():
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    with transaction.atomic():
        print("1. Menyiapkan Master Anyaman...")
        anyaman, anyaman_created = MasterAnyaman.objects.get_or_create(
            nama="TWILL 3/2 - 2 (KANAN)",
            defaults={
                "kode": "TWL 3/2-2",
                "deskripsi": "Twill 3/2 - 2 (Kanan)",
                "is_active": True
            }
        )
        print(f"   -> Anyaman: {anyaman.nama} (ID: {anyaman.id}, Baru: {anyaman_created})")

        print("2. Menyiapkan Master Kain...")
        kain, kain_created = MasterKain.objects.get_or_create(
            nama_kain="MILANO 2",
            defaults={
                "tanggal_order": datetime.date(2026, 10, 5),
                "tanggal_greige": datetime.date(2026, 10, 5),
                "tanggal_finish": datetime.date(2026, 10, 5),
                "status": "AKTIF",
                "epi": Decimal("137.34"),
                "ppi": Decimal("71.00"),
                "ne_warp": Decimal("27.97"),
                "ne_weft": Decimal("35.43"),
                "konst_mesin": Decimal("66.58"),
                "t_ends": 9144,
                "pick_mc": 71,
                "lebar_sisir_efektif": Decimal("169.11"),
                "lebar_greige": Decimal("165.00"),
                "pick_greige": Decimal("72.00"),
                "no_sisir": "34 2/4",
                "cucukan": "2/4",
                "nama_anyaman": anyaman,
                "pcs_length_yd": Decimal("135.00"),
                "keterangan": "No Order: 60929 - 4 B.774 \"Order SU\"\nResep: R 7544 HC\nKode Proses: 102-P (NON WR)",
                "created_by": user
            }
        )
        print(f"   -> Master Kain: {kain.nama_kain} (ID: {kain.id}, Baru: {kain_created})")

        # Benang Lusi: IND TIY 190 D - 108 F 1200 T/M, LOT. D.780A, "S" (IT 12 - CG)
        lusi, lusi_created = BenangLusi.objects.get_or_create(
            master_kain=kain,
            urutan=1,
            defaults={
                "jenis_benang": "IND TIY (IT 12 - CG)",
                "denier": Decimal("190.00"),
                "filamen": 108,
                "no_lot": "D.780A",
                "tpm": Decimal("1200.00"),
                "twist": "S",
                "repeat": 1,
                "yarn_weight_gross": Decimal("190.00"),
                "yarn_weight_netto": Decimal("190.00")
            }
        )
        print(f"   -> Benang Lusi 1 (ID: {lusi.id}, Baru: {lusi_created})")

        # Benang Pakan: TD DTY 150 D - 48 F 1200 T/M, LOT. M20C51 HIM, "S" (PD 06 - HG)
        pakan, pakan_created = BenangPakan.objects.get_or_create(
            master_kain=kain,
            urutan=1,
            defaults={
                "jenis_benang": "TD DTY (PD 06 - HG)",
                "denier": Decimal("150.00"),
                "filamen": 48,
                "no_lot": "M20C51 HIM",
                "tpm": Decimal("1200.00"),
                "twist": "S",
                "repeat": 1,
                "yarn_weight_gross": Decimal("150.00"),
                "yarn_weight_netto": Decimal("150.00")
            }
        )
        print(f"   -> Benang Pakan 1 (ID: {pakan.id}, Baru: {pakan_created})")

        print("3. Menyiapkan Header Standard Flow Process...")
        flow, flow_created = StandardFlowProcess.objects.get_or_create(
            master_kain=kain,
            versi="v20261005",
            defaults={
                "tanggal_pembuatan_form": datetime.date(2026, 10, 5),
                "status": "AKTIF",
                "hasil_lebar": Decimal("149.00"),
                "hasil_pick": Decimal("88.00"),
                "hasil_gramasi": Decimal("273.00"),
                "hasil_susut": Decimal("20.00"), # Susut panjang 20%
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

        print("4. Mengisi 7 Alur Child Proses...")

        # 1. GREIGE
        FlowProcessGreige.objects.create(
            master_flow=flow,
            urutan=1,
            mesin="GREIGE",
            panjang_std=Decimal("135.00"),
            lebar=Decimal("165.00"),
            pick_mesin=Decimal("71.00"),
            pick_greige=Decimal("72.00"),
            berat_greige=None,
            gramasi=Decimal("201.00"),
            catatan_koreksi='NO ORDER : 60929 - 4 B.774 "Order SU" | RESEP : R 7544 HC | HQ : 102-P (NON WR)'
        )
        print("   -> [1/7] Greige OK")

        # 2. JET RELAX (Creeping)
        FlowProcessCreeping.objects.create(
            master_flow=flow,
            urutan=2,
            mesin="JR HISAKA",
            program="123",
            temperatur=Decimal("120.00"),
            waktu=Decimal("40.00"),
            tekanan_pompa=Decimal("40.00"),
            volume_air=Decimal("3200.00"),
            isi_per_tube="3X2Roll / 810 Y",
            isi_per_batch="12 Roll/1200m",
            resep="Nozzle: 110 mm | Resep: AIR SAJA | JR RANGKAP 3X2 | JR NON BEATING | TES Susut : 82 cm",
            hasil_lebar=Decimal("147.00"),
            hasil_pick=Decimal("92.00"),
            hasil_gramasi=Decimal("283.00")
        )
        print("   -> [2/7] Jet Relax (Creeping) OK")

        # 3. DRYER
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
            mesin="EHWHA",
            temperatur=Decimal("200.00"),
            speed=Decimal("40.00"),
            set_lebar=Decimal("148.00"),
            blower=Decimal("1700.00"),
            over_feed=Decimal("3.00"),
            hasil_lebar=Decimal("148.00"),
            hasil_pick=Decimal("90.00"),
            hasil_gramasi=Decimal("277.00")
        )
        print("   -> [4/7] Preset OK")

        # 5. DYEING (CELUP)
        FlowProcessCelup.objects.create(
            master_flow=flow,
            urutan=5,
            mesin="HISAKA 11",
            program="13",
            temperatur=Decimal("130.00"),
            waktu=Decimal("60.00"),
            nozzle=Decimal("110.00"),
            tekanan_pompa=Decimal("40.00"),
            isi_per_tube="3X2 Roll/810 Y",
            isi_per_batch="12Roll/1200m",
            resep="Vol: 3200 L | CELUP RANGKAP 3X2 | TES Susut : 80.5 cm",
            hasil_lebar=Decimal("145.00"),
            hasil_pick=Decimal("94.00"),
            hasil_gramasi=Decimal("291.00")
        )
        print("   -> [5/7] Celup (Dyeing - Hisaka 11) OK")

        # 6. RESIN (DRYER FINAL) + OBAT
        dryer_final = FlowProcessDryerFinal.objects.create(
            master_flow=flow,
            urutan=6,
            mesin="SSD 2",
            silinder_dry=False,
            centrifugal=False,
            hasil_lebar=Decimal("146.00"),
            hasil_pick=Decimal("90.00"),
            hasil_gramasi=Decimal("275.00")
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
            temperatur=Decimal("170.00"),
            speed=Decimal("40.00"),
            set_lebar=Decimal("148.00"),
            blower=Decimal("50.00"),
            over_feed=Decimal("1.00"),
            hasil_lebar=Decimal("149.00"),
            hasil_pick=Decimal("88.00"),
            hasil_gramasi=Decimal("273.00")
        )
        print("   -> [7/7] Final Set OK")

    print(f"\nSUCCESS: Data Milano 2 berhasil diinjeksi ke Database!")
    print(f"URL Admin Master Kain: /admin/monitoring/masterkain/{kain.id}/change/")
    print(f"URL Admin Standard Flow: /admin/monitoring/standardflowprocess/{flow.id}/change/")
    print(f"URL Cetak PDF: /standard-flow/{flow.id}/cetak/")

if __name__ == "__main__":
    run_seed()
