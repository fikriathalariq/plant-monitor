from django.db import migrations, models
from django.db.models import F


def backfill_last_valid_reading_at(apps, schema_editor):
    """Seed dari last_update agar mesin yang sudah punya suhu bisa segera diuji stale."""
    Machine = apps.get_model("monitoring", "Machine")
    Machine.objects.filter(
        operation_mode="AUTO",
        temperature__isnull=False,
        last_update__isnull=False,
        last_valid_reading_at__isnull=True,
    ).update(last_valid_reading_at=F("last_update"))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0065_userfavoritebatch"),
    ]

    operations = [
        migrations.AddField(
            model_name="machine",
            name="last_valid_reading_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp pembacaan sensor valid terakhir dari jumo_realtime",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_last_valid_reading_at, noop_reverse),
    ]
