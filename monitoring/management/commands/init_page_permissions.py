from django.core.management.base import BaseCommand
from monitoring.models import PagePermission


class Command(BaseCommand):
    help = 'Initialize default page permissions for the system'

    def handle(self, *args, **options):
        """
        Create or update page permission entries for all available pages.
        This command is idempotent - safe to run multiple times.
        """
        pages = [
            {
                'code': 'dashboard',
                'name': 'Dashboard',
                'url_name': 'dashboard',
                'description': 'Halaman utama dengan status mesin dan KPI realtime'
            },
            {
                'code': 'manual_input',
                'name': 'Manual Input',
                'url_name': 'manual_machine_usage',
                'description': 'Halaman untuk input manual status mesin'
            },
            {
                'code': 'history',
                'name': 'History',
                'url_name': 'history_list',
                'description': 'Daftar history batch proses dyeing'
            },
            {
                'code': 'history_report',
                'name': 'History Report',
                'url_name': 'history_report',
                'description': 'Detail laporan batch proses dyeing'
            },
            {
                'code': 'analytics',
                'name': 'Analytics',
                'url_name': 'graph_menu',
                'description': 'Halaman grafik dan analisis data'
            },
            {
                'code': 'engineer_workspace',
                'name': 'Engineer Workspace',
                'url_name': 'engineer_workspace',
                'description': 'Workspace engineer energy: command center, inspeksi, perhitungan'
            },
            {
                'code': 'snapshot_history',
                'name': 'Snapshot History',
                'url_name': 'snapshot_history',
                'description': 'Pivot table histori snapshot status mesin'
            },
            {
                'code': 'performance_summary',
                'name': 'Performance Summary',
                'url_name': 'machine_performance_summary',
                'description': 'Ringkasan performa mesin berdasarkan agregasi batch dyeing'
            },
            {
                'code': 'daily_batch_overview',
                'name': 'Daily Batch Overview',
                'url_name': 'daily_batch_overview',
                'description': 'Daftar batch dyeing yang berjalan/selesai pada satu tanggal'
            },
            {
                'code': 'daily_report',
                'name': 'Daily Report',
                'url_name': '(React SPA — /daily-report)',
                'description': 'Laporan harian steam traffic, heatmap, dan availability mesin'
            },
            {
                'code': 'machine_daily_report',
                'name': 'Machine Daily Report',
                'url_name': '(React SPA — /machine-daily-report)',
                'description': 'Laporan harian per mesin: availability, efisiensi, dan histori batch'
            },
            {
                'code': 'monthly_report',
                'name': 'Monthly Report',
                'url_name': '(React SPA — /monthly-report)',
                'description': 'Laporan bulanan steam traffic dan histori proses dyeing'
            },
            {
                'code': 'boiler_report',
                'name': 'Boiler Report',
                'url_name': '(React SPA — /boiler-report)',
                'description': 'Laporan harian KPI boiler: tekanan, suhu oli, dan konsumsi bahan bakar'
            },
            {
                'code': 'boiler_calendar',
                'name': 'Boiler Calendar',
                'url_name': '(React SPA — /boiler-calendar)',
                'description': 'Kalender bulanan ringkasan KPI boiler per hari'
            },
            {
                'code': 'anomaly_detection',
                'name': 'Deteksi Anomali',
                'url_name': '(React SPA — /anomalies)',
                'description': 'Daftar anomali data batch (salah linked, sensor spike, dsb.)'
            },
            {
                'code': 'jumo_live_monitor',
                'name': 'JUMO Live Monitor',
                'url_name': '(React SPA — /jumo-live)',
                'description': 'Diagnosa langsung channel/controller JUMO via Modbus'
            },
            {
                'code': 'dyeing_identities',
                'name': 'Dyeing Identities',
                'url_name': '(React SPA — /dyeing-identities)',
                'description': 'Manajemen identitas produksi (nomor order, artikel kain, dsb.)'
            },
        ]

        created_count = 0
        updated_count = 0

        for page_data in pages:
            page, created = PagePermission.objects.update_or_create(
                code=page_data['code'],
                defaults={
                    'name': page_data['name'],
                    'url_name': page_data['url_name'],
                    'description': page_data.get('description', ''),
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'[+] Created: {page.name} ({page.code})')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'[*] Updated: {page.name} ({page.code})')
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully initialized {len(pages)} page permissions '
                f'({created_count} created, {updated_count} updated)'
            )
        )
        self.stdout.write('')
        self.stdout.write(
            'Next steps:'
        )
        self.stdout.write(
            '  1. Go to Django Admin - Positions'
        )
        self.stdout.write(
            '  2. Edit each position and assign allowed pages'
        )
        self.stdout.write(
            '  3. Ensure operator profiles have positions assigned'
        )
