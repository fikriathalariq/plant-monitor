import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os

code = """
import pytz
from django.utils.dateparse import parse_datetime

def apidog_dyeing_process_lookup_api(request):
    \"\"\"
    Lookup DyeingProcess by machine_code and time.
    Returns batch summary and parallel arrays for temperature and pressure time-series.
    \"\"\"
    machine_code = request.GET.get('machine_code')
    time_str = request.GET.get('time')
    
    if not machine_code or not time_str:
        return JsonResponse({"error": "machine_code and time are required"}, status=400)
    
    try:
        # Parse time string and convert to UTC
        # Assuming input is in WIB (Asia/Jakarta)
        wib_tz = pytz.timezone('Asia/Jakarta')
        
        # If naive, assume it's WIB
        parsed_time = parse_datetime(time_str)
        if parsed_time is None:
            return JsonResponse({"error": "Invalid time format. Use ISO format, e.g., 2026-05-20T10:30:00"}, status=400)
            
        if timezone.is_naive(parsed_time):
            local_time = wib_tz.localize(parsed_time)
            query_time = local_time.astimezone(pytz.UTC)
        else:
            # If already aware, just use it
            query_time = parsed_time
            
    except Exception as e:
        return JsonResponse({"error": f"Error parsing time: {str(e)}"}, status=400)

    # Lookup Machine
    try:
        machine = Machine.objects.get(code=machine_code)
    except Machine.DoesNotExist:
        return JsonResponse({"error": f"Machine with code {machine_code} not found"}, status=404)

    # Lookup DyeingProcess where start_time <= query_time <= end_time
    # Or start_time <= query_time and end_time is None (process still running)
    from django.db.models import Q
    processes = DyeingProcess.objects.filter(
        Q(machine=machine),
        Q(start_time__lte=query_time),
        Q(end_time__gte=query_time) | Q(end_time__isnull=True)
    ).order_by('-start_time')

    if not processes.exists():
        return JsonResponse({"error": f"No dyeing process found for {machine_code} at {query_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"}, status=404)
        
    process = processes.first()
    
    # Process basic info
    batch_info = {
        "batch_number": process.batch_number,
        "start_time": process.start_time.isoformat() if process.start_time else None,
        "end_time": process.end_time.isoformat() if process.end_time else None,
        "start_temp": process.start_temp,
        "max_temp": process.max_temp,
        "is_complete": process.is_complete,
        "total_duration": process.total_duration,
        "avg_steam_pressure": process.avg_steam_pressure,
    }
    
    # Add Identity Info if available
    try:
        identity = process.identity
        if identity:
            batch_info.update({
                "nomor_order": identity.nomor_order,
                "artikel_kain": identity.artikel_kain,
                "batch": identity.batch,
                "nomor_warna": identity.nomor_warna,
                "program": identity.program.nama if identity.program else None,
                "operator": identity.operator,
                "jenis_proses": identity.jenis_proses,
            })
    except Exception:
        pass

    # Fetch Time-Series Data
    # Determine bounds
    ts_start = process.start_time
    ts_end = process.end_time or timezone.now()
    
    # Fetch Temperature Logs
    temp_logs = MachineMinuteLog.objects.filter(
        machine=machine,
        timestamp__range=(ts_start, ts_end)
    ).order_by('timestamp').values('timestamp', 'temperature')
    
    # Create parallel arrays for Temperature
    # Users requested array of objects: "okay. Tapi itu kalau bisa array bukan single. Menurut mu bagaimana?"
    # Wait, "array bukan single" could mean array of objects: `[{"time":..., "temp":..., "press":...}]`
    # Let's align both Temp and Pressure by timestamp (truncate to minute)
    
    # Let's fetch Pressure Logs (Steam_Pr)
    try:
        steam_machine = Machine.objects.get(code="Steam_Pr")
        press_logs = MachineMinuteLog.objects.filter(
            machine=steam_machine,
            timestamp__range=(ts_start, ts_end)
        ).order_by('timestamp').values('timestamp', 'temperature') # pressure is stored in temperature field of Steam_Pr
    except Machine.DoesNotExist:
        press_logs = []
        
    # Build dictionary by minute for easy merging
    time_series_dict = {}
    
    for log in temp_logs:
        # Round down to minute to align easily
        ts = log['timestamp'].replace(second=0, microsecond=0)
        ts_str = ts.isoformat()
        if ts_str not in time_series_dict:
            time_series_dict[ts_str] = {"timestamp": ts_str, "temperature": None, "pressure": None}
        time_series_dict[ts_str]["temperature"] = log['temperature']
        
    for log in press_logs:
        ts = log['timestamp'].replace(second=0, microsecond=0)
        ts_str = ts.isoformat()
        if ts_str not in time_series_dict:
            time_series_dict[ts_str] = {"timestamp": ts_str, "temperature": None, "pressure": None}
        time_series_dict[ts_str]["pressure"] = log['temperature']
        
    # Sort and convert to list of objects
    sorted_timestamps = sorted(time_series_dict.keys())
    time_series_array = [time_series_dict[ts] for ts in sorted_timestamps]

    response_data = {
        "batch_info": batch_info,
        "time_series": time_series_array
    }

    return JsonResponse(response_data)
"""

with open('monitoring/views.py', 'a', encoding='utf-8') as f:
    f.write(code)

print("Appended successfully.")
