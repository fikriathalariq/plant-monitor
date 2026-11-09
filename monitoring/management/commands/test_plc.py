from django.core.management.base import BaseCommand
import snap7

class Command(BaseCommand):
    help = 'Test connection to Siemens PLC'

    def handle(self, *args, **options):
        plc_ip = '192.168.100.101'
        plc = snap7.client.Client()
        
        self.stdout.write(f"Mencoba koneksi protokol S7 ke {plc_ip}...")
        
        try:
            # Rack 0, Slot 1 adalah pengaturan standar untuk S7-1200 / S7-1500
            # Jika Anda pakai S7-300, biasanya Rack 0, Slot 2
            plc.connect(plc_ip, 0, 1)
            
            if plc.get_connected():
                self.stdout.write(self.style.SUCCESS(f"Berhasil terkoneksi ke PLC Siemens di {plc_ip}"))
                plc.disconnect()
            else:
                self.stdout.write(self.style.ERROR("Koneksi gagal."))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Terjadi error: {e}"))