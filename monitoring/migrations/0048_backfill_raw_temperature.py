"""
Data migration: backfill raw_temperature dari temperature (versi cepat).

VERSI INI MENGGANTIKAN versi sebelumnya yang menggunakan Python batch loop
dengan OFFSET pagination — metode tersebut sangat lambat untuk 20+ juta baris
karena setiap batch harus men-scan ulang semua baris sebelumnya.

Versi ini menggunakan satu perintah SQL langsung:
    UPDATE monitoring_machineminutelog
    SET raw_temperature = temperature
    WHERE raw_temperature IS NULL AND temperature IS NOT NULL

SQLite/PostgreSQL dapat menjalankan UPDATE ini jauh lebih efisien karena:
1. Tidak ada overhead Python per-baris
2. Tidak ada OFFSET pagination yang makin lambat
3. Database optimizer dapat memilih strategi terbaik (full table scan sekali)

Estimasi waktu: jauh lebih cepat dari versi batch (mungkin 1-10 menit
tergantung hardware, vs jam untuk versi batch).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0047_add_machinecalibration_and_raw_temperature'),
    ]

    operations = [
        migrations.RunSQL(
            # Forward: salin temperature -> raw_temperature untuk semua data lama
            sql="""
                UPDATE monitoring_machineminutelog
                SET raw_temperature = temperature
                WHERE raw_temperature IS NULL
                  AND temperature IS NOT NULL;
            """,
            # Reverse: reset raw_temperature kembali ke NULL
            reverse_sql="""
                UPDATE monitoring_machineminutelog
                SET raw_temperature = NULL;
            """,
        ),
    ]
