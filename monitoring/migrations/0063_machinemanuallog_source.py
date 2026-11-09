from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0062_boilerdailymetric'),
    ]

    operations = [
        migrations.AddField(
            model_name='machinemanuallog',
            name='source',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Sumber perubahan: dashboard_toggle, mesin_aktif_api, sync_command, dll.',
                max_length=30,
            ),
        ),
    ]
