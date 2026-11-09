from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

from monitoring.models import DyeingProcess, ProductionPlan, ProductionPlanBatch, ProductionPlanBlock

SHIFT_START_HOUR = 6
EXCLUDE_MACHINES = {'Temp_RB_Steam'}
MAX_BATCH_MINUTES = 1440  # batch tunggal > 24 jam dianggap anomali data, bukan overflow wajar

def get_shift_date(start_time_utc, tz):
    local = start_time_utc.astimezone(tz)
    if local.hour < SHIFT_START_HOUR:
        return local.date() - timedelta(days=1)
    return local.date()

def get_start_offset(start_time_utc, tz):
    local = start_time_utc.astimezone(tz)
    offset = local.hour * 60 + local.minute - SHIFT_START_HOUR * 60
    return offset if offset >= 0 else offset + 1440

class Command(BaseCommand):
    help = "Import DyeingProcess aktual ke ProductionPlan (Retroaktif)"

    def add_arguments(self, parser):
        parser.add_argument('--date-from', type=str, required=True, help="Format YYYY-MM-DD")
        parser.add_argument('--date-to', type=str, required=True, help="Format YYYY-MM-DD")
        parser.add_argument('--dry-run', action='store_true', help="Hanya cetak apa yang akan diimpor")
        parser.add_argument('--overwrite', action='store_true', help="Hapus plan 'Aktual' yang sudah ada di range ini")
        parser.add_argument('--verbose', action='store_true', help="Print detail per batch")

    def handle(self, *args, **options):
        date_from_str = options['date_from']
        date_to_str = options['date_to']
        dry_run = options['dry_run']
        overwrite = options['overwrite']
        verbose = options['verbose']

        tz = pytz.timezone('Asia/Jakarta')
        try:
            dt_from = tz.localize(datetime.strptime(date_from_str, '%Y-%m-%d'))
            dt_to = tz.localize(datetime.strptime(date_to_str, '%Y-%m-%d')).replace(hour=23, minute=59, second=59)
        except ValueError:
            self.stdout.write(self.style.ERROR("Format tanggal harus YYYY-MM-DD"))
            return

        with transaction.atomic():
            # Mesin operation_mode='MANUAL' (mis. SPP/SSD continuous processing) TIDAK diimpor
            # dari sini -- jalur resminya adalah `import_manual_to_plan.py` (sumber data
            # MachineManualLog, bukan DyeingProcess). Command itu SUDAH ADA sebelum sesi ini dan
            # sudah menangani cross-day-nya sendiri (memecah sesi ON di batas shift 06:00). Lihat
            # PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §9. Exclude eksplisit di sini murni
            # defensif agar command ini tidak pernah menyentuh mesin MANUAL (mencegah duplikasi/
            # overlap kalau suatu saat ada baris DyeingProcess nyasar untuk mesin MANUAL).
            processes = DyeingProcess.objects.filter(
                start_time__gte=dt_from,
                start_time__lte=dt_to,
                is_complete=True,
                is_valid_process=True
            ).exclude(machine__code__in=EXCLUDE_MACHINES).exclude(
                machine__operation_mode='MANUAL'
            ).select_related('machine').order_by('start_time')

            if overwrite and not dry_run:
                # Find and delete only "Aktual * (Import)" plans in this date range
                plans_to_delete = ProductionPlan.objects.filter(
                    shift_date__gte=dt_from.date(),
                    shift_date__lte=dt_to.date(),
                    name__startswith="Aktual ",
                    name__endswith=" (Import)"
                )
                del_count = plans_to_delete.count()
                plans_to_delete.delete()
                self.stdout.write(self.style.WARNING(f"Menghapus {del_count} plan 'Aktual (Import)' yang ada (overwrite)."))

            plans_cache = {}
            stats = {'created': 0, 'skipped': 0, 'skipped_zero': 0}

            # To avoid duplicates if not overwriting
            skip_shift_dates = set()
            if not overwrite and not dry_run:
                existing_plans = ProductionPlan.objects.filter(
                    shift_date__gte=dt_from.date(),
                    shift_date__lte=dt_to.date(),
                    name__startswith="Aktual ",
                    name__endswith=" (Import)"
                ).prefetch_related('batches')
                for p in existing_plans:
                    if p.batches.exists():
                        skip_shift_dates.add(p.shift_date)

            for proc in processes:
                # Semua baris di sini sudah pasti mesin AUTO (MANUAL dikecualikan di query di atas).
                # HEAT: pakai real_heating_duration (rise time aktual heating_start -> steady_start),
                # sama seperti yang ditampilkan di halaman report (api_report.py, api_batch_detail.py,
                # views.py). heating_duration (cacah menit thermal_state=='HEAT') TIDAK dipakai lagi
                # karena selisih signifikan dengan yang ditampilkan report (lihat investigasi 507 proses).
                heat = max(0, round(proc.real_heating_duration or 0))
                steady = max(0, round(proc.steady_duration or 0))
                # COOL: cooling_duration sudah sama dengan field yang dipakai report untuk cool_actual/
                # actual_cooling, jadi TIDAK diubah (lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md §0/§7 Q1).
                cool = max(0, round(proc.cooling_duration or 0))
                total = heat + steady + cool
                blocks_spec = [
                    ('HEAT', 0, heat),
                    ('STEADY', 1, steady),
                    ('COOL', 2, cool),
                ]

                if total > MAX_BATCH_MINUTES:
                    if verbose:
                        self.stdout.write(f"SKIP batch {proc}: total_duration={total} > {MAX_BATCH_MINUTES} (anomali)")
                    stats['skipped'] += 1
                    continue

                if total <= 0:
                    if verbose:
                        self.stdout.write(f"SKIP batch {proc}: total_duration=0")
                    stats['skipped_zero'] += 1
                    continue

                shift_date = get_shift_date(proc.start_time, tz)
                if shift_date in skip_shift_dates:
                    if verbose:
                        self.stdout.write(f"SKIP batch {proc}: Plan untuk shift {shift_date} sudah ada.")
                    stats['skipped'] += 1
                    continue

                start_offset = get_start_offset(proc.start_time, tz)

                if shift_date not in plans_cache:
                    if not dry_run:
                        plan, _ = ProductionPlan.objects.get_or_create(
                            shift_date=shift_date,
                            name=f"Aktual {shift_date} (Import)",
                            defaults={
                                'status': 'PUBLISHED',
                                'notes': 'Diimpor otomatis dari DyeingProcess aktual sensor.'
                            }
                        )
                        plans_cache[shift_date] = plan
                    else:
                        plans_cache[shift_date] = "DRY_RUN_PLAN"

                plan = plans_cache[shift_date]

                # Batch TIDAK dipotong lagi walau start_offset + total > 1440 (meluber ke shift
                # hari berikutnya) -- lihat PLANNING_V3_IMPORT_FIX_AND_CROSSDAY_PLAN.md Bagian II.
                # Batch tetap diasosiasikan dengan plan hari ini (shift_date), bukan dipecah.
                overflow_note = ""
                if start_offset + total > 1440:
                    overflow_note = f" [lanjut {start_offset + total - 1440}m ke hari berikutnya]"

                label = f"Batch #{proc.batch_number}"

                if not dry_run:
                    batch = ProductionPlanBatch.objects.create(
                        plan=plan,
                        machine=proc.machine,
                        program=None,
                        label=label,
                        start_offset_minutes=start_offset
                    )
                    ProductionPlanBlock.objects.bulk_create([
                        ProductionPlanBlock(batch=batch, phase=phase, sequence=seq, duration_minutes=dur)
                        for phase, seq, dur in blocks_spec
                    ])

                if verbose:
                    detail = ' '.join(f"{phase}={dur}" for phase, _, dur in blocks_spec)
                    self.stdout.write(
                        f"CREATE {label} on {proc.machine.code} (AUTO) offset={start_offset} {detail}{overflow_note}"
                    )

                stats['created'] += 1

            action = "DIIMPOR" if not dry_run else "AKAN DIIMPOR (DRY RUN)"
            self.stdout.write(self.style.SUCCESS(
                f"Selesai: {stats['created']} batch {action}, "
                f"{stats['skipped']} diskip (anomali/plan ada), {stats['skipped_zero']} diskip (durasi 0)."
            ))
