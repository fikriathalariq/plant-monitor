"""
Advanced Batch Detection & Efficiency Analysis Module

This module provides shared functions for batch detection and physics-based analysis
that can be used by both real-time monitoring (log_minute_history) and 
historical reprocessing (process_batch_history).

Key Features:
- EWMA/Kalman filtering for noise reduction
- Heating start locking to find true heating start
- Forward-validated cooling detection
- Physics-based efficiency calculations
- Steam property calculations using IAPWS97
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import timedelta

try:
    from iapws import IAPWS97
    HAS_IAPWS = True
except ImportError:
    HAS_IAPWS = False


# ==========================================
# 1. CONFIGURATION PARAMETERS
# ==========================================
@dataclass
class BatchProcessingConfig:
    """Configuration for batch detection and physics analysis"""
    
    # --- FILTER PARAMETERS ---
    EWMA_ALPHA: float = 0.6
    KALMAN_Q: float = 0.1
    KALMAN_R: float = 0.25
    GRAD_EWMA_ALPHA: float = 0.5
    GRAD_KALMAN_Q: float = 0.05
    GRAD_KALMAN_R: float = 0.3

    # --- SEGMENTATION THRESHOLDS ---
    GRAD_ON: float = 0.25
    GRAD_COOL_ON: float = 0.20
    GRAD_OFF: float = 0.10
    STEADY_TEMP: float = 55.0
    OFF_TEMP: float = 40.0
    
    # --- BATCH LOGIC ---
    RESTART_TEMP: float = 57.0
    MIN_PEAK_TEMP: float = 58.0
    
    # --- ANALYSIS THRESHOLDS ---
    ANALYSIS_HEAT_THRESH: float = 0.2
    LOCK_RISE_DELTA: float = 15.0
    RESET_GRAD_THRESH: float = 0.1
    
    # Cooling Logic Parameters
    RAW_COOL_TRIGGER: float = -0.8     # Pemicu awal cooling (Raw Gradient)
    COOL_ABORT_THRESH: float = -0.1    # Batas toleransi fluktuasi saat validasi
    COOL_CONFIRM_MIN: int = 10          # Durasi validasi ke depan (menit)
    COOL_MAX_REBOUND_STRIKES: int = 2   # Toleransi rebound dalam menit
    
    # Steady Detection
    STEADY_GRAD_THRESH: float = 0.1     # Relaxed threshold for rolling average
    STEADY_SCAN_WINDOW: int = 5         # Rolling window size

    
    # --- CONTROL ---
    DWELL_MIN: float = 3.0
    TIME_GAP_RESET: float = 30.0
    START_SEARCH_WINDOW: int = 60  # updated by user
    
    # --- PHYSICS ---
    MIN_DRIVING_FORCE: float = 5.0
    DEFAULT_STEAM_TEMP: float = 150.0
    K_IDEAL_SEC: float = 7.324e-4
    
    # --- REAL-TIME VALIDATION (for log_minute_history) ---
    MIN_BATCH_DURATION: float = 15.0          # Minimum batch duration in minutes
    GRACE_PERIOD_MINUTES: int = 30             # Tolerance for temporary data gaps (OFFLINE/None)
    REALTIME_LOOKBACK_HOURS: int = 3          # Lookback window for real-time processing


@dataclass
class FilterState:
    """State persistence for filtering algorithms"""
    last_valid_temp: Optional[float] = None
    ewma_temp: Optional[float] = None
    kalman_x: Optional[float] = None
    kalman_p: Optional[float] = None
    ewma_gradient: Optional[float] = None
    kalman_grad_x: Optional[float] = None
    kalman_grad_p: Optional[float] = None
    last_thermal_state: str = "OFF"
    state_since_minutes: float = 0.0


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def pressure_to_steam_temp(pressure_bar, config=None):
    """Convert steam pressure (bar gauge) to saturation temperature (°C)"""
    default_temp = config.DEFAULT_STEAM_TEMP if config else BatchProcessingConfig.DEFAULT_STEAM_TEMP
    
    if pressure_bar is None or math.isnan(pressure_bar) or pressure_bar < 0.1:
        return default_temp
    
    if HAS_IAPWS:
        try:
            p_mpa = (pressure_bar + 1.013) / 10.0
            steam = IAPWS97(P=p_mpa, x=1)
            temp_c = steam.T - 273.15
            if math.isnan(temp_c):
                return default_temp
            return temp_c
        except:
            pass
            
    # Fallback empirical formula
    p_abs = pressure_bar + 1.013
    return 179.32 * (p_abs ** 0.2390)


def calculate_ideal_time(start_temp, end_temp, steam_temp, config):
    """
    Calculate ideal heating time based on heat transfer physics.
    Uses exponential heating model with steam as heat source.
    
    Args:
        start_temp: Temperature at heating start (°C)
        end_temp: Target/peak temperature (°C)
        steam_temp: Saturation temperature of steam (°C) - already converted via IAPWS
        config: BatchProcessingConfig instance
    """
    k_min = config.K_IDEAL_SEC * 60.0
    target_temp = min(end_temp, steam_temp - 1.0)
    
    driving_force_start = steam_temp - start_temp
    driving_force_end = steam_temp - target_temp
    
    if driving_force_start <= 0 or driving_force_end <= 0: 
        return 0.0
    
    try:
        log_term = math.log(driving_force_start / driving_force_end)
        return max(0.0, (1.0 / k_min) * log_term)
    except ValueError:
        return 0.0


# ==========================================
# 3. CORE PROCESSOR
# ==========================================
class BatchGradientProcessor:
    """Processes temperature data with EWMA/Kalman filtering and thermal state classification"""
    
    def __init__(self, config: Optional[BatchProcessingConfig] = None):
        self.config = config or BatchProcessingConfig()
    
    def process_single_with_grace(
        self,
        raw_temp,
        state: FilterState,
        dt_minutes: float = 1.0,
        consecutive_gap_minutes: float = 0.0,
    ):
        """
        Process a reading with grace-period tolerance for short data gaps.

        During gaps (None/OFFLINE), preserve filter + thermal state if cumulative
        gap duration is within GRACE_PERIOD_MINUTES. Prevents false batch splits
        from brief signal loss.

        Returns:
            tuple: (filtered_temp, gradient, thermal_state, new_state, new_gap_minutes)
        """
        cfg = self.config
        is_nan = raw_temp is None or (isinstance(raw_temp, float) and math.isnan(raw_temp))

        if is_nan:
            new_gap = consecutive_gap_minutes + dt_minutes
            in_grace = (
                new_gap <= cfg.GRACE_PERIOD_MINUTES
                and state.last_thermal_state not in ("OFF",)
                and state.last_valid_temp is not None
            )
            if in_grace:
                kx = state.kalman_x if state.kalman_x is not None else state.last_valid_temp
                return kx, 0.0, state.last_thermal_state, state, new_gap

            kx, gx, st, new_state = self.process_single(raw_temp, state, dt_minutes)
            return kx, gx, st, new_state, 0.0

        kx, gx, st, new_state = self.process_single(raw_temp, state, dt_minutes)
        return kx, gx, st, new_state, 0.0

    def process_single(self, raw_temp, state: FilterState, dt_minutes: float = 1.0):
        """
        Process a single temperature reading.
        
        Returns:
            tuple: (filtered_temp, gradient, thermal_state, new_state)
        """
        cfg = self.config
        is_nan = raw_temp is None or (isinstance(raw_temp, float) and math.isnan(raw_temp))
        
        if is_nan or dt_minutes > cfg.TIME_GAP_RESET:
            therm = "OFF" if (is_nan or raw_temp < cfg.OFF_TEMP) else "STEADY"
            val = raw_temp if not is_nan else state.last_valid_temp
            return val, 0.0, therm, FilterState(
                last_valid_temp=val, 
                ewma_temp=val, 
                kalman_x=val, 
                kalman_p=1.0, 
                last_thermal_state=therm
            )
        
        temp = float(raw_temp)
        if state.last_valid_temp is None: 
            state.last_valid_temp = temp
        
        # EWMA filtering
        ewma = temp if state.ewma_temp is None else cfg.EWMA_ALPHA * temp + (1 - cfg.EWMA_ALPHA) * state.ewma_temp
        
        # Kalman filtering (temperature)
        x = state.kalman_x if state.kalman_x is not None else ewma
        p = (state.kalman_p if state.kalman_p is not None else 1.0) + cfg.KALMAN_Q
        K = p / (p + cfg.KALMAN_R)
        kx = x + K * (ewma - x)
        kp = (1 - K) * p
        
        # Calculate gradient
        effective_dt = max(0.5, min(dt_minutes, 10.0))
        grad = (kx - state.kalman_x) / effective_dt if state.kalman_x is not None else 0.0
        
        # EWMA filtering (gradient)
        g_ewma = grad if state.ewma_gradient is None else cfg.GRAD_EWMA_ALPHA * grad + (1 - cfg.GRAD_EWMA_ALPHA) * state.ewma_gradient
        
        # Kalman filtering (gradient)
        gx = state.kalman_grad_x if state.kalman_grad_x is not None else g_ewma
        gp = (state.kalman_grad_p if state.kalman_grad_p is not None else 1.0) + cfg.GRAD_KALMAN_Q
        Kg = gp / (gp + cfg.GRAD_KALMAN_R)
        kgx = gx + Kg * (g_ewma - gx)
        kgp = (1 - Kg) * gp
        
        # Classify thermal state
        state_res, dwell = self._classify_state(kx, kgx, state.last_thermal_state, state.state_since_minutes, effective_dt)
        
        return kx, kgx, state_res, FilterState(
            last_valid_temp=temp, 
            ewma_temp=ewma, 
            kalman_x=kx, 
            kalman_p=kp, 
            ewma_gradient=g_ewma, 
            kalman_grad_x=kgx, 
            kalman_grad_p=kgp, 
            last_thermal_state=state_res, 
            state_since_minutes=dwell
        )
    
    def _classify_state(self, temp, grad, curr_state, dwell, dt):
        """Classify thermal state based on temperature and gradient"""
        cfg = self.config
        
        if grad > cfg.GRAD_ON: 
            raw = "HEAT"
        elif grad <= -cfg.GRAD_COOL_ON: 
            raw = "COOL"
        elif temp >= cfg.STEADY_TEMP and grad > -cfg.GRAD_COOL_ON and grad <= cfg.GRAD_ON:
            raw = "STEADY"
        elif abs(grad) < cfg.GRAD_OFF:
            if temp < cfg.OFF_TEMP: 
                raw = "OFF"
            else: 
                raw = "OFF"
        else: 
            raw = curr_state
        
        # State transition requires dwell time
        if raw != curr_state and dwell >= cfg.DWELL_MIN:
            return raw, dt
        else:
            return curr_state, dwell + dt


# ==========================================
# 4. DETAILED ANALYSIS (FIXED COOLING LOGIC)
# ==========================================
def analyze_batch_details(batch_logs, peak_temp, config, pressure_map=None):
    """
    Analyze batch details with physics-based metrics.
    
    Args:
        batch_logs: List of dicts with keys: timestamp, raw_temp, filtered_temp, gradient, state
        peak_temp: Peak temperature of the batch
        config: BatchProcessingConfig instance
        pressure_map: Dict mapping timestamp to steam pressure
    
    Returns:
        dict: Metrics including heating_start, cooling_start, efficiency, etc.
    """
    if not batch_logs: 
        return {}
    
    metrics = {
        'heating_span': 0.0, 
        'steady_duration': 0, 
        'cooling_70_duration': 0.0,
        'cooling_start_time': None, 
        'heating_start_time': None, 
        'reached_70c_time': None,
        'steady_start_time': None, 
        'real_heating_duration': 0, 
        'avg_heating_efficiency': 0.0,
        'ideal_heating_time': 0.0, 
        'heating_lag': 0.0, 
        'avg_steam_temp': 0.0, 
        'avg_steam_pressure': 0.0
    }
    
    # 1. PEAK DETECTION (FILTERED)
    # Gunakan filtered_temp agar tidak tertipu oleh sensor noise/spike (misal 141 padahal aslinya 133)
    peak_idx = max(range(len(batch_logs)), key=lambda i: batch_logs[i]['filtered_temp'])
    peak_time = batch_logs[peak_idx]['timestamp']
    peak_val_filtered = batch_logs[peak_idx]['filtered_temp']
    logs_before_peak = batch_logs[:peak_idx+1]
    
    # 2. HEATING START (LOCKING)
    candidate_log = None
    real_start_locked = False
    
    for log in logs_before_peak:
        grad, temp = log['gradient'], log['filtered_temp']
        if real_start_locked: 
            break
        
        if candidate_log is None:
            if grad >= config.ANALYSIS_HEAT_THRESH: 
                candidate_log = log
        else:
            if (temp - candidate_log['filtered_temp']) >= config.LOCK_RISE_DELTA:
                metrics['heating_start_time'] = candidate_log['timestamp'] - timedelta(minutes=1)
                real_start_locked = True
                break
            if grad <= config.RESET_GRAD_THRESH: 
                candidate_log = None
    
    if not metrics['heating_start_time'] and candidate_log: 
        metrics['heating_start_time'] = candidate_log['timestamp'] - timedelta(minutes=1)
    if not metrics['heating_start_time']: 
        metrics['heating_start_time'] = batch_logs[0]['timestamp']

    # 3. COOLING START (ROLLING WINDOW)
    start_search_idx = peak_idx
    cooling_start_found = None
    
    w_cool = config.STEADY_SCAN_WINDOW  # Use the same window size (5)
    for k in range(start_search_idx, len(batch_logs)):
        if k >= start_search_idx + w_cool - 1:
            window_start_idx = k - (w_cool - 1)
            window_logs = batch_logs[window_start_idx:k+1]
            
            total_dt = 0
            total_dtemp = 0
            for idx in range(1, len(window_logs)):
                dt = (window_logs[idx]['timestamp'] - window_logs[idx-1]['timestamp']).total_seconds() / 60.0
                if dt > 0:
                    total_dt += dt
                    total_dtemp += (window_logs[idx]['filtered_temp'] - window_logs[idx-1]['filtered_temp'])
            
            if total_dt > 0:
                avg_grad = total_dtemp / total_dt
                if avg_grad <= -0.7:  # Threshold requested by user
                    cooling_start_found = window_logs[0]['timestamp']
                    break
                    
    if not cooling_start_found:
        cooling_start_found = peak_time  # Fallback to peak
        
    metrics['cooling_start_time'] = cooling_start_found

    # 4. STEADY START (ROLLING WINDOW)
    steady_thresh = peak_val_filtered - 5.0
    
    steady_window = [
        log for log in batch_logs 
        if log['timestamp'] >= metrics['heating_start_time']
        and log['timestamp'] <= metrics['cooling_start_time']
    ]
    
    found_steady = False
    
    # Attempt 1: Rolling window average gradient
    # Window size = w logs: [k-(w-1), ..., k]
    # Steady START = first log in window = k-(w-1)
    w = config.STEADY_SCAN_WINDOW
    for k in range(len(steady_window)):
        log = steady_window[k]
        
        if log['filtered_temp'] < steady_thresh:
            continue
            
        if k >= w - 1:  # need at least w logs (indices k-(w-1) to k)
            window_start_idx = k - (w - 1)
            window_logs = steady_window[window_start_idx:k+1]  # exactly w logs
            total_dt = 0
            total_dtemp = 0
            for idx in range(1, len(window_logs)):
                dt = (window_logs[idx]['timestamp'] - window_logs[idx-1]['timestamp']).total_seconds() / 60.0
                if dt > 0:
                    total_dt += dt
                    total_dtemp += (window_logs[idx]['filtered_temp'] - window_logs[idx-1]['filtered_temp'])
            
            if total_dt > 0:
                avg_grad = total_dtemp / total_dt
                if abs(avg_grad) <= config.STEADY_GRAD_THRESH:
                    # Point to the FIRST log in the window (where steady actually began)
                    metrics['steady_start_time'] = steady_window[window_start_idx]['timestamp']
                    found_steady = True
                    break
            
    # Attempt 2: Fallback
    if not found_steady:
        fallback_candidates = [l for l in steady_window if l['filtered_temp'] >= steady_thresh and l['state'] != 'HEAT']
        if fallback_candidates:
            metrics['steady_start_time'] = fallback_candidates[0]['timestamp']
        else:
            metrics['steady_start_time'] = metrics['cooling_start_time']
    
    # Calculate Duration
    if metrics['steady_start_time']:
        if metrics['steady_start_time'] >= metrics['cooling_start_time']:
            metrics['steady_duration'] = 0
        else:
            diff = (metrics['cooling_start_time'] - metrics['steady_start_time']).total_seconds() / 60.0
            metrics['steady_duration'] = max(0, int(diff))

    # 5. PHYSICS & EFFICIENCY
    if metrics['heating_start_time'] and metrics['cooling_start_time']:
        end_window = metrics['cooling_start_time']
        heating_window = [log for log in batch_logs 
                          if metrics['heating_start_time'] <= log['timestamp'] < end_window]
        valid_heating = [log for log in heating_window if log['gradient'] >= config.ANALYSIS_HEAT_THRESH]
        metrics['real_heating_duration'] = len(valid_heating)
        
        # --- HEATING EFFICIENCY: tetap hanya dari menit valid_heating ---
        eff_scores = []
        for log in valid_heating:
            ts = log['timestamp'].replace(second=0, microsecond=0)
            pressure = pressure_map.get(ts) if pressure_map else None
            steam_temp = pressure_to_steam_temp(pressure, config)
            drive = steam_temp - log['filtered_temp']
            if drive > config.MIN_DRIVING_FORCE:
                eff_scores.append(log['gradient'] / drive)

        # --- STEAM PRESSURE & TEMP: dari heating_start → cooling_start ---
        # (tanpa filter gradient, mencakup keseluruhan masa heating dan fase hold/keeping)
        pressures, steams = [], []
        for log in heating_window:
            ts = log['timestamp'].replace(second=0, microsecond=0)
            pressure = pressure_map.get(ts) if pressure_map else None
            if pressure:
                pressures.append(pressure)
            steam_temp = pressure_to_steam_temp(pressure, config)
            steams.append(steam_temp)
        
        if eff_scores: 
            metrics['avg_heating_efficiency'] = sum(eff_scores) / len(eff_scores)
        if pressures: 
            metrics['avg_steam_pressure'] = sum(pressures) / len(pressures)
        
        if steams: 
            metrics['avg_steam_temp'] = sum(steams) / len(steams)
        else: 
            metrics['avg_steam_temp'] = config.DEFAULT_STEAM_TEMP
            
        start_log = next((log for log in batch_logs if log['timestamp'] == metrics['heating_start_time']), None)
        start_val = start_log['filtered_temp'] if start_log else 0.0
        
        # Use avg_steam_temp (already correctly computed via IAPWS per-point above)
        # This ensures ideal_heating_time is calculated even when pressure_map is unavailable
        avg_steam_temp = metrics['avg_steam_temp']
        
        if start_val > 0 and avg_steam_temp > start_val:
            metrics['ideal_heating_time'] = calculate_ideal_time(
                start_val, peak_temp, avg_steam_temp, config
            )
    else:
        metrics['avg_steam_temp'] = config.DEFAULT_STEAM_TEMP

    # 6. COOLING DURATION (CONDITIONAL TARGET)
    cooling_phase = [log for log in batch_logs if log['timestamp'] >= metrics['cooling_start_time']]
    
    target_temp = 70.0 if peak_val_filtered > 75.0 else 45.0
    below_target = [log for log in cooling_phase if log['raw_temp'] <= target_temp]
    
    if below_target:
        metrics['reached_70c_time'] = below_target[0]['timestamp']
        metrics['cooling_70_duration'] = (metrics['reached_70c_time'] - metrics['cooling_start_time']).total_seconds() / 60.0
    elif batch_logs:
        metrics['cooling_70_duration'] = (batch_logs[-1]['timestamp'] - metrics['cooling_start_time']).total_seconds() / 60.0

    return metrics



def detect_multi_heating_cycles(
    logs_or_process,
    start_bound=None,
    end_bound=None,
    drop_thresh: float = 15.0,
    rise_thresh: float = 15.0,
    min_peak_temp: float = 75.0,
) -> dict:
    """
    Mendeteksi apakah dalam satu batch terdapat >= 2 siklus kenaikan suhu (Re-Heating / Multi-Heating),
    misalnya suhu sudah mencapai puncak (mis. 128°C), turun pendinginan parsial (mis. ke 73.2°C, belum <70°C),
    lalu dipanaskan naik kembali ke suhu tinggi untuk siklus ke-2 (atau ke-3 dst) akibat kain macet / proses ulang.
    """
    from django.utils import timezone

    pts = []
    if hasattr(logs_or_process, 'machine_id'):
        proc = logs_or_process
        from monitoring.models import MachineMinuteLog
        s_dt = start_bound or proc.heating_start_time or proc.start_time
        e_dt = end_bound or proc.reached_70c_time or proc.end_time
        if s_dt and e_dt:
            qs = MachineMinuteLog.objects.filter(
                machine_id=proc.machine_id,
                timestamp__range=(s_dt, e_dt)
            ).order_by('timestamp').values_list('timestamp', 'temperature', 'raw_temperature')
            for ts, temp, raw_t in qs:
                val = raw_t if raw_t is not None else temp
                if val is not None:
                    pts.append((ts, float(val)))
    else:
        for item in (logs_or_process or []):
            ts = item[0]
            val = item[1]
            if val is None:
                continue
            if start_bound and ts < start_bound:
                continue
            if end_bound and ts > end_bound:
                continue
            pts.append((ts, float(val)))

    if len(pts) < 10:
        return {
            'is_multi_heating': False,
            'cycle_count': 1 if pts else 0,
            'cycles': [],
            'valleys': [],
            'reheat_extra_mins': 0.0,
            'final_cooling_mins': 0.0,
        }

    raw_cycles = []
    raw_valleys = []

    mode = 'HEATING'
    curr_start_idx = 0
    curr_peak_idx = 0
    curr_hold_end_idx = 0
    curr_valley_idx = 0

    for i, (ts, t) in enumerate(pts):
        if mode == 'HEATING':
            if t > pts[curr_peak_idx][1]:
                curr_peak_idx = i
                curr_hold_end_idx = i
            elif pts[curr_peak_idx][1] >= min_peak_temp and (pts[curr_peak_idx][1] - t) <= 6.0:
                curr_hold_end_idx = i
            elif pts[curr_peak_idx][1] >= min_peak_temp and (pts[curr_peak_idx][1] - t) >= drop_thresh:
                mode = 'COOLING_VALLEY'
                curr_valley_idx = i
        elif mode == 'COOLING_VALLEY':
            if t < pts[curr_valley_idx][1]:
                curr_valley_idx = i
            elif (t - pts[curr_valley_idx][1]) >= rise_thresh:
                raw_cycles.append((curr_start_idx, curr_peak_idx, curr_hold_end_idx))
                raw_valleys.append((curr_hold_end_idx, curr_valley_idx))
                curr_start_idx = curr_valley_idx
                curr_peak_idx = i
                curr_hold_end_idx = i
                mode = 'HEATING'

    if not raw_cycles or (pts[curr_peak_idx][1] - pts[curr_start_idx][1]) >= rise_thresh:
        raw_cycles.append((curr_start_idx, curr_peak_idx, curr_hold_end_idx))

    cycles = []
    for idx, (s_i, pk_i, he_i) in enumerate(raw_cycles, 1):
        s_ts, s_temp = pts[s_i]
        pk_ts, pk_temp = pts[pk_i]
        he_ts, he_temp = pts[he_i]

        # Cari awal holding (pertama kali mencapai peak_temp - 4.0°C)
        hs_i = pk_i
        for j in range(s_i, pk_i + 1):
            if pts[j][1] >= pk_temp - 4.0:
                hs_i = j
                break
        hs_ts = pts[hs_i][0]

        heat_m = round(max(0.0, (hs_ts - s_ts).total_seconds() / 60.0), 1)
        hold_m = round(max(0.0, (he_ts - hs_ts).total_seconds() / 60.0), 1)
        tot_m = round(max(0.0, (he_ts - s_ts).total_seconds() / 60.0), 1)

        cycles.append({
            'cycle_no': idx,
            'start_ts': s_ts,
            'start_str': timezone.localtime(s_ts).strftime('%H:%M'),
            'start_temp': round(s_temp, 1),
            'hold_start_ts': hs_ts,
            'hold_start_str': timezone.localtime(hs_ts).strftime('%H:%M'),
            'peak_ts': pk_ts,
            'peak_str': timezone.localtime(pk_ts).strftime('%H:%M'),
            'peak_temp': round(pk_temp, 1),
            'hold_end_ts': he_ts,
            'hold_end_str': timezone.localtime(he_ts).strftime('%H:%M'),
            'hold_end_temp': round(he_temp, 1),
            'heat_mins': heat_m,
            'hold_mins': hold_m,
            'total_mins': tot_m,
        })

    valleys = []
    for idx, (cs_i, v_i) in enumerate(raw_valleys, 1):
        cs_ts, cs_temp = pts[cs_i]
        v_ts, v_temp = pts[v_i]
        next_pk_temp = cycles[idx]['peak_temp'] if idx < len(cycles) else v_temp
        cool_m = round(max(0.0, (v_ts - cs_ts).total_seconds() / 60.0), 1)
        valleys.append({
            'valley_no': idx,
            'cool_start_ts': cs_ts,
            'cool_start_str': timezone.localtime(cs_ts).strftime('%H:%M'),
            'from_peak_temp': round(cs_temp, 1),
            'valley_ts': v_ts,
            'valley_str': timezone.localtime(v_ts).strftime('%H:%M'),
            'valley_temp': round(v_temp, 1),
            'to_peak_temp': round(next_pk_temp, 1),
            'drop_delta_c': round(cs_temp - v_temp, 1),
            'rise_delta_c': round(next_pk_temp - v_temp, 1),
            'cool_mins': cool_m,
        })

    is_multi = len(cycles) >= 2 and len(valleys) >= 1
    reheat_extra_mins = 0.0
    final_cooling_mins = 0.0

    if is_multi:
        first_cool_ts = cycles[0]['hold_end_ts']
        last_hold_end_ts = cycles[-1]['hold_end_ts']
        final_ts = pts[-1][0]
        reheat_extra_mins = round(max(0.0, (last_hold_end_ts - first_cool_ts).total_seconds() / 60.0), 1)
        final_cooling_mins = round(max(0.0, (final_ts - last_hold_end_ts).total_seconds() / 60.0), 1)

    return {
        'is_multi_heating': is_multi,
        'cycle_count': len(cycles),
        'cycles': cycles,
        'valleys': valleys,
        'reheat_extra_mins': reheat_extra_mins,
        'final_cooling_mins': final_cooling_mins,
    }
