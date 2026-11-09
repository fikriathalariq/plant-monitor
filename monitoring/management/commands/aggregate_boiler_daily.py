from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoring.api_report import upsert_boiler_daily_metric, _get_logical_boiler_today


class Command(BaseCommand):
    help = (
        'Hitung dan simpan ringkasan KPI boiler harian ke BoilerDailyMetric. '
        'Jalankan sekali untuk backfill historis, atau otomatis via log_minute_history.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Jumlah hari ke belakang yang di-aggregate (default 30)',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Tanggal tunggal YYYY-MM-DD (override --days)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Aggregate semua hari sejak snapshot pertama tersedia',
        )

    def handle(self, *args, **options):
        from monitoring.models import MachineStatusSnapshot

        if options['date']:
            dates = [options['date']]
        elif options['all']:
            first = MachineStatusSnapshot.objects.order_by('timestamp').first()
            if not first:
                self.stdout.write(self.style.WARNING('Tidak ada snapshot.'))
                return
            logical_start = (timezone.localtime(first.timestamp) - timedelta(hours=6)).date()
            logical_today = _get_logical_boiler_today()
            dates = []
            d = logical_start
            while d <= logical_today:
                dates.append(d.strftime('%Y-%m-%d'))
                d += timedelta(days=1)
        else:
            logical_today = _get_logical_boiler_today()
            dates = [
                (logical_today - timedelta(days=i)).strftime('%Y-%m-%d')
                for i in range(options['days'] - 1, -1, -1)
            ]

        self.stdout.write(self.style.SUCCESS(f'Mengaggregate {len(dates)} hari boiler...'))

        for i, date_str in enumerate(dates, 1):
            try:
                metric = upsert_boiler_daily_metric(date_str)
                self.stdout.write(
                    f'  [{i}/{len(dates)}] {date_str} — steam {metric.total_steam_usage_kg} kg, '
                    f'SFC {metric.specific_fuel_consumption}'
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  {date_str} gagal: {e}'))

        self.stdout.write(self.style.SUCCESS('Selesai.'))
