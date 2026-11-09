from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Dict, Any, Optional
from datetime import datetime
from django.utils import timezone
from monitoring.models import DataAnomaly, DyeingIdentity
from monitoring.decorators import user_can_access_page

anomaly_router = Router(tags=["Anomalies"])

PAGE_CODE = "anomaly_detection"


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


from datetime import datetime, time, timedelta
import pytz
from django.conf import settings
from django.core.cache import cache
from .models import AnomalyRuleConfig, DataAnomaly

def get_anomaly_label_map():
    mapping = cache.get('anomaly_label_map')
    if mapping is None:
        rules = AnomalyRuleConfig.objects.filter(is_active=True)
        mapping = {r.adds_flag: (r.display_label or r.adds_flag.title()) for r in rules}
        mapping.setdefault('REHEATING', 'Re-Heating (≥2x Naik)')
        mapping.setdefault('KEEP', 'Hold')
        mapping.setdefault('HEAT', 'Heat')
        mapping.setdefault('SUHU', 'Suhu')
        mapping.setdefault('COOL', 'Cool')
        mapping.setdefault('SUHU_HARD', 'Suhu Ekstrem (>25°C)')
        mapping.setdefault('OVER_HOLD', 'Over-Holding (>8m)')
        mapping.setdefault('LATE_STOP', 'Pasca-Cooling (>45m)')
        mapping.setdefault('COOL_STAGNATION', 'Stagnasi Cooling')
        mapping.setdefault('SLOW_COOL', 'Cooling Lambat')
        mapping.setdefault('MID_HEAT_PAUSE', 'Jeda Heating')
        mapping.setdefault('START_TEMP_HIGH', 'Suhu Awal Tinggi (>60°C)')
        cache.set('anomaly_label_map', mapping, 3600)
    else:
        mapping.setdefault('REHEATING', 'Re-Heating (≥2x Naik)')
        mapping.setdefault('KEEP', 'Hold')
        mapping.setdefault('HEAT', 'Heat')
        mapping.setdefault('SUHU', 'Suhu')
        mapping.setdefault('COOL', 'Cool')
        mapping.setdefault('SUHU_HARD', 'Suhu Ekstrem (>25°C)')
        mapping.setdefault('OVER_HOLD', 'Over-Holding (>8m)')
        mapping.setdefault('LATE_STOP', 'Pasca-Cooling (>45m)')
        mapping.setdefault('COOL_STAGNATION', 'Stagnasi Cooling')
        mapping.setdefault('SLOW_COOL', 'Cooling Lambat')
        mapping.setdefault('MID_HEAT_PAUSE', 'Jeda Heating')
        mapping.setdefault('START_TEMP_HIGH', 'Suhu Awal Tinggi (>60°C)')
    return mapping

def map_anomaly_flags(flags_list):
    label_map = get_anomaly_label_map()
    types = []
    for f in flags_list:
        label = label_map.get(f, str(f).title())
        if label not in types:
            types.append(label)
    return sorted(types)

class ResolveAnomalyIn(Schema):
    action: str
    notes: Optional[str] = ""

@anomaly_router.get("/")
def list_anomalies(request, is_resolved: Optional[bool] = None, date: Optional[str] = None):
    _require_permission(request)
    qs = DataAnomaly.objects.all()
    if is_resolved is not None:
        qs = qs.filter(is_resolved=is_resolved)
    
    if date:
        tz = pytz.timezone(settings.TIME_ZONE)
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            start_shift = tz.localize(datetime.combine(target_date, time(6, 0)))
            end_shift = start_shift + timedelta(days=1)
            
            qs = qs.filter(
                process_record__start_time__gte=start_shift,
                process_record__start_time__lt=end_shift
            )
        except ValueError:
            pass
            
    qs = qs.select_related('identity_record__machine', 'identity_record__program', 'process_record').order_by('-created_at')
    
    summary = {}
    data = []
    
    for a in qs:
        machine_code = a.identity_record.machine.code if a.identity_record and a.identity_record.machine else '-'
        batch_number = a.process_record.batch_number if a.process_record else '-'
        batch_start = a.process_record.start_time.isoformat() if a.process_record and a.process_record.start_time else None
        
        program_name = a.identity_record.program.nama if a.identity_record and a.identity_record.program else '-'
        artikel_kain = a.identity_record.artikel_kain if a.identity_record else '-'
        nomor_order = a.identity_record.nomor_order if a.identity_record else '-'
        batch_kain = a.identity_record.batch if a.identity_record else '-'
        jenis_proses = a.identity_record.get_jenis_proses_display() if a.identity_record and a.identity_record.jenis_proses else '-'

        flags = a.details.get("flags", []) if isinstance(a.details, dict) else []
        mapped_types = map_anomaly_flags(flags)
        
        for t in mapped_types:
            summary[t] = summary.get(t, 0) + 1
            
        data.append({
            'id': a.id,
            'process_record_id': a.process_record_id,
            'anomaly_type': a.anomaly_type,
            'severity': a.severity,
            'machine_code': machine_code,
            'batch_number': batch_number,
            'batch_start': batch_start,
            'program_name': program_name,
            'artikel_kain': artikel_kain,
            'nomor_order': nomor_order,
            'batch_kain': batch_kain,
            'jenis_proses': jenis_proses,
            'details': a.details,
            'anomaly_types': mapped_types,
            'is_resolved': a.is_resolved,
            'resolved_action': a.resolved_action,
            'resolution_notes': a.resolution_notes,
            'created_at': a.created_at.isoformat()
        })
        
    return {
        'status': 'success', 
        'summary': {'total_batches': len(qs), 'breakdown': summary}, 
        'data': data
    }

@anomaly_router.post("/{anomaly_id}/resolve/")
def resolve_anomaly(request, anomaly_id: int, payload: ResolveAnomalyIn):
    _require_permission(request)
    try:
        anomaly = DataAnomaly.objects.get(id=anomaly_id)
    except DataAnomaly.DoesNotExist:
        return 404, {'status': 'error', 'message': 'Anomaly not found'}
        
    action = payload.action
    notes = payload.notes
    
    ident = anomaly.identity_record
    process = anomaly.process_record
    
    if action == 'UNLINK':
        if ident:
            ident.dyeing_process = None
            ident.save(update_fields=['dyeing_process'])
        anomaly.resolved_action = 'UNLINKED'
        
    elif action == 'INVALIDATE':
        if process:
            process.is_valid_process = False
            process.save(update_fields=['is_valid_process'])
        anomaly.resolved_action = 'INVALIDATED'
        
    elif action == 'SOLVE':
        anomaly.resolved_action = 'SOLVED'
        
    else:
        return 400, {'status': 'error', 'message': 'Invalid action'}
        
    anomaly.is_resolved = True
    anomaly.resolution_notes = notes
    anomaly.resolved_at = timezone.now()
    anomaly.save()
    
    return {'status': 'success', 'message': 'Anomaly resolved'}

from monitoring.models import AnomalyThresholdProposal

class ProposalActionIn(Schema):
    action: str # APPROVE or REJECT

@anomaly_router.get("/proposals/")
def list_proposals(request, status: str = 'DRAFT'):
    _require_permission(request)
    proposals = AnomalyThresholdProposal.objects.filter(status=status).select_related('master__machine', 'master__program')
    data = []
    for p in proposals:
        data.append({
            'id': p.id,
            'machine_code': p.master.machine.code if p.master and p.master.machine else '-',
            'program_name': p.master.program.nama if p.master and p.master.program else '-',
            'week_start': p.week_start_date.isoformat(),
            'week_end': p.week_end_date.isoformat(),
            'new_data_count': p.new_data_count,
            'outlier_rejected_count': p.outlier_rejected_count,
            'is_warning': p.is_warning,
            'warning_message': p.warning_message,
            'status': p.status,
            'suhu_bounds': [p.suhu_lower_bound_new, p.suhu_upper_bound_new],
            'heat_bounds': [p.heat_lower_bound_new, p.heat_upper_bound_new],
            'keep_bounds': [p.keep_lower_bound_new, p.keep_upper_bound_new],
            'cool_bounds': [p.cool_lower_bound_new, p.cool_upper_bound_new],
        })
    return {'status': 'success', 'data': data}

@anomaly_router.post("/proposals/{proposal_id}/action/")
def action_proposal(request, proposal_id: int, payload: ProposalActionIn):
    _require_permission(request)
    try:
        proposal = AnomalyThresholdProposal.objects.get(id=proposal_id)
    except AnomalyThresholdProposal.DoesNotExist:
        return 404, {'status': 'error', 'message': 'Proposal not found'}
        
    if proposal.status != 'DRAFT':
        return 400, {'status': 'error', 'message': 'Proposal already processed'}
        
    if payload.action == 'APPROVE':
        master = proposal.master
        # Overwrite master values
        master.suhu_mean = proposal.suhu_mean_new or master.suhu_mean
        master.suhu_stddev = proposal.suhu_stddev_new or master.suhu_stddev
        master.suhu_lower_bound = proposal.suhu_lower_bound_new
        master.suhu_upper_bound = proposal.suhu_upper_bound_new
        master.suhu_count += proposal.new_data_count
        
        master.heat_mean = proposal.heat_mean_new or master.heat_mean
        master.heat_stddev = proposal.heat_stddev_new or master.heat_stddev
        master.heat_lower_bound = proposal.heat_lower_bound_new
        master.heat_upper_bound = proposal.heat_upper_bound_new
        master.heat_count += proposal.new_data_count
        
        master.keep_mean = proposal.keep_mean_new or master.keep_mean
        master.keep_stddev = proposal.keep_stddev_new or master.keep_stddev
        master.keep_lower_bound = proposal.keep_lower_bound_new
        master.keep_upper_bound = proposal.keep_upper_bound_new
        master.keep_count += proposal.new_data_count
        
        master.cool_mean = proposal.cool_mean_new or master.cool_mean
        master.cool_stddev = proposal.cool_stddev_new or master.cool_stddev
        master.cool_lower_bound = proposal.cool_lower_bound_new
        master.cool_upper_bound = proposal.cool_upper_bound_new
        master.cool_count += proposal.new_data_count
        
        master.save()
        
        proposal.status = 'APPROVED'
        proposal.processed_at = timezone.now()
        proposal.save()
        
    elif payload.action == 'REJECT':
        proposal.status = 'REJECTED'
        proposal.processed_at = timezone.now()
        proposal.save()
    else:
        return 400, {'status': 'error', 'message': 'Invalid action'}
        
    return {'status': 'success', 'message': f'Proposal {payload.action}D'}
