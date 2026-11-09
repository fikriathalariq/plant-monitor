import os
import statistics
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction
from monitoring.models import DyeingIdentity, DataAnomaly

def iqr_bounds(values, multiplier=2.5):
    if len(values) < 4:
        return None, None
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    return q1 - multiplier * iqr, q3 + multiplier * iqr

class Command(BaseCommand):
    help = 'Menghitung dan menyimpan anomali data (salah linked, dsb)'

    def handle(self, *args, **kwargs):
        self.stdout.write("Memulai perhitungan anomali data...")
        
        # 1. Ambil data Identity yang memiliki batch dan program
        qs = list(
            DyeingIdentity.objects
            .filter(dyeing_process__isnull=False, program__isnull=False,
                    dyeing_process__is_valid_process=True)
            .select_related('machine', 'dyeing_process', 'program')
        )
        
        records_with_diff = []
        for r in qs:
            p, b = r.program, r.dyeing_process
            diff_suhu = (b.max_temp - p.suhu_max) if p.suhu_max and b.max_temp else None
            diff_heat = (b.heating_duration - p.durasi_heating_ideal) if p.durasi_heating_ideal and b.heating_duration is not None else None
            diff_keep = (b.steady_duration - p.durasi_keeping_ideal)  if p.durasi_keeping_ideal and b.steady_duration is not None else None
            diff_cool = (b.cooling_duration - p.durasi_cooling_ideal)  if p.durasi_cooling_ideal and b.cooling_duration is not None else None
            records_with_diff.append({
                'r': r,
                'program_name': p.nama,
                'diff_suhu': diff_suhu,
                'diff_heat': diff_heat,
                'diff_keep': diff_keep,
                'diff_cool': diff_cool,
                'ideal_suhu': p.suhu_max, 'act_suhu': b.max_temp,
                'ideal_heat': p.durasi_heating_ideal, 'act_heat': b.heating_duration,
                'ideal_keep': p.durasi_keeping_ideal, 'act_keep': b.steady_duration,
                'ideal_cool': p.durasi_cooling_ideal, 'act_cool': b.cooling_duration,
            })
            
        by_prog = defaultdict(list)
        for r in records_with_diff:
            by_prog[r['program_name']].append(r)
            
        flagged = []
        for prog_name, recs in by_prog.items():
            if len(recs) < 3:
                continue
            d_suhu = [r['diff_suhu'] for r in recs if r['diff_suhu'] is not None]
            d_heat = [r['diff_heat'] for r in recs if r['diff_heat'] is not None]
            d_keep = [r['diff_keep'] for r in recs if r['diff_keep'] is not None]
            d_cool = [r['diff_cool'] for r in recs if r['diff_cool'] is not None]
            
            lo_s, hi_s = iqr_bounds(d_suhu) if d_suhu else (None, None)
            lo_h, hi_h = iqr_bounds(d_heat) if d_heat else (None, None)
            lo_k, hi_k = iqr_bounds(d_keep) if d_keep else (None, None)
            lo_c, hi_c = iqr_bounds(d_cool) if d_cool else (None, None)
            
            for r in recs:
                f = []
                if r['diff_suhu'] is not None and lo_s is not None:
                    if r['diff_suhu'] < lo_s or r['diff_suhu'] > hi_s:
                        f.append('SUHU')
                if r['diff_heat'] is not None and lo_h is not None:
                    if r['diff_heat'] < lo_h or r['diff_heat'] > hi_h:
                        f.append('HEAT')
                if r['diff_keep'] is not None and lo_k is not None:
                    if r['diff_keep'] < lo_k or r['diff_keep'] > hi_k:
                        f.append('KEEP')
                if r['diff_cool'] is not None and lo_c is not None:
                    if r['diff_cool'] < lo_c or r['diff_cool'] > hi_c:
                        f.append('COOL')
                        
                if r['diff_suhu'] is not None and abs(r['diff_suhu']) > 25 and 'SUHU' not in f:
                    f.append('SUHU_HARD')
                    
                if f:
                    r['flags'] = f
                    r['suspicion'] = len(f)
                    flagged.append(r)

        # 2. Simpan ke database
        # Ambil SEMUA anomaly (baik resolved maupun unresolved) agar tidak double insert
        existing_anomalies_qs = DataAnomaly.objects.all()
        existing_map = { a.identity_record_id: a for a in existing_anomalies_qs if a.identity_record_id }
        
        inserted = 0
        updated = 0
        
        with transaction.atomic():
            for f_rec in flagged:
                ident = f_rec['r']
                suspicion = f_rec['suspicion']
                
                if suspicion >= 3:
                    severity = 'CRITICAL'
                elif suspicion == 2:
                    severity = 'MEDIUM'
                else:
                    severity = 'LOW'
                    
                details = {
                    'flags': f_rec['flags'],
                    'diffs': {
                        'suhu': f_rec['diff_suhu'],
                        'heat': f_rec['diff_heat'],
                        'keep': f_rec['diff_keep'],
                        'cool': f_rec['diff_cool']
                    },
                    'actuals': {
                        'suhu': f_rec['act_suhu'],
                        'heat': f_rec['act_heat'],
                        'keep': f_rec['act_keep'],
                        'cool': f_rec['act_cool']
                    },
                    'ideals': {
                        'suhu': f_rec['ideal_suhu'],
                        'heat': f_rec['ideal_heat'],
                        'keep': f_rec['ideal_keep'],
                        'cool': f_rec['ideal_cool']
                    }
                }
                
                if ident.id in existing_map:
                    # Update (hanya jika belum di-resolve manual oleh user)
                    a = existing_map[ident.id]
                    if not a.is_resolved:
                        a.severity = severity
                        a.details = details
                        a.process_record = ident.dyeing_process
                        a.save()
                        updated += 1
                else:
                    # Insert
                    DataAnomaly.objects.create(
                        identity_record=ident,
                        process_record=ident.dyeing_process,
                        anomaly_type='WRONG_LINK',
                        severity=severity,
                        details=details
                    )
                    inserted += 1
                    
        # Tandai anomali yang dulunya ada tapi sekarang sudah tidak ada sebagai SOLVED (Otomatis)
        current_anomalous_ids = set([r['r'].id for r in flagged])
        to_resolve_auto = []
        for e_id, a in existing_map.items():
            if e_id not in current_anomalous_ids and not a.is_resolved:
                to_resolve_auto.append(a.id)
                
        if to_resolve_auto:
            DataAnomaly.objects.filter(id__in=to_resolve_auto).update(
                is_resolved=True, 
                resolved_action='SOLVED',
                resolution_notes='Sistem mendeteksi data sudah kembali normal / tidak anomali lagi pada kalkulasi ulang.'
            )

        self.stdout.write(self.style.SUCCESS(f"Selesai! {inserted} baru dimasukkan, {updated} diupdate, {len(to_resolve_auto)} diselesaikan otomatis."))
