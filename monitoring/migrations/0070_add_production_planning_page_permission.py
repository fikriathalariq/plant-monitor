# Data migration: PagePermission for production_planning

from django.db import migrations


def add_page_permission(apps, schema_editor):
    PagePermission = apps.get_model("monitoring", "PagePermission")
    PagePermission.objects.get_or_create(
        code="production_planning",
        defaults={
            "name": "Perencanaan Produksi",
            "url_name": "production_planning",
            "description": "Papan perencanaan proses Heat/Hold/Cool per mesin",
            "is_active": True,
        },
    )


def remove_page_permission(apps, schema_editor):
    PagePermission = apps.get_model("monitoring", "PagePermission")
    PagePermission.objects.filter(code="production_planning").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0069_production_planning"),
    ]

    operations = [
        migrations.RunPython(add_page_permission, remove_page_permission),
    ]
