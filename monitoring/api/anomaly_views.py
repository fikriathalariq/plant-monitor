import json
from datetime import datetime
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from monitoring.models import DataAnomaly, DyeingIdentity

@require_http_methods(["GET"])
def list_anomalies(request):
    is_resolved = request.GET.get('is_resolved', 'false').lower() == 'true'
    anomalies = DataAnomaly.objects.filter(is_resolved=is_resolved).select_related('identity_record__machine', 'process_record')
    
    data = []
    for a in anomalies:
        machine_code = a.identity_record.machine.code if a.identity_record and a.identity_record.machine else '-'
        batch_number = a.process_record.batch_number if a.process_record else '-'
        batch_start = a.process_record.start_time.isoformat() if a.process_record and a.process_record.start_time else None
        
        data.append({
            'id': a.id,
            'anomaly_type': a.anomaly_type,
            'severity': a.severity,
            'machine_code': machine_code,
            'batch_number': batch_number,
            'batch_start': batch_start,
            'details': a.details,
            'is_resolved': a.is_resolved,
            'resolved_action': a.resolved_action,
            'resolution_notes': a.resolution_notes,
            'created_at': a.created_at.isoformat()
        })
        
    return JsonResponse({'status': 'success', 'data': data})

@require_http_methods(["POST"])
def resolve_anomaly(request, anomaly_id):
    try:
        anomaly = DataAnomaly.objects.get(id=anomaly_id)
    except DataAnomaly.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Anomaly not found'}, status=404)
        
    try:
        body = json.loads(request.body)
        action = body.get('action')
        notes = body.get('notes', '')
        
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
            return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
            
        anomaly.is_resolved = True
        anomaly.resolution_notes = notes
        anomaly.resolved_at = timezone.now()
        anomaly.save()
        
        return JsonResponse({'status': 'success', 'message': 'Anomaly resolved'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
