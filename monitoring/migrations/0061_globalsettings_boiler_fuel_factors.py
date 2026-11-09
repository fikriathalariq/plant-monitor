from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0060_rename_grey_to_greige'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalsettings',
            name='coal_calorific_value',
            field=models.FloatField(
                default=5500.0,
                help_text='Dipakai untuk hitung efisiensi termal (energi output / energi input).',
                verbose_name='Nilai Kalor Batu Bara (kcal/kg)',
            ),
        ),
        migrations.AddField(
            model_name='globalsettings',
            name='fuel_factor_hto_boiler',
            field=models.FloatField(
                default=0.0,
                help_text='kg batu bara per jam untuk setiap 1 Hz kecepatan Speed_R_Bakar. Isi 0 jika belum dikalibrasi.',
                verbose_name='Faktor Konsumsi Batu Bara Boiler HTO (kg/jam per Hz)',
            ),
        ),
        migrations.AddField(
            model_name='globalsettings',
            name='fuel_factor_steam_boiler',
            field=models.FloatField(
                default=0.0,
                help_text='kg batu bara per jam untuk setiap 1 Hz kecepatan Speed_RB_Steam. Isi 0 jika belum dikalibrasi.',
                verbose_name='Faktor Konsumsi Batu Bara Boiler Steam (kg/jam per Hz)',
            ),
        ),
    ]
