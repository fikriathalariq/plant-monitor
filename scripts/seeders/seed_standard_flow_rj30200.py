import django, os, sys
from decimal import Decimal
from datetime import date

sys.path.insert(0, r'C:\Users\HP\Documents\Plant-Monitor\plant-monitor')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.contrib.auth import get_user_model
from monitoring.models import (
    MasterKain, StandardFlowProcess,
    FlowProcessGreige, FlowProcessCreeping, FlowProcessDryer,
    FlowProcessPreset, FlowProcessWR, FlowProcessCelup,
    FlowProcessDryerFinal, FlowProcessFinalSet,
    ObatAntistatic, ObatSoftener
)

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first()

# 1. MasterKain
nama_kain = "SPUN (PE 30 X DTY 200)"
mk, created = MasterKain.objects.get_or_create(
    nama_kain=nama_kain,
    defaults={
        "status": "AKTIF",
        "tanggal_order": date(2026, 5, 28),
        "tanggal_greige": date(2026, 5, 28),
        "tanggal_finish": date(2026, 5, 28),
        "lebar_greige": Decimal("159.00"),
        "pick_greige": Decimal("72.00"),
        "keterangan": (
            "ORDER: P\n"
            "NAMA KAIN: SPUN RJU PE 30 X DTY 200\n"
            "NO ORDER: 46 - 104 \"Order STA / Lokal\"\n"
            "RESEP: RJ 30200\n"
            "KODE PROSES: 400 (PROSES KHUSUS)\n"
            "GREIGE LUAR\n"
            "GRAMASI: 173 GR/M'"
        ),
        "created_by": admin_user
    }
)
print(f"MasterKain: {mk.id} - {mk.nama_kain} (created={created})")

# 2. StandardFlowProcess
sfp, created_sfp = StandardFlowProcess.objects.get_or_create(
    master_kain=mk,
    versi="v20260528",
    defaults={
        "tanggal_pembuatan_form": date(2026, 5, 28),
        "status": "AKTIF",
        "hasil_lebar": Decimal("153.00"),
        "hasil_pick": Decimal("76.00"),
        "hasil_gramasi": Decimal("128.00"),
        "hasil_susut": None,
        "hasil_persen_wr": None,
        "created_by": admin_user
    }
)
print(f"StandardFlowProcess: {sfp.id} (created={created_sfp})")

# Clear existing child items if re-running
sfp.flowprocessgreige_set.all().delete()
sfp.flowprocesscreeping_set.all().delete()
sfp.flowprocessdryer_set.all().delete()
sfp.flowprocesspreset_set.all().delete()
sfp.flowprocesswr_set.all().delete()
sfp.flowprocesscelup_set.all().delete()
sfp.flowprocessdryerfinal_set.all().delete()
sfp.flowprocessfinalset_set.all().delete()

# Urutan 1: GREIGE
fp_greige = FlowProcessGreige.objects.create(
    master_flow=sfp,
    urutan=1,
    mesin="GREIGE",
    lebar=Decimal("159.00"),
    pick_greige=Decimal("72.00"),
    gramasi=Decimal("173.00"),
    catatan_koreksi=(
        "NO ORDER : 46 - 104 \"Order STA / Lokal\"\n"
        "RESEP : RJ 30200\n"
        "KODE PROSES : 400 (PROSES KHUSUS)\n"
        "GREIGE LUAR"
    )
)
print("Created FlowProcessGreige")

# Urutan 2: CPB (COLD PAD BATH) -> FlowProcessCreeping
fp_cpb = FlowProcessCreeping.objects.create(
    master_flow=sfp,
    urutan=2,
    mesin="CPB",
    tekanan_pompa=Decimal("0.50"),
    volume_air=Decimal("600.00"),
    waktu=Decimal("16.00"),
    program="WPU: 70% | Speed: 16 Rpm",
    isi_per_tube="Panjang: 1200 m",
    resep=(
        "WPU: 70% | Tekanan: 0.5 | Speed: 16 Rpm | Vol: 600 Lt | Waktu: 16 Jam | Pjg: 1200 m\n"
        "Resep:\n"
        "- COSTIK 25 g\n"
        "- LIPOTOL 8 g\n"
        "- SUDEROL 2\n"
        "- SANQUEST 1"
    ),
    hasil_lebar=Decimal("157.00"),
    hasil_pick=Decimal("70.00"),
    hasil_gramasi=Decimal("156.00")
)
print("Created FlowProcessCreeping (CPB)")

# Urutan 3: SMCH -> FlowProcessDryer
fp_smch = FlowProcessDryer.objects.create(
    master_flow=sfp,
    urutan=3,
    mesin="SMCH",
    temperatur=Decimal("90.00"),
    speed=Decimal("10.00"),
    hasil_lebar=Decimal("157.00"),
    hasil_pick=Decimal("70.00"),
    hasil_gramasi=Decimal("156.00")
)
print("Created FlowProcessDryer (SMCH)")

# Urutan 4: SSD 2 -> FlowProcessDryer
fp_ssd2 = FlowProcessDryer.objects.create(
    master_flow=sfp,
    urutan=4,
    mesin="SSD 2",
    silinder_dry=True,
    hasil_lebar=Decimal("147.00"),
    hasil_pick=Decimal("72.00"),
    hasil_gramasi=Decimal("161.00")
)
print("Created FlowProcessDryer (SSD 2)")

# Urutan 5: PRE SETT -> FlowProcessPreset
fp_preset = FlowProcessPreset.objects.create(
    master_flow=sfp,
    urutan=5,
    mesin="MONFONG",
    temperatur=Decimal("190.00"),
    speed=Decimal("40.00"),
    set_lebar=Decimal("152.00"),
    blower=Decimal("60.00"),
    over_feed=Decimal("2.00"),
    hasil_lebar=Decimal("153.00"),
    hasil_pick=Decimal("76.00"),
    hasil_gramasi=Decimal("163.00")
)
print("Created FlowProcessPreset (MONFONG)")

# Urutan 6: CALENDER -> FlowProcessDryer
fp_calender = FlowProcessDryer.objects.create(
    master_flow=sfp,
    urutan=6,
    mesin="CALENDER (Tekanan: 30 Ton)",
    temperatur=Decimal("150.00"),
    speed=Decimal("20.00"),
    hasil_lebar=Decimal("150.00"),
    hasil_pick=Decimal("74.00"),
    hasil_gramasi=Decimal("161.00")
)
print("Created FlowProcessDryer (CALENDER)")

# Urutan 7: WR -> FlowProcessWR
fp_wr = FlowProcessWR.objects.create(
    master_flow=sfp,
    urutan=7,
    mesin="JR (Prog 51 | 130°C x 90' | Vol 2800L | 'WR 2 KARTU')",
    coustic=Decimal("53.00"),
    persen_wr=Decimal("22.00"),
    hasil_lebar=Decimal("150.00"),
    hasil_pick=Decimal("74.00"),
    hasil_gramasi=Decimal("133.00")
)
print("Created FlowProcessWR")

# Urutan 8: DYEING -> FlowProcessCelup
fp_dyeing = FlowProcessCelup.objects.create(
    master_flow=sfp,
    urutan=8,
    mesin="HUAH JEN",
    program="13",
    temperatur=Decimal("130.00"),
    waktu=Decimal("50.00"),
    nozzle=Decimal("4.00"),
    tekanan_pompa=Decimal("1350.00"),
    isi_per_tube="600 m",
    isi_per_batch="1200 m",
    resep="Vol: 2000 L | WARNA: MOCCA",
    hasil_lebar=Decimal("150.00"),
    hasil_pick=Decimal("76.00"),
    hasil_gramasi=Decimal("133.00")
)
print("Created FlowProcessCelup (DYEING)")

# Urutan 9: RESIN -> FlowProcessDryerFinal
fp_resin = FlowProcessDryerFinal.objects.create(
    master_flow=sfp,
    urutan=9,
    mesin="SSD 2",
    silinder_dry=True,
    centrifugal=True,
    hasil_lebar=Decimal("150.00"),
    hasil_pick=Decimal("75.00"),
    hasil_gramasi=Decimal("133.00")
)
ObatAntistatic.objects.create(dryer_final=fp_resin, nama="DAISTAT", persentase="0.25")
ObatSoftener.objects.create(dryer_final=fp_resin, nama="NT42", persentase="1.5")
ObatSoftener.objects.create(dryer_final=fp_resin, nama="ELTEX", persentase="1.5")
print("Created FlowProcessDryerFinal (RESIN)")

# Urutan 10: FINAL -> FlowProcessFinalSet
fp_final = FlowProcessFinalSet.objects.create(
    master_flow=sfp,
    urutan=10,
    mesin="SPT 2",
    temperatur=Decimal("175.00"),
    speed=Decimal("40.00"),
    set_lebar=Decimal("153.00"),
    blower=Decimal("50.00"),
    over_feed=Decimal("2.00"),
    hasil_lebar=Decimal("152.00"),
    hasil_pick=Decimal("76.00"),
    hasil_gramasi=Decimal("128.00")
)
print("Created FlowProcessFinalSet (FINAL)")

print(f"\nAll seeded successfully! StandardFlowProcess ID = {sfp.id}")
