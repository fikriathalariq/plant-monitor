from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import localtime
from monitoring.models import DyeingProcess, MachineMinuteLog, DyeingIdentity
from monitoring.decorators import user_can_access_page

batch_detail_router = Router(tags=["Batch Detail"])

PAGE_CODE = "history_report"


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")


@batch_detail_router.get("/{machine_code}/{batch_number}/")
def get_batch_detail(request, machine_code: str, batch_number: int):
    _require_permission(request)
    process = get_object_or_404(
        DyeingProcess.objects.select_related("machine", "machine__group"),
        machine__code=machine_code,
        batch_number=batch_number
    )
    
    # Get identity if exists
    identity = DyeingIdentity.objects.filter(dyeing_process=process).select_related('program').first()

    start_dt = process.start_time
    end_dt = process.end_time or timezone.now()

    # === 1. Fetch Main Machine Logs ===
    main_logs = MachineMinuteLog.objects.filter(
        machine=process.machine,
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")

    if not main_logs.exists():
        return {"status": "error", "message": "Tidak ada data log untuk batch ini."}

    # === 2. Fetch Auxiliary Logs (Steam & HTO) ===
    steam_logs = MachineMinuteLog.objects.filter(
        machine__code="Steam_Pr",
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")

    hto_logs = MachineMinuteLog.objects.filter(
        machine__code="Oil_Temp",
        timestamp__range=(start_dt, end_dt)
    ).order_by("timestamp")

    steam_map = {
        log.timestamp.replace(second=0, microsecond=0): log.temperature
        for log in steam_logs if log.temperature is not None
    }
    hto_map = {
        log.timestamp.replace(second=0, microsecond=0): log.temperature
        for log in hto_logs if log.temperature is not None
    }

    chart_data = []

    for log in main_logs:
        ts = log.timestamp.replace(second=0, microsecond=0)
        steam = steam_map.get(ts)
        hto = hto_map.get(ts)

        main_temp = log.temperature

        # Calculate efficiency per row
        efficiency = None
        if log.thermal_state == "HEAT" and log.gradient and log.gradient > 0.1:
            steam_temp = 150.0
            filtered_temp = log.filtered_temp or main_temp or 0
            driving_force = steam_temp - filtered_temp
            if driving_force > 1.0:
                efficiency = round(log.gradient / driving_force, 4)

        chart_data.append({
            "time": localtime(ts).strftime("%H:%M"),
            "full_time": localtime(ts).isoformat(),
            "temp": round(main_temp, 1) if main_temp is not None else None,
            "steam": round(steam, 1) if steam is not None else None,
            "hto": round(hto, 1) if hto is not None else None,
            "state": log.thermal_state,
            "efficiency": efficiency,
            "gradient": round(log.gradient, 2) if log.gradient is not None else None
        })

    # === 3. Analysis payload ===
    analysis = {}
    if process.ideal_heating_time:
        analysis["ideal_heating_time"] = round(process.ideal_heating_time, 1)
    if process.real_heating_duration:
        analysis["heating_duration"] = round(process.real_heating_duration, 1)
        
    if identity and identity.program and identity.program.durasi_ideal and process.duration_effective:
        analysis["heating_efficiency"] = round((identity.program.durasi_ideal / process.duration_effective) * 100, 1)
        
    if process.max_temp:
        analysis["peak_temp"] = round(process.max_temp, 1)
    if process.avg_steam_temp:
        analysis["avg_steam_temp"] = round(process.avg_steam_temp, 1)
    if process.avg_steam_pressure:
        analysis["avg_steam_pressure"] = round(process.avg_steam_pressure, 2)
        
    identity_data = None
    if identity:
        identity_data = {
            "id": identity.id,
            "nomor_order": identity.nomor_order,
            "artikel_kain": identity.artikel_kain,
            "program_name": identity.program.nama if identity.program else "-",
            "operator": identity.operator,
            "jenis_proses": identity.jenis_proses,
            "isi_per_tube": identity.isi_per_tube,
            "cycle_60": identity.cycle_60,
            "cycle_puncak": identity.cycle_puncak,
            "nozzle_main_pump": identity.nozzle_main_pump,
            "keterangan": identity.keterangan,
            "target_suhu_max": identity.program.suhu_max if identity.program else None,
            "target_heating": identity.program.durasi_heating_ideal if identity.program else None,
            "target_keeping": identity.program.durasi_keeping_ideal if identity.program else None,
            "target_cooling": identity.program.durasi_cooling_ideal if identity.program else None,
        }

    return {
        "status": "success",
        "data": {
            "process_id": process.id,
            "machine_code": process.machine.code,
            "machine_name": process.machine.name,
            "batch_number": process.batch_number,
            "start_time": localtime(process.start_time).isoformat(),
            "end_time": localtime(process.end_time).isoformat() if process.end_time else None,
            "is_complete": process.is_complete,
            "is_valid": process.is_valid_process,
            "actual_heating": process.heating_duration,
            "actual_keeping": process.steady_duration,
            "actual_cooling": process.cooling_duration,
            "analysis": analysis,
            "identity": identity_data,
            "chart_data": chart_data
        }
    }

from ninja import Schema
from typing import Optional

class BatchActionIn(Schema):
    action: str # "UNLINK" or "SAVE_NOTES"
    notes: Optional[str] = ""

@batch_detail_router.post("/{machine_code}/{batch_number}/action/")
def perform_batch_action(request, machine_code: str, batch_number: int, payload: BatchActionIn):
    _require_permission(request)
    process = get_object_or_404(
        DyeingProcess,
        machine__code=machine_code,
        batch_number=batch_number
    )
    
    identity = DyeingIdentity.objects.filter(dyeing_process=process).first()
    if not identity:
        return 400, {"status": "error", "message": "Tidak ada identitas yang terhubung dengan batch ini."}
        
    if payload.action == "SAVE_NOTES":
        identity.keterangan = payload.notes
        identity.save(update_fields=['keterangan'])
        return {"status": "success", "message": "Notes berhasil disimpan."}
        
    elif payload.action == "UNLINK":
        if payload.notes:
            identity.keterangan = payload.notes
        identity.dyeing_process = None
        identity.save(update_fields=['dyeing_process', 'keterangan'] if payload.notes else ['dyeing_process'])
        return {"status": "success", "message": "Identitas berhasil di-unlink dari batch."}
        
    return 400, {"status": "error", "message": "Invalid action."}
