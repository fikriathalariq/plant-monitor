import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open('monitoring/management/commands/log_minute_history.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Inject get_shield_settings()
shield_helper = '''
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

class Command'''
text = text.replace('class Command', shield_helper, 1)

# 2. Inject Re-Hydration logic before try: while True:
rehydrate_logic = '''        filter_states = {}  # key = machine.code, value = FilterState
        
        # [NEW] Re-Hydration Saat Restart (Breach-Aware + Temporally Aware)
        self.stdout.write("Initialize filter states (Re-hydration)...")
        shield = get_shield_settings()
        SHADOW_MAX = shield['shadow_max_minutes']
        REHYDRATE_BUFFER = shield['rehydrate_buffer_minutes']
        
        from monitoring.models import Machine, MachineMinuteLog
        now_init = timezone.now()
        
        for m in Machine.objects.filter(is_active=True):
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

        # BUFFER: Store latest values'''

text = re.sub(r'        filter_states = \{\}.*?# BUFFER: Store latest values', rehydrate_logic, text, flags=re.DOTALL)

# 3. Replace sampling loop (Layer 1)
sampling_loop_old = '''                for m in machines_for_sampling:
                    # Store/update latest value in buffer for this minute
                    # We store the full machine object to avoid re-fetching later
                    minute_buffer[m.code] = {
                        'machine': m,
                        'temperature': m.temperature,
                        'operation_mode': m.operation_mode,
                        'manual_status': m.manual_status,
                        'timestamp': now
                    }'''

sampling_loop_new = '''                for m in machines_for_sampling:
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
                                'temperature': current_temp,
                                'timestamp': now,
                                'has_good_reading': True,
                            })
                        else:
                            if not minute_buffer[m.code].get('has_good_reading', False):
                                minute_buffer[m.code].update({'temperature': current_temp, 'timestamp': now})
                            else:
                                pass # PRE-BUFFER SHIELD ACTIVE! Do not update timestamp.'''

text = text.replace(sampling_loop_old, sampling_loop_new)

# 4. Replace saving loop (Layer 2)
saving_loop_old_regex = r"                        # Iterate over the buffered data for the minute that just ended.*?# Update filter state\s+filter_states\[m\.code\] = new_state\s+# Create log entry for PREVIOUS minute\s+log = MachineMinuteLog\("

saving_loop_new = '''                        shield_iter = get_shield_settings()
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
                                log = MachineMinuteLog('''

text = re.sub(saving_loop_old_regex, saving_loop_new, text, flags=re.DOTALL)

text = re.sub(r'(log = MachineMinuteLog\([^)]+)', r'\1, data_quality=data_qual', text, count=1)

with open('monitoring/management/commands/log_minute_history.py', 'w', encoding='utf-8') as f:
    f.write(text)
