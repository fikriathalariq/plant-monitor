from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0061_globalsettings_boiler_fuel_factors'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoilerDailyMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True, help_text='Tanggal hari operasional (06:00 tanggal ini s/d 06:00 besok)', unique=True)),
                ('total_steam_usage_kg', models.FloatField(default=0.0)),
                ('avg_pressure', models.FloatField(blank=True, null=True)),
                ('avg_oil_temp', models.FloatField(blank=True, null=True)),
                ('total_fuel_kg', models.FloatField(blank=True, null=True)),
                ('total_fuel_steam_kg', models.FloatField(blank=True, null=True)),
                ('total_fuel_hto_kg', models.FloatField(blank=True, null=True)),
                ('specific_fuel_consumption', models.FloatField(blank=True, null=True)),
                ('pressure_ideal_percent', models.FloatField(blank=True, null=True)),
                ('pressure_ideal_count', models.IntegerField(default=0)),
                ('pressure_under_count', models.IntegerField(default=0)),
                ('pressure_over_count', models.IntegerField(default=0)),
                ('alert_count_critical', models.IntegerField(default=0)),
                ('alert_count_warning', models.IntegerField(default=0)),
                ('alert_count_total', models.IntegerField(default=0)),
                ('has_data', models.BooleanField(default=False, help_text='True jika ada data sensor/tekanan valid pada hari ini')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Boiler Daily Metric',
                'verbose_name_plural': 'Boiler Daily Metrics',
                'ordering': ['-date'],
            },
        ),
    ]
