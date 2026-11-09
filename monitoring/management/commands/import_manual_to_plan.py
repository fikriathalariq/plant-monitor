from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

from monitoring.models import Machine, MachineManualLog, ProductionPlan, ProductionPlanBatch, ProductionPlanBlock

SHIFT_START_HOUR = 6
RUNNING_STATUSES = {'Running'}
STOP_STATUSES = {'Stop'}

def reconstruct_sessions(logs_for_machine, range_end):
    sessions = []
    current_on = None

    for log in logs_for_machine:
        if log.new_status in RUNNING_STATUSES and current_on is None:
            current_on = log.timestamp
        elif log.new_status in STOP_STATUSES and current_on is not None:
            sessions.append((current_on, log.timestamp, False))
            current_on = None

    if current_on is not None:
        sessions.append((current_on, range_end, True))

    return sessions


def split_session_to_shifts(on_time, off_time, tz, is_open_ended):
    results = []
    cursor = on_time.astimezone(tz)
    end = off_time.astimezone(tz)

    while cursor < end:
        if cursor.hour < SHIFT_START_HOUR:
            shift_date = cursor.date() - timedelta(days=1)
            this_shift_end = tz.localize(datetime(cursor.year, cursor.month, cursor.day, SHIFT_START_HOUR, 0, 0))
        else:
            shift_date = cursor.date()
            next_day = cursor.date() + timedelta(days=1)
            this_shift_end = tz.localize(datetime(next_day.year, next_day.month, next_day.day, SHIFT_START_HOUR, 0, 0))

        segment_end = min(end, this_shift_end)
        
        start_offset = (cursor.hour * 60 + cursor.minute) - SHIFT_START_HOUR * 60
        if start_offset < 0:
            start_offset += 1440
            
        duration = round((segment_end - cursor).total_seconds() / 60.0)

        if duration > 0:
            is_last = segment_end >= end
            results.append({
                'shift_date': shift_date,
                'start_offset': start_offset,
                'duration': duration,
                'is_open_ended': is_open_ended and is_last,
            })

        cursor = segment_end

    return results

class Command(BaseCommand):
    help = "Import MachineManualLog aktual ke ProductionPlan (MANUAL Machines)"

    def add_arguments(self, parser):
        parser.add_argument('--date-from', type=str, required=True, help="Format YYYY-MM-DD")
        parser.add_argument('--date-to', type=str, required=True, help="Format YYYY-MM-DD")
        parser.add_argument('--dry-run', action='store_true', help="Hanya cetak apa yang akan diimpor")
        parser.add_argument('--overwrite', action='store_true', help="Hapus batch MANUAL yang sudah ada di range ini pada plan 'Aktual'")
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

        manual_machines = Machine.objects.filter(operation_mode='MANUAL', is_active=True).order_by('code')

        with transaction.atomic():
            if overwrite and not dry_run:
                batches_to_delete = ProductionPlanBatch.objects.filter(
                    plan__shift_date__gte=dt_from.date(),
                    plan__shift_date__lte=dt_to.date(),
                    plan__name__startswith="Aktual ",
                    plan__name__endswith=" (Import)",
                    machine__operation_mode='MANUAL'
                )
                del_count = batches_to_delete.count()
                batches_to_delete.delete()
                self.stdout.write(self.style.WARNING(f"Menghapus {del_count} batch MANUAL yang ada (overwrite)."))

            plans_cache = {}
            
            # Populate plans cache if not overwrite
            if not dry_run:
                existing_plans = ProductionPlan.objects.filter(
                    shift_date__gte=dt_from.date(),
                    shift_date__lte=dt_to.date(),
                    name__startswith="Aktual ",
                    name__endswith=" (Import)"
                )
                for p in existing_plans:
                    plans_cache[p.shift_date] = p

            stats = {'created': 0, 'skipped': 0, 'open_ended': 0}
            
            for machine in manual_machines:
                logs = MachineManualLog.objects.filter(
                    machine=machine,
                    timestamp__gte=dt_from,
                    timestamp__lte=dt_to
                ).order_by('timestamp')

                sessions = reconstruct_sessions(logs, dt_to)

                if not sessions:
                    if verbose:
                        self.stdout.write(f"SKIP {machine.code}: tidak ada log di range ini")
                    stats['skipped'] += 1
                    continue
                
                for on_time, off_time, is_open_ended in sessions:
                    segments = split_session_to_shifts(on_time, off_time, tz, is_open_ended)

                    for seg in segments:
                        # Skip micro-segments (e.g. less than 1 min)
                        if seg['duration'] < 1:
                            continue

                        shift_date = seg['shift_date']
                        
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
                        
                        label = f"MANUAL {machine.code}"
                        if seg['is_open_ended']:
                            label += " [MASIH JALAN]"
                            stats['open_ended'] += 1

                        if not dry_run:
                            # Verify if a batch already exists to prevent duplicate on re-runs without --overwrite
                            existing_batch = ProductionPlanBatch.objects.filter(
                                plan=plan, 
                                machine=machine, 
                                start_offset_minutes=seg['start_offset']
                            ).exists()
                            
                            if not existing_batch:
                                batch = ProductionPlanBatch.objects.create(
                                    plan=plan,
                                    machine=machine,
                                    program=None,
                                    label=label,
                                    start_offset_minutes=seg['start_offset']
                                )
                                ProductionPlanBlock.objects.create(
                                    batch=batch, 
                                    phase='RUNNING', 
                                    sequence=0, 
                                    duration_minutes=seg['duration']
                                )
                                stats['created'] += 1
                            else:
                                if verbose:
                                    self.stdout.write(f"SKIP {machine.code} on {shift_date}: batch already exists")
                        else:
                            if verbose:
                                self.stdout.write(f"CREATE {label} on {machine.code} shift={shift_date} offset={seg['start_offset']} dur={seg['duration']}")
                            stats['created'] += 1

            action = "DIIMPOR" if not dry_run else "AKAN DIIMPOR (DRY RUN)"
            self.stdout.write(self.style.SUCCESS(
                f"Selesai: {stats['created']} batch (segmen) {action}, "
                f"{stats['skipped']} mesin tanpa log di-skip. "
                f"{stats['open_ended']} segmen ditandai [MASIH JALAN]."
            ))
