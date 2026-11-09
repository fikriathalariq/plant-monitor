"""
Script Seeder untuk Standard Flow Process & Master Kain
Berdasarkan Dokumen Fisik:
- Artikel: HEAVY VALENTINO 3 PICK 58 T
- Resep: R 7864 AA
- Order: 60929 - 6 "Order IC"
- Kode Proses: 100-DM (NON WR)
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
    FlowProcessDryer, FlowProcessPreset, FlowProcessWR, FlowProcessCelup,
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
            nama_kain="HEAVY VALENTINO 3 PICK 58 T",
            defaults={
                "tanggal_order": datetime.date(2026, 10, 12),
                "tanggal_greige": datetime.date(2026, 10, 12),
                "tanggal_finish": datetime.date(2026, 10, 12),
                "status": "AKTIF",
                "epi": Decimal("137.34"),
                "ppi": Decimal("58.00"),
                "ne_warp": Decimal("27.97"),
                "ne_weft": Decimal("17.72"),
                "konst_mesin": Decimal("66.58"),
                "t_ends": 9144,
                "pick_mc": 58,
                "lebar_sisir_efektif": Decimal("169.11"),
                "lebar_greige": Decimal("166.00"),
                "pick_greige": Decimal("62.00"),
                "no_sisir": "34 2/4",
                "cucukan": "2/4",
                "nama_anyaman": anyaman,
                "pcs_length_yd": Decimal("135.00"),
                "keterangan": "No Order: 60929 - 6 \"Order IC\"\nResep: R 7864 AA\nKode Proses: 100-DM (NON WR)",
                "created_by": user
            }
        )
        print(f"   -> Master Kain: {kain.nama_kain} (ID: {kain.id}, Baru: {kain_created})")

        # Benang Lusi
        lusi, lusi_created = BenangLusi.objects.get_or_create(
            master_kain=kain,
            urutan=1,
            defaults={
                "jenis_benang": "IND TIY (IT12 - CG)",
                "denier": Decimal("190.00"),
                "filamen": 108,
                "no_lot": "D780A",
                "tpm": Decimal("1200.00"),
                "twist": "S",
                "repeat": 1,
                "vhs_suhu": Decimal("60.00"),
                "vhs_waktu": Decimal("40.00"),
                "yarn_weight_gross": Decimal("190.00"),
                "yarn_weight_netto": Decimal("190.00")
            }
        )
        print(f"   -> Benang Lusi 1 (ID: {lusi.id}, Baru: {lusi_created})")

        # Benang Pakan
        pakan, pakan_created = BenangPakan.objects.get_or_create(
            master_kain=kain,
            urutan=1,
            defaults={
                "jenis_benang": "IND DTY (ID19 - CL)",
                "denier": Decimal("300.00"),
                "filamen": 96,
                "no_lot": "AX4D2459",
                "tpm": Decimal("800.00"),
                "twist": "S",
                "repeat": 1,
                "vhs_suhu": Decimal("60.00"),
                "vhs_waktu": Decimal("40.00"),
                "yarn_weight_gross": Decimal("300.00"),
                "yarn_weight_netto": Decimal("300.00")
            }
        )
        print(f"   -> Benang Pakan 1 (ID: {pakan.id}, Baru: {pakan_created})")

        print("3. Menyiapkan Header Standard Flow Process...")
        flow, flow_created = StandardFlowProcess.objects.get_or_create(
            master_kain=kain,
            versi="v20261012",
            defaults={
                "tanggal_pembuatan_form": datetime.date(2026, 10, 12),
                "status": "AKTIF",
                "hasil_lebar": Decimal("149.00"),
                "hasil_pick": Decimal("70.00"),
                "hasil_gramasi": Decimal("308.00"),
                "hasil_persen_wr": Decimal("20.00"),
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
            lebar=Decimal("166.00"),
            pick_mesin=Decimal("58.00"),
            pick_greige=Decimal("62.00"),
            berat_greige=Decimal("49.00"),
            gramasi=Decimal("396.00"),
            catatan_koreksi='NO ORDER : 60929 - 6 "Order IC" | RESEP : R 7864 AA | HQ : 100-DM (NON WR)'
        )
        print("   -> [1/7] Greige OK")

        # 2. JET RELAX (Creeping)
        FlowProcessCreeping.objects.create(
            master_flow=flow,
            urutan=2,
            mesin="JR HISAKA",
            program="3",
            temperatur=Decimal("120.00"),
            waktu=Decimal("60.00"),
            tekanan_pompa=Decimal("40.00"),
            volume_air=Decimal("3200.00"),
            isi_per_tube="3X2 / 810 y",
            isi_per_batch="12 Roll/1200m",
            resep="Nozzle: 110 mm | Berat: 586 kg | V Lot Air: 1:5 | KOSTIK 6 Lt | HISAKA NON BEATING | TES Susut : 82 cm",
            hasil_lebar=Decimal("148.50"),
            hasil_pick=Decimal("74.00"),
            hasil_gramasi=Decimal("323.00")
        )
        print("   -> [2/7] Jet Relax (Creeping) OK")

        # 3. DRYER
        FlowProcessDryer.objects.create(
            master_flow=flow,
            urutan=3,
            mesin="SILINDER DRY",
            silinder_dry=True,
            scutcher=False
        )
        print("   -> [3/7] Dryer OK")

        # 4. PRESET
        FlowProcessPreset.objects.create(
            master_flow=flow,
            urutan=4,
            mesin="EHWHA",
            temperatur=Decimal("200.00"),
            speed=Decimal("40.00"),
            set_lebar=Decimal("148.00"),
            blower=Decimal("1700.00"),
            over_feed=Decimal("12.00"),
            hasil_lebar=Decimal("149.00"),
            hasil_pick=Decimal("70.00"),
            hasil_gramasi=Decimal("311.00")
        )
        print("   -> [4/7] Preset OK")

        # 5. DYEING (CELUP)
        FlowProcessCelup.objects.create(
            master_flow=flow,
            urutan=5,
            mesin="HISAKA",
            program="8",
            temperatur=Decimal("130.00"),
            waktu=Decimal("30.00"),
            nozzle=Decimal("110.00"),
            tekanan_pompa=Decimal("40.00"),
            isi_per_tube="3X2Roll / 810 y",
            isi_per_batch="12 Roll/1200m",
            resep="Vol: 3200 L | Berat: 586 kg | V Lot Air: 1:6 | TES Susut : 81 cm | HISAKA : Celup 2 Lapis | Tong Geng : Celup 1 Lapis",
            hasil_lebar=Decimal("147.00"),
            hasil_pick=Decimal("76.00"),
            hasil_gramasi=Decimal("323.00")
        )
        print("   -> [5/7] Celup (Dyeing) OK")

        # 6. RESIN (DRYER FINAL) + OBAT
        dryer_final = FlowProcessDryerFinal.objects.create(
            master_flow=flow,
            urutan=6,
            mesin="SSD 2",
            silinder_dry=False,
            centrifugal=False,
            hasil_lebar=Decimal("147.00"),
            hasil_pick=Decimal("74.00"),
            hasil_gramasi=Decimal("316.00")
        )
        ObatAntistatic.objects.create(
            dryer_final=dryer_final,
            nama="DAISTAT",
            persentase="0.25%"
        )
        ObatSoftener.objects.create(
            dryer_final=dryer_final,
            nama="COTTON FEEL",
            persentase="0.25%"
        )
        print("   -> [6/7] Resin (Dryer Final + Daistat & Cotton Feel) OK")

        # 7. FINAL SET
        FlowProcessFinalSet.objects.create(
            master_flow=flow,
            urutan=7,
            mesin="SPT 2",
            temperatur=Decimal("170.00"),
            speed=Decimal("40.00"),
            set_lebar=Decimal("148.00"),
            blower=Decimal("50.00"),
            over_feed=Decimal("-2.00"),
            hasil_lebar=Decimal("149.00"),
            hasil_pick=Decimal("70.00"),
            hasil_gramasi=Decimal("308.00")
        )
        print("   -> [7/7] Final Set OK")

    print(f"\nSUCCESS: Data Heavy Valentino 3 berhasil diinjeksi ke Database!")
    print(f"URL Admin Master Kain: /admin/monitoring/masterkain/{kain.id}/change/")
    print(f"URL Admin Standard Flow: /admin/monitoring/standardflowprocess/{flow.id}/change/")
    print(f"URL Cetak PDF: /standard-flow/{flow.id}/cetak/")

if __name__ == "__main__":
    run_seed()
