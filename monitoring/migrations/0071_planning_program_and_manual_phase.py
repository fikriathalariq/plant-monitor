# Generated for Production Planning v2: program FK + RUNNING phase

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0070_add_production_planning_page_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionplanbatch",
            name="program",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Program target yang dipilih saat batch dibuat/diedit (opsional, hanya untuk mesin AUTO). "
                    "Disimpan untuk histori/pelaporan — durasi aktual tetap di ProductionPlanBlock, "
                    "TIDAK auto-sync kalau ProgramMaster diubah admin di kemudian hari."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="plan_batches",
                to="monitoring.programmaster",
            ),
        ),
        migrations.AlterField(
            model_name="productionplanblock",
            name="phase",
            field=models.CharField(
                choices=[
                    ("HEAT", "Heating"),
                    ("STEADY", "Hold / Keeping"),
                    ("COOL", "Cooling"),
                    ("RUNNING", "Running (Manual On)"),
                ],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="productionplanblock",
            name="sequence",
            field=models.PositiveSmallIntegerField(
                help_text="0=Heat, 1=Hold, 2=Cool (AUTO) atau 0=Running (MANUAL)"
            ),
        ),
    ]
