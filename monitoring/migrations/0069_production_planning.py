# Generated manually for Production Planning feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("monitoring", "0068_machine_last_status_no_signal"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shift_date", models.DateField(help_text="Tanggal awal shift (jam 06:00), sama makna dgn shift_date di snapshot-history")),
                ("name", models.CharField(blank=True, help_text="Nama rencana, misal: 'Rencana Shift A - 21 Agu'", max_length=150)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], default="DRAFT", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1, help_text="Dinaikkan setiap update tersimpan; untuk optimistic locking sederhana")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_plans_created", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="production_plans_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Production Plan",
                "verbose_name_plural": "Production Plans",
                "ordering": ["-shift_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProductionPlanBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, help_text="Label bebas, misal: 'Batch 12 - PO-2231'", max_length=100)),
                ("order", models.PositiveIntegerField(default=0, help_text="Urutan tampil bila >1 batch pada mesin yang sama")),
                ("start_offset_minutes", models.PositiveIntegerField(help_text="Menit sejak shift_start (0–1439)")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plan_batches", to="monitoring.machine")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="monitoring.productionplan")),
            ],
            options={
                "verbose_name": "Production Plan Batch",
                "verbose_name_plural": "Production Plan Batches",
                "ordering": ["machine_id", "start_offset_minutes"],
            },
        ),
        migrations.CreateModel(
            name="ProductionPlanBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phase", models.CharField(choices=[("HEAT", "Heating"), ("STEADY", "Hold / Keeping"), ("COOL", "Cooling")], max_length=10)),
                ("sequence", models.PositiveSmallIntegerField(help_text="0=Heat, 1=Hold, 2=Cool — urutan tetap dalam satu batch")),
                ("duration_minutes", models.PositiveIntegerField()),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocks", to="monitoring.productionplanbatch")),
            ],
            options={
                "verbose_name": "Production Plan Block",
                "verbose_name_plural": "Production Plan Blocks",
                "ordering": ["batch_id", "sequence"],
                "unique_together": {("batch", "sequence")},
            },
        ),
        migrations.AddIndex(
            model_name="productionplan",
            index=models.Index(fields=["shift_date", "status"], name="monitoring__shift_d_prodpl_idx"),
        ),
        migrations.AddIndex(
            model_name="productionplanbatch",
            index=models.Index(fields=["plan", "machine"], name="monitoring__plan_id_prodba_idx"),
        ),
    ]
