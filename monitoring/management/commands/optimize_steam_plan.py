import re
import statistics
from datetime import timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from monitoring.models import ProductionPlan, ProductionPlanBatch, ProductionPlanBlock, DyeingProcess, Machine

class Command(BaseCommand):
    help = 'Optimasi penjadwalan uap untuk Production Planning (Steam Levelling)'

    def add_arguments(self, parser):
        parser.add_argument('--date-from', type=str, required=True, help='YYYY-MM-DD')
        parser.add_argument('--date-to', type=str, required=True, help='YYYY-MM-DD')
        parser.add_argument('--target-steam', type=float, default=6000.0, help='Target Max Steam kg/h')
        parser.add_argument('--dry-run', action='store_true', help='Jalankan simulasi tanpa save ke DB')

    def handle(self, *args, **options):
        from datetime import datetime
        
        date_from = datetime.strptime(options['date_from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(options['date_to'], '%Y-%m-%d').date()
        target_steam = options['target_steam']
        dry_run = options['dry_run']

        self.stdout.write("Membaca data referensi...")
        machines = Machine.objects.select_related('group').all()
        steam_usage = {m.code: m.average_steam_usage or 0 for m in machines}
        operation_mode = {m.code: m.operation_mode for m in machines}
        machine_groups = {m.code: m.group for m in machines}

        # Baseline IQR (Durasi Ideal untuk >110C)
        baseline_data = {
            'JD_01': (187.8, 57.5, 72.8), 'JD_03': (125.7, 33.6, 63.3), 'JD_04': (116.0, 38.7, 57.0),
            'JD_08': (150.5, 52.8, 76.4), 'JD_09': (120.9, 45.2, 47.0), 'JD_10': (119.1, 49.8, 69.4),
            'JD_11': (133.7, 58.0, 38.0), 'JD_12': (105.0, 46.6, 46.1), 'JD_13': (115.1, 44.8, 46.5),
            'JD_14': (114.9, 52.1, 40.1), 'JD_15': (154.5, 52.3, 53.0), 'JD_16': (126.7, 55.1, 52.8),
            'JD_18': (141.8, 45.7, 56.0), 'JD_19': (185.2, 53.9, 39.1), 'JD_JetMini': (142.9, 45.5, 74.8),
            'JR_02': (165.1, 41.4, 56.8), 'JR_03': (146.1, 43.3, 48.7), 'JR_04': (164.3, 55.4, 62.6),
            'JR_05': (141.5, 55.0, 52.6), 'JR_06': (101.0, 55.7, 94.7), 'JR_07': (138.6, 45.1, 42.9),
            'JR_08': (124.3, 48.8, 51.2), 'JR_09': (129.7, 46.6, 57.4), 'JR_11': (175.6, 60.8, 79.1),
            'JR_12': (119.8, 62.0, 33.5), 'JR_13': (108.1, 53.4, 32.6), 'ZET_06': (140.5, 35.7, 32.5),
            'ZET_07': (141.3, 44.7, 26.5), 'ZET_08': (153.4, 55.8, 19.0), 'ZET_10': (144.9, 24.2, 35.2),
            'ZET_11': (135.6, 35.1, 43.0),
        }

        self.stdout.write(f"Mengambil batch dari {date_from} sampai {date_to}...")
        batches = ProductionPlanBatch.objects.filter(
            plan__shift_date__gte=date_from,
            plan__shift_date__lte=date_to
        ).select_related('plan', 'machine').prefetch_related('blocks')

        records = []
        for b in batches:
            day_idx = (b.plan.shift_date - date_from).days
            start_abs = day_idx * 1440 + b.start_offset_minutes
            blocks = list(b.blocks.all().order_by('sequence'))
            orig_total_dur = sum(block.duration_minutes for block in blocks)
            
            max_temp = 0
            avg_pressure = 0.0
            m = re.search(r'Batch #(\d+)', b.label)
            if m:
                proc = DyeingProcess.objects.filter(machine=b.machine, batch_number=m.group(1)).first()
                if proc:
                    if proc.max_temp:
                        max_temp = proc.max_temp
                    if proc.avg_steam_pressure:
                        avg_pressure = proc.avg_steam_pressure

            records.append({
                'batch_obj': b,
                'machine_code': b.machine.code,
                'original_start_abs': start_abs,
                'original_end_abs': start_abs + orig_total_dur,
                'orig_total_dur': orig_total_dur,
                'max_temp': max_temp,
                'avg_pressure': avg_pressure,
                'blocks': blocks,
                'mode': operation_mode.get(b.machine.code, 'AUTO')
            })

        # Urutkan berdasarkan waktu mulai absolut asli
        records.sort(key=lambda x: x['original_start_abs'])

        # Global steam tracking
        # 30 days buffer ahead
        TOTAL_MINUTES = ((date_to - date_from).days + 30) * 1440 
        global_steam = [0.0] * TOTAL_MINUTES

        machine_state = {}
        updates = []

        for r in records:
            mc = r['machine_code']
            usage = steam_usage.get(mc, 0)
            mode = r['mode']
            
            is_opt = False
            baseline_dur = 0
            
            if mode == 'AUTO' and r['max_temp'] > 110 and r['avg_pressure'] < 3.5 and mc in baseline_data:
                heat, hold, cool = baseline_data[mc]
                baseline_dur = heat + hold + cool
                new_blocks = [
                    {'phase': 'HEAT', 'duration': int(round(heat))},
                    {'phase': 'STEADY', 'duration': int(round(hold))},
                    {'phase': 'COOL', 'duration': int(round(cool))}
                ]
                is_opt = True
            else:
                new_blocks = [{'phase': blk.phase, 'duration': blk.duration_minutes} for blk in r['blocks']]
                
            new_total_dur = sum(blk['duration'] for blk in new_blocks)
            new_steam_dur = sum(blk['duration'] for blk in new_blocks if blk['phase'] in ['HEAT', 'STEADY', 'RUNNING'])
            
            if mc in machine_state:
                prev = machine_state[mc]
                real_gap = r['original_start_abs'] - prev['orig_end_abs']
                
                if real_gap > 120:
                    E_start = max(r['original_start_abs'], prev['new_end_abs'])
                else:
                    allowed_min_gap = min(60, max(0, real_gap))
                    E_start = prev['new_end_abs'] + allowed_min_gap
                    
                    if is_opt:
                        max_early_shift = baseline_dur * 0.5
                    else:
                        max_early_shift = r['orig_total_dur'] * 0.5
                        
                    absolute_earliest = r['original_start_abs'] - max_early_shift
                    if E_start < absolute_earliest:
                        E_start = int(absolute_earliest)
            else:
                E_start = r['original_start_abs']
                
            O_start = E_start
            while O_start + new_steam_dur < TOTAL_MINUTES:
                window = global_steam[O_start : O_start + new_steam_dur]
                if not window:
                    break
                if max(window) + usage <= target_steam:
                    break 
                O_start += 1
                if O_start - E_start > 720: # 12 hours escape valve
                    break

            for i in range(O_start, min(O_start + new_steam_dur, TOTAL_MINUTES)):
                global_steam[i] += usage
                
            machine_state[mc] = {
                'orig_end_abs': r['original_end_abs'],
                'new_end_abs': O_start + new_total_dur
            }
            
            # Siapkan data update
            new_day_idx = O_start // 1440
            new_offset = O_start % 1440
            new_shift_date = date_from + timedelta(days=new_day_idx)
            
            updates.append({
                'batch_obj': r['batch_obj'],
                'new_shift_date': new_shift_date,
                'new_offset': new_offset,
                'new_blocks': new_blocks,
                'mc': mc
            })
            
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN SELESAI. {len(updates)} batch diproses. Max steam: {max(global_steam):.1f} kg/h"))
            return

        self.stdout.write("Menyimpan hasil optimasi ke database...")
        plan_cache = {}
        def get_plan(shift_date):
            cache_key = shift_date
            if cache_key not in plan_cache:
                plan, _ = ProductionPlan.objects.get_or_create(
                    shift_date=shift_date,
                    name=f"Aktual {shift_date} (Import)",
                    defaults={'status': 'PUBLISHED'}
                )
                plan_cache[cache_key] = plan
            return plan_cache[cache_key]

        with transaction.atomic():
            for u in updates:
                batch = u['batch_obj']
                group = machine_groups[u['mc']]
                
                # Update plan & offset
                new_plan = get_plan(u['new_shift_date'])
                batch.plan = new_plan
                batch.start_offset_minutes = u['new_offset']
                batch.save(update_fields=['plan', 'start_offset_minutes'])
                
                # Hapus blok lama & buat baru
                batch.blocks.all().delete()
                
                new_block_objs = []
                for idx, blk in enumerate(u['new_blocks']):
                    new_block_objs.append(ProductionPlanBlock(
                        batch=batch,
                        phase=blk['phase'],
                        sequence=idx,
                        duration_minutes=blk['duration']
                    ))
                ProductionPlanBlock.objects.bulk_create(new_block_objs)

        self.stdout.write(self.style.SUCCESS(f"Optimasi berhasil. {len(updates)} batch diperbarui. Max steam: {max(global_steam):.1f} kg/h"))
