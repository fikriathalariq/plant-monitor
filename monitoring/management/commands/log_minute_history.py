import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from monitoring.models import Machine, MachineMinuteLog, Alert, get_calibrated_temperature
from monitoring.utils.gradient_processor import (
    GradientProcessor,
    FilterState,
    ProcessingConfig,
    build_filter_state_from_log,
)
from monitoring.utils.batch_analyzer import FilterState as BatchFilterState


def check_and_create_critical_alerts(minute_log):
    """
    Check for critical conditions and create alerts if thresholds are crossed.
    Also auto-deactivates alerts when conditions return to normal.
    
    Critical Conditions:
    1. Steam Pressure (Steam_Pr) < 3 bar
    2. HTO Temperature (Oil_Temp) < 235°C
    """
    # Skip if temperature is None or invalid
    if minute_log.temperature is None:
        return
    
    # Get machine code
    machine_code = minute_log.machine.code
    current_value = minute_log.temperature
    
    # Define thresholds
    STEAM_PRESSURE_THRESHOLD = 3.0  # bar
    HTO_TEMP_THRESHOLD = 235.0  # °C
    
    # Check if we need to deactivate existing alerts (condition normalized)
    if machine_code == "Steam_Pr" and current_value >= STEAM_PRESSURE_THRESHOLD:
        # Steam pressure is now normal, deactivate any active steam pressure alerts
        deactivated = Alert.objects.filter(
            machine=minute_log.machine,
            alert_type=Alert.TYPE_STEAM_PRESSURE,
            is_active=True
        ).update(is_active=False)
        if deactivated > 0:
            print(f"✓ RESOLVED: Steam Pressure normalized to {current_value:.2f} bar - {deactivated} alert(s) deactivated")
        return
    
    if machine_code == "Oil_Temp" and current_value >= HTO_TEMP_THRESHOLD:
        # HTO temperature is now normal, deactivate any active HTO temp alerts
        deactivated = Alert.objects.filter(
            machine=minute_log.machine,
            alert_type=Alert.TYPE_HTO_TEMPERATURE,
            is_active=True
        ).update(is_active=False)
        if deactivated > 0:
            print(f"✓ RESOLVED: HTO Temperature normalized to {current_value:.1f}°C - {deactivated} alert(s) deactivated")
        return
    
    # Now check if we need to create new alerts
    alert_type = None
    threshold = None
    
    # Check Steam Pressure
    if machine_code == "Steam_Pr" and current_value < STEAM_PRESSURE_THRESHOLD:
        alert_type = Alert.TYPE_STEAM_PRESSURE
        threshold = STEAM_PRESSURE_THRESHOLD
    
    # Check HTO Temperature
    elif machine_code == "Oil_Temp" and current_value < HTO_TEMP_THRESHOLD:
        alert_type = Alert.TYPE_HTO_TEMPERATURE
        threshold = HTO_TEMP_THRESHOLD
    
    # If no alert condition detected, return
    if alert_type is None:
        return
    
    # IMPROVED DEDUPLICATION: Check if ANY active alert already exists for this machine + type
    # Don't create new alert if one is already active (regardless of when it was created)
    active_alert_exists = Alert.objects.filter(
        machine=minute_log.machine,
        alert_type=alert_type,
        is_active=True
    ).exists()
    
    if active_alert_exists:
        # Alert already exists and is active, don't create duplicate
        return
    
    # Create new alert (only if no active alert exists)
    if alert_type == Alert.TYPE_STEAM_PRESSURE:
        title = f"⚠️ Steam Pressure Critical Low"
        message = f"Steam pressure dropped to {current_value:.2f} bar (threshold: {threshold} bar). Immediate attention required!"
    else:  # HTO Temperature
        title = f"⚠️ HTO Temperature Critical Low"
        message = f"HTO temperature dropped to {current_value:.1f}°C (threshold: {threshold}°C). Check heating system!"
    
    Alert.objects.create(
        severity=Alert.SEVERITY_CRITICAL,
        alert_type=alert_type,
        machine=minute_log.machine,
        title=title,
        message=message,
        current_value=current_value,
        threshold_value=threshold,
        is_active=True
    )
    
    print(f"✓ CRITICAL ALERT CREATED: {title} - Value: {current_value}")



def get_shield_settings():
    """
    Ambil parameter Data Quality Shield dari GlobalSettings.
    """
    from monitoring.models import GlobalSettings
    gs = GlobalSettings.objects.first()
    if gs:
        return {
            'shadow_max_minutes': gs.sensor_shadow_max_minutes,
            'rehydrate_buffer_minutes': gs.sensor_rehydrate_buffer_minutes,
        }
    return {
        'shadow_max_minutes': 15,
        'rehydrate_buffer_minutes': 5,
    }

class Command(BaseCommand):
    help = "Snapshot data mesin setiap 1 menit dengan analisis gradien termal."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            "Start log_minute_history (dengan gradient analysis). "
            "Tekan CTRL+C untuk berhenti."
        ))

        last_minute = None
        
        # Initialize gradient processor
        config = ProcessingConfig()
        processor = GradientProcessor(config)
        
        # Store filter state per machine (persisted in memory)
        filter_states = {}  # key = machine.code, value = FilterState
        
        # [NEW] Re-Hydration Saat Restart (Breach-Aware + Temporally Aware)
        self.stdout.write("Initialize filter states (Re-hydration)...")
        shield = get_shield_settings()
        SHADOW_MAX = shield['shadow_max_minutes']
        REHYDRATE_BUFFER = shield['rehydrate_buffer_minutes']
        
        from monitoring.models import Machine, MachineMinuteLog
        now_init = timezone.now()
        
        for m in Machine.objects.filter(is_active=True):
            if m.operation_mode != 'AUTO':
                continue
                
            last_log = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp').first()
            if last_log is None:
                filter_states[m.code] = FilterState()
                continue
            
            last_dq = getattr(last_log, 'data_quality', 'NORMAL')
            if last_dq == 'OFFLINE':
                filter_states[m.code] = FilterState()
                continue
                
            time_since_last_log = (now_init - last_log.timestamp).total_seconds() / 60.0
            
            if time_since_last_log > REHYDRATE_BUFFER:
                prev_log = MachineMinuteLog.objects.filter(machine=m, filtered_temp__isnull=False).order_by('-timestamp').first()
                state = build_filter_state_from_log(prev_log) if prev_log else FilterState()
                state.consecutive_shadow_minutes = 0
                filter_states[m.code] = state
                continue
                
            prev_log = MachineMinuteLog.objects.filter(machine=m, filtered_temp__isnull=False).order_by('-timestamp').first()
            state = build_filter_state_from_log(prev_log) if prev_log else FilterState()
            
            shadow_count = 0
            recent_logs = MachineMinuteLog.objects.filter(machine=m).order_by('-timestamp')[:SHADOW_MAX + 5]
            for log in recent_logs:
                if getattr(log, 'data_quality', 'NORMAL') == 'SHADOWED':
                    shadow_count += 1
                else:
                    break
                    
            state.consecutive_shadow_minutes = shadow_count
            filter_states[m.code] = state

        # BUFFER: Store latest values during the current minute
        # Format: {machine_code: {'machine': Machine_obj, 'temperature': val, 'operation_mode': mode, 'manual_status': status, 'timestamp': when}}
        minute_buffer = {}

        try:
            while True:
                now = timezone.now()
                current_minute = now.replace(second=0, microsecond=0)
                
                # SAMPLING: Update buffer with latest Machine data every loop (5 sec)
                # This continuously captures the LAST value during the minute
                # We need to fetch machines here to get their latest state for sampling
                machines_for_sampling = Machine.objects.filter(is_active=True)
                
                for m in machines_for_sampling:
                    current_temp = m.temperature
                    is_valid_reading = (
                        current_temp is not None and
                        m.valid_min <= current_temp <= m.valid_max
                    )
                    
                    if m.code not in minute_buffer:
                        minute_buffer[m.code] = {
                            'machine': m,
                            'temperature': current_temp,
                            'operation_mode': m.operation_mode,
                            'manual_status': m.manual_status,
                            'timestamp': now,
                            'has_good_reading': is_valid_reading,
                        }
                    else:
                        if is_valid_reading:
                            minute_buffer[m.code].update({
                                'machine': m,
                                'temperature': current_temp,
                                'operation_mode': m.operation_mode,
                                'manual_status': m.manual_status,
                                'timestamp': now,
                                'has_good_reading': True,
                            })
                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'temperature': current_temp,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status,
                                    'timestamp': now
                                })
                            else:
                                # PRE-BUFFER SHIELD ACTIVE! 
                                # Do not update temperature/timestamp, but DO update machine state
                                minute_buffer[m.code].update({
                                    'machine': m,
                                    'operation_mode': m.operation_mode,
                                    'manual_status': m.manual_status
                                })
                
                # SAVE: When minute changes, save buffered data from PREVIOUS minute
                if current_minute != last_minute and last_minute is not None:
                    # We have buffered data for the previous minute - save it now!
                    self.stdout.write(f"\n[{timezone.localtime(last_minute):%H:%M}] Saving buffered data from previous minute...")
                    
                    with transaction.atomic():
                        logs_to_create = []
                        machines_to_update = []
                        
                        shield_iter = get_shield_settings()
                        SHADOW_MAX_ITER = shield_iter['shadow_max_minutes']

                        # Iterate over the buffered data for the minute that just ended
                        for code, data in minute_buffer.items():
                            m = data['machine']
                            
                            if data['operation_mode'] == "AUTO":
                                state = filter_states.get(m.code, FilterState())
                                
                                from monitoring.utils.gradient_processor import (
                                    is_invalid_temperature, get_machine_status, get_filtered_temp_for_invalid
                                )
                                from monitoring.utils.signal_freshness import is_signal_stale, STATUS_NO_SIGNAL
                                
                                temp = data['temperature']
                                is_bad_quality = not data.get('has_good_reading', True)
                                
                                if is_bad_quality or is_signal_stale(m, now=data.get('timestamp') or now):
                                    if state.last_valid_temp is not None:
                                        new_consecutive = state.consecutive_shadow_minutes + 1
                                        if new_consecutive > SHADOW_MAX_ITER:
                                            raw_temp = temp
                                            cal_temp = None
                                            filtered_temp = None
                                            gradient = None
                                            thermal_state = "OFFLINE"
                                            machine_status = get_machine_status(thermal_state)
                                            
                                            new_state = FilterState(
                                                last_valid_temp=None,
                                                ewma_temp=None,
                                                kalman_x=None,
                                                kalman_p=None,
                                                ewma_gradient=None,
                                                kalman_grad_x=None,
                                                kalman_grad_p=None,
                                                last_thermal_state="OFFLINE",
                                                state_since_minutes=0.0,
                                                batch_transitions=state.batch_transitions,
                                                minutes_since_heat_cool_flip=state.minutes_since_heat_cool_flip,
                                                last_classified_thermal=state.last_classified_thermal,
                                                consecutive_shadow_minutes=0,
                                            )
                                            data_qual = "OFFLINE"
                                        else:
                                            temp_for_filter = state.last_valid_temp
                                            filtered_temp, gradient, thermal_state, new_state = processor.process_single(
                                                raw_temp=temp_for_filter, state=state, dt_minutes=1.0
                                            )
                                            new_state.consecutive_shadow_minutes = new_consecutive
                                            raw_temp = temp
                                            cal_temp = temp_for_filter
                                            machine_status = get_machine_status(thermal_state)
                                            data_qual = "SHADOWED"
                                    else:
                                        raw_temp = temp
                                        cal_temp = None
                                        filtered_temp = None
                                        gradient = None
                                        thermal_state = "OFFLINE"
                                        machine_status = get_machine_status(thermal_state)
                                        
                                        new_state = FilterState(
                                            last_thermal_state="OFFLINE",
                                            batch_transitions=state.batch_transitions,
                                            minutes_since_heat_cool_flip=state.minutes_since_heat_cool_flip,
                                            last_classified_thermal=state.last_classified_thermal,
                                            consecutive_shadow_minutes=0,
                                        )
                                        data_qual = "OFFLINE"
                                else:
                                    filtered_temp, gradient, thermal_state, new_state = processor.process_single(
                                        raw_temp=temp, state=state, dt_minutes=1.0
                                    )
                                    new_state.consecutive_shadow_minutes = 0
                                    raw_temp = temp
                                    cal_temp = get_calibrated_temperature(m.id, raw_temp)
                                    machine_status = get_machine_status(thermal_state)
                                    data_qual = "NORMAL"
                                
                                filter_states[m.code] = new_state
                                
                                # Create log entry for PREVIOUS minute
                                log = MachineMinuteLog(
                                    machine=m,
                                    timestamp=last_minute,  # Log for PREVIOUS minute
                                    raw_temperature=raw_temp,
                                    temperature=cal_temp,
                                    last_status=machine_status,  # Use mapped status for log display (legacy field)
                                    # Processed fields
                                    filtered_temp=filtered_temp,
                                    gradient=round(gradient, 4) if gradient else None,
                                    thermal_state=thermal_state,
                                    ewma_temp=new_state.ewma_temp,
                                    kalman_x=new_state.kalman_x,
                                    kalman_p=new_state.kalman_p,
                                    ewma_gradient=new_state.ewma_gradient,
                                    kalman_grad_x=new_state.kalman_grad_x,
                                    data_quality=data_qual,
                                )
                                logs_to_create.append(log)
                                
                                # --- Hitung perubahan display status (AUTO) ---
                                # Oil/Steam pakai last_status; mesin lain pakai thermal_state.
                                # Samakan Offline / OFFLINE / No Signal supaya tidak dianggap "ganti" tiap menit.
                                _LOST = {"Offline", "OFFLINE", "No Signal", "OFF"}

                                if m.code in ("Oil_Temp", "Steam_Pr"):
                                    old_display_auto = m.last_status or "Offline"
                                    new_display_auto = machine_status
                                else:
                                    old_display_auto = m.last_thermal_status or "OFFLINE"
                                    new_display_auto = thermal_state or "OFFLINE"

                                really_changed = old_display_auto != new_display_auto
                                if really_changed and old_display_auto in _LOST and new_display_auto in _LOST:
                                    really_changed = False

                                if really_changed:
                                    m.previous_display_status = old_display_auto
                                    m.status_changed_at = last_minute

                                # ALWAYS update machine's status, thermal_status, and gradient
                                m.last_status = machine_status
                                m.last_thermal_status = thermal_state  # NEW: always sync thermal status
                                m.last_update = now
                                m.temperature_gradient = log.gradient  # ALWAYS sync gradient (even if None)
                                machines_to_update.append(m)
                            
                            elif data['operation_mode'] == "MANUAL":
                                # MANUAL MODE: Simple status recording (no gradient analysis)
                                machine_status = data['manual_status'] or "Stop"
                                
                                # --- Hitung perubahan display status (MANUAL) ---
                                old_display_manual = m.manual_status or "Stop"
                                new_display_manual = machine_status
                                
                                if old_display_manual != new_display_manual:
                                    m.previous_display_status = old_display_manual
                                    m.status_changed_at = last_minute

                                # Create log entry for manual machine
                                log = MachineMinuteLog(
                                    machine=m,
                                    timestamp=last_minute,  # Log for PREVIOUS minute
                                    temperature=None,  # Manual machines don't track temp
                                    last_status=machine_status,
                                    # No processed fields for manual
                                    filtered_temp=None,
                                    gradient=None,
                                    thermal_state="",  # Empty for manual
                                    ewma_temp=None,
                                    kalman_x=None,
                                    kalman_p=None,
                                    ewma_gradient=None,
                                    kalman_grad_x=None,
                                )
                                logs_to_create.append(log)
                                
                                # Update machine status
                                m.last_status = machine_status
                                m.last_update = now
                                machines_to_update.append(m)

                        # Bulk create logs (inside transaction for atomicity)
                        MachineMinuteLog.objects.bulk_create(logs_to_create, ignore_conflicts=True)
                        
                        # CHECK FOR CRITICAL ALERTS on newly created logs
                        for log in logs_to_create:
                            try:
                                check_and_create_critical_alerts(log)
                            except Exception as e:
                                # Don't break the whole process if alert check fails
                                self.stdout.write(
                                    self.style.ERROR(f"Alert check error for {log.machine.code}: {e}")
                                )
                        
                        # Bulk update machines - ALWAYS update ALL machines
                        if machines_to_update:
                            Machine.objects.bulk_update(
                                machines_to_update,
                                ['last_status', 'last_thermal_status', 'last_update', 'temperature_gradient', 'previous_display_status', 'status_changed_at'],
                                batch_size=50
                            )
                        
                        # BATCH REPROCESSING (Every 10 minutes) - only for AUTO machines
                        if last_minute.minute % 10 == 0:
                            auto_machines_list = [d['machine'] for d in minute_buffer.values() 
                                                 if d['operation_mode'] == "AUTO"]
                            
                            # JALANKAN DI BACKGROUND SETELAH DATA TERSIMPAN
                            # Mencegah loop utama terhenti (yang menyebabkan data hilang/bolong)
                            # dan mencegah table lock karena transaction yang terlalu lama.
                            transaction.on_commit(
                                lambda: self._run_reprocess_in_thread(auto_machines_list, last_minute)
                            )
                        
                        # RECORD STATUS SNAPSHOT (Every minute) - includes ALL machines now
                        machines_list = [d['machine'] for d in minute_buffer.values()]
                        self._record_status_snapshot(machines_list, last_minute)

                        # Perbarui cache KPI boiler harian (setiap 10 menit, selaras bucket chart)
                        if last_minute.minute % 10 == 0:
                            from monitoring.api_report import upsert_boiler_daily_metric, _get_logical_boiler_today
                            logical_today = _get_logical_boiler_today()
                            transaction.on_commit(
                                lambda d=logical_today: upsert_boiler_daily_metric(d)
                            )
                        
                        # Summary
                        state_counts = {}
                        for log in logs_to_create:
                            s = log.thermal_state or "UNKNOWN"
                            state_counts[s] = state_counts.get(s, 0) + 1
                        
                        summary = ", ".join([f"{k}:{v}" for k, v in state_counts.items()])
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[{timezone.localtime(last_minute):%H:%M}] {len(logs_to_create)} logs saved | States: {summary}"
                            )
                        )
                    
                    # Clear buffer for new minute
                    minute_buffer = {}
                
                # Update last_minute tracker for the next iteration
                last_minute = current_minute
                
                # cek tiap 10 detik
                time.sleep(10)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("log_minute_history dihentikan oleh user."))
    
    def _run_reprocess_in_thread(self, machines, current_time):
        """
        Menjalankan reprocessing di background thread agar tidak memblokir
        loop utama yang bertugas mencatat data suhu setiap menit.
        """
        import threading
        from django.db import connection

        def target():
            try:
                processed = self._reprocess_recent_batches(machines, current_time)
                if processed > 0:
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ [Background] Reprocessed {processed} recent batches")
                    )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Background reprocess error: {e}"))
            finally:
                # Wajib tutup koneksi di thread agar tidak bocor (connection leak)
                connection.close()
                
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()

    def _reprocess_recent_batches(self, machines, current_time):
        """
        Reprocess last 3 batches per machine by DELETING and RECREATING them.
        Uses process_batch_history logic to ensure proper batch splitting.
        This allows automatic detection of new batches without manual creation.
        Returns number of batches processed.
        """
        from monitoring.models import DyeingProcess
        
        processed_count = 0
        
        for machine in machines:
            try:
                # Find last 3 batches to determine reprocessing time window
                last_3_batches = list(DyeingProcess.objects.filter(
                    machine=machine
                ).order_by('-start_time')[:3])
                
                if not last_3_batches:
                    continue
                
                # Get start_time of 3rd-to-last batch (oldest of the 3)
                reprocess_from = last_3_batches[-1].start_time

                # Simpan metadata batch ke cache sebelum dihapus agar URL history/report/:id lama tetap bisa di-resolve!
                try:
                    from django.core.cache import cache
                    for b in last_3_batches:
                        cache.set(f"dyeing_process_meta_{b.id}", {
                            "machine": machine.code,
                            "batch": b.batch_number,
                        }, timeout=259200) # 3 hari
                except Exception:
                    pass
                
                # Delete all batches from that start_time onwards
                deleted_count = DyeingProcess.objects.filter(
                    machine=machine,
                    start_time__gte=reprocess_from
                ).delete()[0]
                
                # Reprocess from that time using process_batch_history logic
                from monitoring.management.commands.process_batch_history import Command as ProcessCommand
                
                # Create temporary command instance
                process_cmd = ProcessCommand()
                process_cmd.stdout = self.stdout
                process_cmd.style = self.style
                
                # Get logs from reprocess_from to current_time
                logs = MachineMinuteLog.objects.filter(
                    machine=machine,
                    timestamp__gte=reprocess_from,
                    timestamp__lte=current_time
                ).order_by('timestamp')
                
                if logs.exists():
                    # Call process_machine directly with the logs
                    process_cmd.process_machine(machine, logs)
                    processed_count += 1
                    
                    # Count new batches created
                    new_count = DyeingProcess.objects.filter(
                        machine=machine,
                        start_time__gte=reprocess_from
                    ).count()
                    
                    # ── Re-link orphaned DyeingIdentity ───────────────────────
                    from monitoring.models import DyeingIdentity
                    # Cari semua identity yang orphaned di mesin ini sejak reprocess_from
                    # Cari batch terdekat berdasarkan start_time_snapshot
                    orphans = DyeingIdentity.objects.filter(
                        machine=machine,
                        dyeing_process__isnull=True,
                        start_time_snapshot__gte=reprocess_from - timedelta(hours=1)
                    )
                    
                    for orphan in orphans:
                        # Cari batch terdekat (+- 15 min window)
                        from datetime import timedelta as td
                        matching_batch = DyeingProcess.objects.filter(
                            machine=machine,
                            start_time__range=(
                                orphan.start_time_snapshot - td(minutes=15),
                                orphan.start_time_snapshot + td(minutes=15)
                            )
                        ).first()
                        
                        if matching_batch:
                            orphan.dyeing_process = matching_batch
                            orphan.save(update_fields=["dyeing_process"])
                    # ────────────────────────────────────────────────────────
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [{machine.code}] Deleted {deleted_count}, Created {new_count} batches "
                            f"(from {reprocess_from:%H:%M})"
                        )
                    )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error reprocessing {machine.code}: {e}")
                )
        
        return processed_count
    

    
    def _record_status_snapshot(self, machines, timestamp):
        """Record status snapshot for all machines with energy data."""
        from monitoring.models import MachineStatusSnapshot
        
        snapshot_data = {}
        
        # Get energy source data for this timestamp
        steam_log = MachineMinuteLog.objects.filter(
            machine__code='Steam_Pr',
            timestamp=timestamp
        ).first()
        
        hto_log = MachineMinuteLog.objects.filter(
            machine__code='Oil_Temp',
            timestamp=timestamp
        ).first()
        
        steam_value = steam_log.temperature if steam_log and steam_log.temperature is not None else None
        hto_value = hto_log.temperature if hto_log and hto_log.temperature is not None else None
        
        for machine in machines:
            # Determine detail based on mode
            if machine.operation_mode == "MANUAL":
                detail = machine.manual_status or ""
            else:
                detail = machine.last_thermal_status or ""
            
            # Get corresponding MachineMinuteLog for this machine at this timestamp
            log = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp=timestamp
            ).first()
            
            # Base snapshot data
            machine_snapshot = {
                "status": machine.last_status or "Unknown",
                "detail": detail,
                "mode": machine.operation_mode
            }
            
            # Add energy data if log exists
            if log:
                machine_snapshot["temperature"] = log.temperature
                machine_snapshot["filtered_temp"] = log.filtered_temp
                machine_snapshot["gradient"] = log.gradient
                machine_snapshot["thermal_state"] = log.thermal_state or ""
            else:
                # No log found - set energy data to None
                machine_snapshot["temperature"] = None
                machine_snapshot["filtered_temp"] = None
                machine_snapshot["gradient"] = None
                machine_snapshot["thermal_state"] = ""
            
            snapshot_data[machine.code] = machine_snapshot
        
        # Add global energy source data to snapshot
        # This will be used for reference/display
        snapshot_data["_energy_sources"] = {
            "steam_pr": steam_value,
            "oil_temp": hto_value
        }
        
        # Create or update snapshot
        MachineStatusSnapshot.objects.update_or_create(
            timestamp=timestamp,
            defaults={"snapshot_data": snapshot_data}
        )


