from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0066_machine_last_valid_reading_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("STEAM_PRESSURE", "Steam Pressure Low"),
                    ("HTO_TEMPERATURE", "HTO Temperature Low"),
                    ("NO_SIGNAL", "Sensor No Signal"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
