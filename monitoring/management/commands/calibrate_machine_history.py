import time
from django.core.management.base import BaseCommand
from django.db import transaction
from monitoring.models import Machine, MachineMinuteLog, MachineCalibration

class Command(BaseCommand):
    help = 'Melakukan backfill / kalibrasi ulang untuk seluruh histori log pada 1 mesin tertentu secara aman (chunking).'

    def add_arguments(self, parser):
        parser.add_argument('machine_code', type=str, help='Kode Mesin (contoh: JR_10)')
        parser.add_argument(
            '--batch-size',
            type=int,
            default=5000,
            help='Jumlah baris data yang diproses sekali jalan (default: 5000)'
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=0.1,
            help='Waktu jeda antar batch dalam detik (default: 0.1)'
        )

    def handle(self, *args, **options):
        machine_code = options['machine_code']
        batch_size = options['batch_size']
        sleep_time = options['sleep']

        # 1. Validasi Mesin
        try:
            machine = Machine.objects.get(code=machine_code)
            self.stdout.write(self.style.SUCCESS(f"Mesin ditemukan: {machine.name} (ID: {machine.id})"))
        except Machine.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"GAGAL: Mesin dengan kode '{machine_code}' tidak ditemukan!"))
            return

        # 2. Validasi Konfigurasi Kalibrasi
        try:
            cal = MachineCalibration.objects.get(machine=machine, is_active=True)
            self.stdout.write(self.style.SUCCESS(
                f"Kalibrasi AKTIF ditemukan: y = {cal.a_coeff}x^2 + {cal.b_coeff}x + {cal.c_coeff}"
            ))
        except MachineCalibration.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"GAGAL: Tidak ada konfigurasi kalibrasi AKTIF untuk mesin {machine_code}."
            ))
            self.stdout.write("Silakan buat dan aktifkan kalibrasi di menu Django Admin terlebih dahulu.")
            return

        # 3. Hitung jumlah total data yang perlu dikalibrasi
        #    Kita ambil semua log yang raw_temperature-nya belum diisi (masih NULL)
        #    ATAU jika Anda ingin menimpa paksa semuanya, kita bisa ambil semua log.
        #    Untuk amannya, kita kerjakan semua log mesin tersebut.
        total_logs = MachineMinuteLog.objects.filter(machine=machine).count()
        
        if total_logs == 0:
            self.stdout.write(self.style.WARNING(f"Tidak ada data log suhu untuk mesin {machine_code}."))
            return

        self.stdout.write(self.style.WARNING(f"\nTotal data histori yang akan dikalibrasi: {total_logs:,} baris"))
        self.stdout.write(f"Batch size: {batch_size} | Jeda: {sleep_time} detik")
        self.stdout.write("Memulai proses...\n")

        processed = 0
        updated_count = 0
        start_time = time.time()

        # Gunakan iterator agar tidak memuat jutaan baris ke memori sekaligus
        logs_queryset = MachineMinuteLog.objects.filter(machine=machine).order_by('timestamp')
        
        # Buffer untuk bulk_update
        update_buffer = []

        for log in logs_queryset.iterator(chunk_size=batch_size):
            # Jika raw_temperature masih kosong (NULL), amankan suhu aslinya ke raw_temperature
            raw_val = log.raw_temperature
            if raw_val is None:
                raw_val = log.temperature
                log.raw_temperature = raw_val

            # Jika angka tidak valid, lewati perhitungan
            if raw_val is None:
                processed += 1
                continue
                
            try:
                raw_float = float(raw_val)
                # Hitung kalibrasi
                calibrated = (cal.a_coeff * raw_float ** 2) + (cal.b_coeff * raw_float) + cal.c_coeff
                new_temp = round(calibrated, 4)
                
                # Update nilai suhu
                log.temperature = new_temp
                update_buffer.append(log)
                
            except (TypeError, ValueError):
                pass # Bukan angka (misal '-')
                
            processed += 1

            # Lakukan Bulk Update jika buffer sudah penuh
            if len(update_buffer) >= batch_size:
                with transaction.atomic():
                    MachineMinuteLog.objects.bulk_update(
                        update_buffer, 
                        ['raw_temperature', 'temperature'],
                        batch_size=1000
                    )
                updated_count += len(update_buffer)
                update_buffer = []
                
                # Progress report
                percent = (processed / total_logs) * 100
                self.stdout.write(f"Progress: {processed:,} / {total_logs:,} ({percent:.1f}%) ... Istirahat {sleep_time}s")
                time.sleep(sleep_time) # Istirahat agar server tidak hang

        # Update sisa buffer yang belum tersimpan
        if update_buffer:
            with transaction.atomic():
                MachineMinuteLog.objects.bulk_update(
                    update_buffer, 
                    ['raw_temperature', 'temperature'],
                    batch_size=1000
                )
            updated_count += len(update_buffer)

        duration = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f"\nSELESAI! Berhasil mengkalibrasi {updated_count:,} baris data dalam {duration:.1f} detik."
        ))
