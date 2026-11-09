from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0067_alert_type_no_signal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machine",
            name="last_status",
            field=models.CharField(
                choices=[
                    ("Running", "Running"),
                    ("Warning", "Warning"),
                    ("Stop", "Stop"),
                    ("Offline", "Offline"),
                    ("No Signal", "No Signal"),
                ],
                default="Offline",
                max_length=20,
            ),
        ),
    ]
