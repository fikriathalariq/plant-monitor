import time
from django.core.management.base import BaseCommand
from monitoring.models import Machine, JumoDevice, JumoChannel

class Command(BaseCommand):
    help = "Migrasi data device JUMO dari list hardcode ke database"

    def handle(self, *args, **options):
        # Definisikan ulang list DEVICES lama di sini hanya untuk keperluan seeding
        OLD_DEVICES = [
            {
                "name": "JUMO_A_601",
                "ip": "192.168.4.10",
                "start_addr": "0x1006",
                "device_id": 255,
                "num_ai": 6,
                "channels": ["ZET_01", "ZET_06", "ZET_07", "ZET_10", "ZET_11", "ZET_12"],
            },
            {
                "name": "JUMO_B_601",
                "ip": "192.168.4.11",
                "start_addr": "0x1006",
                "device_id": 255,
                "num_ai": 6,
                "channels": ["ZET_02", "ZET_03", "ZET_04", "ZET_05", "ZET_08", "ZET_09"],
            },
            {
                "name": "JUMO_C_500CF",
                "ip": "192.168.3.20",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["Steam_Pr", "Temp_RB_Steam", "Speed_RB_Steam", "Oil_Temp", "Temp_R_Bakar", "Speed_R_Bakar"],
            },
            {
                "name": "JUMO_D_500CF",
                "ip": "192.168.3.15",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["JD_01", "JD_03", "JR_09", "JD_07", "JD_08", "JR_10"],
            },
            {
                "name": "JUMO_E_500CF",
                "ip": "192.168.3.14",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["JD_09", "JD_JetMiniHSK", "JD_10", "JD_12", "JD_13", "JD_14"],
            },
            {
                "name": "JUMO_F_500CF",
                "ip": "192.168.3.13",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["JR_07", "JD_04", "JD_15", "JD_16", "JD_11", "JD_19"],
            },
            {
                "name": "JUMO_G_500CF",
                "ip": "192.168.3.17",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["JR_05", "JR_06", "JR_07", "JR_08", "JR_11", "JR_12"],  # NOTE: JR_7 is likely JR_07 based on the other list having JR_07
            },
            {
                "name": "JUMO_H_500CF",
                "ip": "192.168.3.18",
                "start_addr": "0x0035",
                "device_id": 1,
                "num_ai": 6,
                "channels": ["JR_13", "JD_18", "JR_02", "JR_03", "JR_04", "AI_06"],
            },
        ]

        total_devices_created = 0
        total_channels_created = 0
        errors = []

        self.stdout.write("Memulai migrasi data JUMO...")

        for dev_data in OLD_DEVICES:
            hex_addr = dev_data["start_addr"]
            if isinstance(hex_addr, int):
                hex_addr = str(hex_addr)

            device, dev_created = JumoDevice.objects.get_or_create(
                name=dev_data["name"],
                defaults={
                    "ip_address": dev_data["ip"],
                    "port": 502,
                    "start_addr": hex_addr,
                    "device_id": dev_data["device_id"],
                    "num_ai": dev_data["num_ai"],
                    "is_active": True,
                }
            )

            if dev_created:
                total_devices_created += 1
                self.stdout.write(self.style.SUCCESS(f"  [CREATE] Device: {device.name} ({device.ip_address})"))
            else:
                self.stdout.write(f"  [SKIP]   Device sudah ada: {device.name}")

            # Buat channel mapping
            for idx, ch_code in enumerate(dev_data["channels"]):
                if not ch_code:
                    continue  # Skip slot kosong
                
                # Fix typo JR_7 -> JR_07 if present
                if ch_code == "JR_7":
                    ch_code = "JR_07"

                machine = Machine.objects.filter(code=ch_code).first()
                if machine is None:
                    msg = f"    [WARN] Machine code='{ch_code}' tidak ditemukan di DB (device={device.name}, ch={idx})"
                    self.stdout.write(self.style.WARNING(msg))
                    errors.append(msg)

                channel, ch_created = JumoChannel.objects.get_or_create(
                    device=device,
                    channel_index=idx,
                    defaults={"machine": machine}
                )

                if ch_created:
                    total_channels_created += 1
                    target = machine.code if machine else "(kosong)"
                    self.stdout.write(self.style.SUCCESS(f"    [CREATE] Ch {idx} -> {target}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"=== Selesai: {total_devices_created} device baru, {total_channels_created} channel baru. ==="
        ))
        if errors:
            self.stdout.write(self.style.WARNING(f"\n{len(errors)} peringatan Machine tidak ditemukan:"))
            for e in errors:
                self.stdout.write(self.style.WARNING(e))
            self.stdout.write(self.style.WARNING(
                "Periksa kode-kode di atas di Django Admin dan mapping manual jika diperlukan."
            ))

