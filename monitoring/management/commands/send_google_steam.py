import time
import requests
import json
from django.core.management.base import BaseCommand
from monitoring.models import Machine

# --- KONFIGURASI ---
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwniG_Fs5TMe_iFJ8kaTYGs19vpbTja35231vGvTuVIOLT7P8603MLuqZzGssaf1G-MVg/exec"
TARGET_CODE = "Steam_Pr"  # Kode mesin/channel yang mau diambil
INTERVAL = 60 # Detik

class Command(BaseCommand):
    help = "Mengirim data Steam_Pr dari Database ke Google Apps Script"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Service Pengirim Steam ke Google Berjalan..."))
        
        while True:
            try:
                # 1. AMBIL DATA DARI DATABASE (Hasil kerja jumo_realtime)
                # Kita cari Machine yang kodenya "Steam_Pr"
                machine = Machine.objects.filter(code=TARGET_CODE).first()

                if machine and machine.temperature is not None:
                    nilai_tekanan = float(machine.temperature)
                    
                    # Cek apakah data cukup baru (optional, misal < 2 menit)
                    # Agar tidak mengirim data basi jika jumo_realtime mati
                    # if (timezone.now() - machine.last_update).total_seconds() > 120:
                    #     print("Data basi, skip kirim.")
                    #     continue

                    # 2. KIRIM KE GOOGLE
                    self.kirim_ke_google(nilai_tekanan)
                else:
                    self.stdout.write(self.style.WARNING(f"Menunggu data '{TARGET_CODE}' masuk ke DB..."))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error Loop Utama: {e}"))

            # 3. Jeda
            time.sleep(INTERVAL)

    def kirim_ke_google(self, nilai):
        try:
            payload = {'pressure': nilai}
            headers = {'Content-Type': 'application/json'}
            
            # Kirim POST request
            response = requests.post(
                APPS_SCRIPT_URL, 
                data=json.dumps(payload), 
                headers=headers,
                timeout=5 # Timeout biar tidak hang kalau internet lemot
            )
            
            if response.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] Terkirim: {nilai} Bar | OK")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Gagal: {response.status_code}")
                
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error Koneksi: {e}")