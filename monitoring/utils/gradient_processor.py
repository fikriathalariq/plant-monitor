from __future__ import annotations

"""
Gradient Processor Module for Jet Dyeing Heat Exchanger Analysis

Multi-stage signal processing pipeline:
1. Outlier Gate (physical bounds)
2. Hold-Last-Value (outlier replacement)
3. Physics dT/dt Limit (saturated steam @ 5.5 bar) - TEMPERATURE DEPENDENT
4. EWMA Smoothing (α=0.25)
5. Kalman Filter
6. Gradient Calculation
7. Hysteresis + State Classification

Physics Reference (Jet Dyeing HX with Saturated Steam @ 5.5 bar):
- Tsat = 155°C
- Bath Volume = 3200 L
- U*A / (m*Cp) = 1.89 × 10^-4 /s

Max heating rate formula: dT/dt = (U*A / m*Cp) × (T_steam - T_current)
- At 20°C: dT/dt ≈ 1.53 °C/min
- At 60°C: dT/dt ≈ 1.08 °C/min
- At 100°C: dT/dt ≈ 0.62 °C/min
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Union


def is_invalid_temperature(temp: Union[float, int, str, None]) -> bool:
    """
    Centralized helper to check if a temperature value is invalid.
    
    Invalid conditions:
    - None
    - String "-" or empty string
    - <= 0
    - NaN
    
    Args:
        temp: Temperature value (can be float, int, str, or None)
        
    Returns:
        True if temperature is invalid, False if valid
    """
    if temp is None or temp == "-":
        return True
    if isinstance(temp, str):
        return temp.strip() in ["", "-", "nan", "NaN"]
    if isinstance(temp, (int, float)):
        if temp <= -1000 or temp >= 100000:
            return True
        if isinstance(temp, float) and math.isnan(temp):
            return True
    return False


def get_filtered_temp_for_invalid(raw_temp: Union[float, int, str, None]) -> Union[str, None]:
    """
    Get the appropriate filtered_temp value when raw_temp is invalid.
    
    User Requirement: If raw_temp is "-", filtered_temp should also be "-"
    to preserve the state indication.
    
    Args:
        raw_temp: The raw temperature value
        
    Returns:
        "-" if raw_temp was "-", None otherwise
    """
    if raw_temp == "-":
        return "-"
    return None


# Status mapping constants (centralized)
# Maps thermal_state to last_status for Machine model
THERMAL_STATE_TO_STATUS = {
    "HEAT": "Running",
    "COOL": "Running", 
    "STEADY": "Running",
    "OFF": "Stop",
    "OFFLINE": "Offline",
    "FAULT": "Warning",
}


def get_machine_status(thermal_state: str, is_invalid: bool = False) -> str:
    """
    Get machine status from thermal state.
    
    Args:
        thermal_state: The thermal state (HEAT, COOL, STEADY, OFF, OFFLINE, FAULT)
        is_invalid: DEPRECATED - no longer used, kept for backward compatibility
        
    Returns:
        Machine status: "Running", "Stop", "Warning", or "Offline"
    """
    return THERMAL_STATE_TO_STATUS.get(thermal_state, "Offline")


def infer_classified_thermal(
    thermal_state: str,
    gradient: Optional[float],
    temp: Optional[float],
    config: Optional[ProcessingConfig] = None,
) -> str:
    """Rekonstruksi state klasifikasi (bukan FAULT) dari log historis."""
    cfg = config or ProcessingConfig()
    if thermal_state in ("HEAT", "STEADY", "COOL", "OFF", "OFFLINE"):
        return thermal_state
    if temp is None or gradient is None:
        return "OFF"
    if temp < cfg.OFF_TEMP:
        return "OFF"
    if gradient > cfg.GRAD_ON:
        return "HEAT"
    if gradient <= -cfg.GRAD_COOL_ON:
        return "COOL"
    if temp >= cfg.STEADY_TEMP and gradient > -cfg.GRAD_COOL_ON and gradient <= cfg.GRAD_ON:
        return "STEADY"
    if abs(gradient) < cfg.GRAD_OFF and temp >= cfg.STEADY_TEMP:
        return "STEADY"
    return "OFF"


def rebuild_fault_counters_from_logs(logs, config: Optional[ProcessingConfig] = None):
    """Hitung ulang batch_transitions dari riwayat log menit (timestamp ASC)."""
    cfg = config or ProcessingConfig()
    batch_transitions = 0
    minutes_since_flip = cfg.FAULT_RECOVERY_MINUTES + 1
    prev_cls = "OFF"
    prev_ts = None

    for row in logs:
        ts = row.timestamp if hasattr(row, "timestamp") else row["timestamp"]
        thermal_state = row.thermal_state if hasattr(row, "thermal_state") else row.get("thermal_state", "")
        gradient = row.gradient if hasattr(row, "gradient") else row.get("gradient")
        filtered_temp = row.filtered_temp if hasattr(row, "filtered_temp") else row.get("filtered_temp")
        temperature = row.temperature if hasattr(row, "temperature") else row.get("temperature")
        temp = filtered_temp if filtered_temp is not None else temperature

        classified = infer_classified_thermal(thermal_state or "", gradient, temp, cfg)

        if (prev_cls == "HEAT" and classified == "COOL") or (prev_cls == "COOL" and classified == "HEAT"):
            batch_transitions += 1
            minutes_since_flip = 0
        elif prev_ts is not None:
            minutes_since_flip += (ts - prev_ts).total_seconds() / 60.0

        if classified == "OFF":
            batch_transitions = 0
            minutes_since_flip = cfg.FAULT_RECOVERY_MINUTES + 1

        if minutes_since_flip > cfg.FAULT_RECOVERY_MINUTES:
            batch_transitions = 0

        prev_cls = classified
        prev_ts = ts

    return batch_transitions, minutes_since_flip, prev_cls


def build_filter_state_from_log(prev_log, config: Optional[ProcessingConfig] = None) -> FilterState:
    """Bangun FilterState dari log terakhir + rebuild counter fault dari riwayat singkat."""
    from datetime import timedelta
    from monitoring.models import MachineMinuteLog

    cfg = config or ProcessingConfig()
    if not prev_log:
        return FilterState()

    window_start = prev_log.timestamp - timedelta(hours=4)
    history = list(
        MachineMinuteLog.objects.filter(
            machine_id=prev_log.machine_id,
            timestamp__gte=window_start,
            timestamp__lte=prev_log.timestamp,
        ).order_by("timestamp")
    )

    batch_transitions, minutes_since_flip, last_classified = rebuild_fault_counters_from_logs(
        history, cfg
    )

    return FilterState(
        last_valid_temp=prev_log.filtered_temp,
        ewma_temp=prev_log.ewma_temp,
        kalman_x=prev_log.kalman_x,
        kalman_p=prev_log.kalman_p,
        ewma_gradient=prev_log.ewma_gradient,
        kalman_grad_x=prev_log.kalman_grad_x,
        last_thermal_state=prev_log.thermal_state or "OFF",
        state_since_minutes=0.0,
        batch_transitions=batch_transitions,
        minutes_since_heat_cool_flip=minutes_since_flip,
        last_classified_thermal=last_classified or "OFF",
    )


@dataclass
class FilterState:
    """Menyimpan state filter untuk kontinuitas antar record."""
    # Temperature filter state
    last_valid_temp: Optional[float] = None
    ewma_temp: Optional[float] = None
    kalman_x: Optional[float] = None
    kalman_p: Optional[float] = None
    
    # Gradient filter state (NEW)
    ewma_gradient: Optional[float] = None
    kalman_grad_x: Optional[float] = None
    kalman_grad_p: Optional[float] = None
    
    # State tracking
    last_thermal_state: str = "OFF"
    state_since_minutes: float = 0.0
    
    # Batch tracking (reset when OFF)
    batch_transitions: int = 0
    minutes_since_heat_cool_flip: float = 999.0
    last_classified_thermal: str = "OFF"
    
    # Shadow / Data Quality Tracking (field formal)
    consecutive_shadow_minutes: int = 0


@dataclass
class ProcessingConfig:
    """Konfigurasi parameter processing."""
    # Physical bounds (relax to extremely wide ranges, real limits are in Machine model)
    T_MIN: float = -9999.0
    T_MAX: float = 9999.0
    
    # === HEAT EXCHANGER PHYSICS (Saturated Steam @ 5.5 bar) ===
    T_STEAM: float = 155.0   # °C
    UA_mCp: float = 4.3e-4  # per second
    MAX_COOL_RATE: float = 2.0   # °C/min
    
    # EWMA for temperature
    EWMA_ALPHA: float = 0.6
    EWMA_ALPHA_PHYSICS: float = 0.5
    
    # Kalman for temperature
    KALMAN_Q: float = 0.1
    KALMAN_R: float = 0.25
    
    # === GRADIENT SMOOTHING (NEW) ===
    GRAD_EWMA_ALPHA: float = 0.5    # EWMA for gradient
    GRAD_KALMAN_Q: float = 0.05     # Kalman process noise for gradient
    GRAD_KALMAN_R: float = 0.3      # Kalman measurement noise for gradient
    
    # Gradient thresholds (hysteresis band)
    GRAD_ON: float = 0.15           # Definite heating threshold (> 0.15 °C/min)
    GRAD_COOL_ON: float = 0.20      # Definite cooling threshold (<= -0.20 °C/min)
    GRAD_OFF: float = 0.10          # Definite steady
    
    # Temperature thresholds
    STEADY_TEMP: float = 53.0   # °C for STEADY state
    OFF_TEMP: float = 40.0      # °C for OFF state
    
    # Dwell time
    DWELL_MIN: float = 1.0  # minutes before confirming state change
    
    # Time gap reset
    TIME_GAP_RESET_MINUTES: float = 30.0  # 30 minutes (was previously 2 hours)
    
    # === FAULT DETECTION ===
    # Max allowed H <-> C transitions in one batch before declaring FAULT
    FAULT_BATCH_TRANSITIONS: int = 6
    # After this many minutes without HEAT<->COOL flip, clear fault latch
    FAULT_RECOVERY_MINUTES: float = 10.0
    
    def get_max_heat_rate(self, current_temp: float) -> float:
        """
        Calculate physics-based maximum heating rate at current temperature.
        
        Formula: dT/dt = (U*A / m*Cp) × (T_steam - T_current)
        
        At lower temperatures, heating is faster (larger ΔT).
        At higher temperatures, heating slows down (smaller ΔT).
        
        Examples:
        - T = 20°C: dT/dt = 0.01134 × 135 = 1.53 °C/min
        - T = 60°C: dT/dt = 0.01134 × 95 = 1.08 °C/min
        - T = 100°C: dT/dt = 0.01134 × 55 = 0.62 °C/min
        """
        if current_temp >= self.T_STEAM:
            return 0.0  # Can't heat above steam temp
        
        delta_T = self.T_STEAM - current_temp
        # Convert /s to /min: × 60
        rate_per_min = self.UA_mCp * 60.0 * delta_T
        
        # Add 50% margin for real-world variations
        return rate_per_min * 1.5


class GradientProcessor:
    """
    Multi-stage signal processor untuk analisis gradien temperatur.
    
    Pipeline:
    Raw → Outlier Gate → Hold/EWMA → Physics Limit → EWMA → Kalman → Gradient → State
    """
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()
    
    def process_single(
        self,
        raw_temp: Optional[float],
        state: FilterState,
        dt_minutes: float = 1.0
    ) -> Tuple[Optional[float], Optional[float], str, FilterState]:
        """
        Process a single temperature reading through the full pipeline.
        
        Args:
            raw_temp: Raw temperature reading (°C)
            state: Current filter state
            dt_minutes: Time delta since last reading (minutes)
        
        Returns:
            (filtered_temp, gradient, thermal_state, new_state)
        """
        cfg = self.config
        
        # === INVALID TEMPERATURE CHECK (using centralized helper) ===
        if is_invalid_temperature(raw_temp):
            # Return appropriate filtered_temp ("-" if raw was "-", else None)
            filtered_temp = get_filtered_temp_for_invalid(raw_temp)
            return filtered_temp, None, "OFFLINE", FilterState()
        
        # === TIME GAP CHECK: Reset if gap is too large ===
        if dt_minutes > cfg.TIME_GAP_RESET_MINUTES:
            # Data loss detected - reset filter state
            # Classify based on current temperature only
            if raw_temp is None or raw_temp < cfg.T_MIN or raw_temp > cfg.T_MAX or raw_temp == "-":
                thermal_state = "OFFLINE"  # Invalid data
                filtered_temp = None
            elif raw_temp < cfg.OFF_TEMP:
                thermal_state = "OFF"  # Valid but low temp
                filtered_temp = raw_temp
            elif raw_temp >= cfg.STEADY_TEMP:
                thermal_state = "STEADY"
                filtered_temp = raw_temp
            else:
                thermal_state = "OFF"  # Ambiguous, default to OFF
                filtered_temp = raw_temp
            
            # Return fresh state initialized with current reading
            new_state = FilterState(
                last_valid_temp=filtered_temp,
                ewma_temp=filtered_temp,
                kalman_x=filtered_temp,
                kalman_p=1.0,  # Reset uncertainty
                last_thermal_state=thermal_state,
                state_since_minutes=0.0
            )
            return filtered_temp, 0.0, thermal_state, new_state
            
        # CLAMPING MOVED HERE: Now that we've checked for massive gaps, clamp dt_minutes
        # for physics and gradient calculations to avoid extreme math artifacts
        dt_minutes = max(0.5, min(dt_minutes, 10.0))
        
        # === STAGE 1: Outlier Gate ===
        is_outlier = False
        if raw_temp is None:
            is_outlier = True
        elif raw_temp < cfg.T_MIN or raw_temp > cfg.T_MAX:
            is_outlier = True
        
        # === STAGE 2: Hold-Last-Value or use raw ===
        if is_outlier:
            temp = state.last_valid_temp
        else:
            temp = raw_temp
        
        if temp is None:
            # No valid data yet
            return None, None, "OFFLINE", state
        
        # === STAGE 3: Physics dT/dt Limit with EWMA smoothing ===
        if state.last_valid_temp is not None and dt_minutes > 0:
            delta = temp - state.last_valid_temp
            
            # Calculate temperature-dependent max rate
            if delta > 0:
                # Heating - use physics-based rate
                max_rate = cfg.get_max_heat_rate(state.last_valid_temp)
            else:
                # Cooling - use fixed rate
                max_rate = cfg.MAX_COOL_RATE
            
            max_delta = max_rate * dt_minutes
            
            # Check if physics violation
            if abs(delta) > max_delta * 2:  # Extreme violation
                # Use EWMA smoothing instead of hard clamp
                if state.ewma_temp is not None:
                    temp = cfg.EWMA_ALPHA_PHYSICS * temp + (1 - cfg.EWMA_ALPHA_PHYSICS) * state.ewma_temp
            elif abs(delta) > max_delta:
                # Moderate violation - soft clamp with EWMA blend
                clamped = state.last_valid_temp + (max_delta if delta > 0 else -max_delta)
                temp = 0.5 * temp + 0.5 * clamped  # Blend
        
        # Update last valid
        new_last_valid = temp
        
        # === STAGE 4: EWMA Smoothing ===
        if state.ewma_temp is None:
            ewma_out = temp
        else:
            ewma_out = cfg.EWMA_ALPHA * temp + (1 - cfg.EWMA_ALPHA) * state.ewma_temp
        
        # === STAGE 5: Kalman Filter ===
        # Prediction step
        x_pred = state.kalman_x if state.kalman_x is not None else ewma_out
        p_pred = (state.kalman_p if state.kalman_p is not None else 1.0) + cfg.KALMAN_Q
        
        # Update step
        K = p_pred / (p_pred + cfg.KALMAN_R)
        kalman_x_new = x_pred + K * (ewma_out - x_pred)
        kalman_p_new = (1 - K) * p_pred
        
        filtered_temp = kalman_x_new
        
        # === STAGE 6: Raw Gradient Calculation ===
        if state.kalman_x is not None and dt_minutes > 0:
            raw_gradient = (kalman_x_new - state.kalman_x) / dt_minutes
        else:
            raw_gradient = 0.0
        
        # === STAGE 7: Gradient Smoothing (EWMA + Kalman) ===
        # EWMA on gradient
        if state.ewma_gradient is None:
            ewma_grad = raw_gradient
        else:
            ewma_grad = cfg.GRAD_EWMA_ALPHA * raw_gradient + (1 - cfg.GRAD_EWMA_ALPHA) * state.ewma_gradient
        
        # Kalman on gradient
        grad_x_pred = state.kalman_grad_x if state.kalman_grad_x is not None else ewma_grad
        grad_p_pred = (state.kalman_grad_p if state.kalman_grad_p is not None else 1.0) + cfg.GRAD_KALMAN_Q
        
        K_grad = grad_p_pred / (grad_p_pred + cfg.GRAD_KALMAN_R)
        kalman_grad_x_new = grad_x_pred + K_grad * (ewma_grad - grad_x_pred)
        kalman_grad_p_new = (1 - K_grad) * grad_p_pred
        
        smoothed_gradient = kalman_grad_x_new
        
        # === STAGE 8: State Classification with Hysteresis ===
        classify_base = state.last_classified_thermal or state.last_thermal_state
        if classify_base == "FAULT":
            classify_base = "OFF"
        thermal_state, new_dwell = self._classify_state(
            filtered_temp,
            smoothed_gradient,
            classify_base,
            state.state_since_minutes,
            dt_minutes
        )
        classified = thermal_state

        # === STAGE 9: FAULT Detection (oscillation, non-sticky) ===
        batch_transitions = state.batch_transitions
        minutes_since_flip = state.minutes_since_heat_cool_flip
        prev_cls = state.last_classified_thermal or "OFF"
        if prev_cls == "FAULT":
            prev_cls = "OFF"

        if prev_cls == "OFF" and classified != "OFF":
            batch_transitions = 0
            minutes_since_flip = cfg.FAULT_RECOVERY_MINUTES + 1

        heat_cool_flip = (
            (prev_cls == "HEAT" and classified == "COOL")
            or (prev_cls == "COOL" and classified == "HEAT")
        )
        if heat_cool_flip:
            batch_transitions += 1
            minutes_since_flip = 0
        else:
            minutes_since_flip += dt_minutes

        if classified == "OFF":
            batch_transitions = 0
            minutes_since_flip = cfg.FAULT_RECOVERY_MINUTES + 1
            thermal_state = "OFF"
        elif batch_transitions > cfg.FAULT_BATCH_TRANSITIONS and minutes_since_flip <= cfg.FAULT_RECOVERY_MINUTES:
            thermal_state = "FAULT"
        else:
            if minutes_since_flip > cfg.FAULT_RECOVERY_MINUTES:
                batch_transitions = 0
            thermal_state = classified

        # Build new state
        new_state = FilterState(
            last_valid_temp=new_last_valid,
            ewma_temp=ewma_out,
            kalman_x=kalman_x_new,
            kalman_p=kalman_p_new,
            ewma_gradient=ewma_grad,
            kalman_grad_x=kalman_grad_x_new,
            kalman_grad_p=kalman_grad_p_new,
            last_thermal_state=thermal_state,
            state_since_minutes=new_dwell,
            batch_transitions=batch_transitions,
            minutes_since_heat_cool_flip=minutes_since_flip,
            last_classified_thermal=classified,
        )
        
        return filtered_temp, smoothed_gradient, thermal_state, new_state
    
    def _classify_state(
        self,
        temp: float,
        gradient: float,
        current_state: str,
        dwell_minutes: float,
        dt_minutes: float
    ) -> Tuple[str, float]:
        """
        Classify thermal state with hysteresis band and dwell time.
        
        Hysteresis:
        - |gradient| > GRAD_ON (0.15): Definite HEAT/COOL
        - |gradient| < GRAD_OFF (0.10): Definite STEADY/OFF
        - Between: Hold previous state (ambiguous zone)
        
        Returns:
            (thermal_state, new_dwell_minutes)
        """
        cfg = self.config
        
        # Determine raw state
        if temp < cfg.OFF_TEMP:
            raw_state = "OFF"
        elif gradient > cfg.GRAD_ON:
            raw_state = "HEAT"
        elif gradient <= -cfg.GRAD_COOL_ON:
            raw_state = "COOL"
        elif temp >= cfg.STEADY_TEMP and gradient > -cfg.GRAD_COOL_ON and gradient <= cfg.GRAD_ON:
            raw_state = "STEADY"
        elif abs(gradient) < cfg.GRAD_OFF and temp < cfg.STEADY_TEMP:
            raw_state = "OFF"
        else:
            # Gradient in ambiguous zone
            raw_state = current_state
        
        # Dwell time logic
        if raw_state == current_state:
            # Same state - accumulate dwell
            new_dwell = dwell_minutes + dt_minutes
        else:
            # State change - check if dwell satisfied
            if dwell_minutes >= cfg.DWELL_MIN:
                # Dwell satisfied - allow transition
                new_dwell = dt_minutes
                return raw_state, new_dwell
            else:
                # Dwell not satisfied - hold current state
                new_dwell = dwell_minutes + dt_minutes
                return current_state, new_dwell
        
        return raw_state, new_dwell


def process_machine_history(logs: list, config: Optional[ProcessingConfig] = None):
    """
    Process a list of MachineMinuteLog objects (already sorted by timestamp ASC).
    
    Args:
        logs: List of MachineMinuteLog instances ordered by timestamp
        config: Processing configuration
    
    Returns:
        List of dicts with processed data
    """
    processor = GradientProcessor(config)
    state = FilterState()
    results = []
    
    prev_timestamp = None
    
    for log in logs:
        # Calculate dt
        if prev_timestamp is not None:
            dt_seconds = (log.timestamp - prev_timestamp).total_seconds()
            dt_minutes = dt_seconds / 60.0
        else:
            dt_minutes = 1.0  # Default for first record
        
        # DO NOT clamp dt_minutes here so that process_single can detect time gaps > 30 mins
        # dt_minutes = max(0.5, min(dt_minutes, 10.0))  # REMOVED due to bug
        
        # Process
        filtered_temp, gradient, thermal_state, state = processor.process_single(
            raw_temp=log.temperature,
            state=state,
            dt_minutes=dt_minutes
        )
        
        results.append({
            'log': log,
            'filtered_temp': filtered_temp,
            'gradient': gradient,
            'thermal_state': thermal_state,
            'ewma_temp': state.ewma_temp,
            'kalman_x': state.kalman_x,
            'kalman_p': state.kalman_p,
        })
        
        prev_timestamp = log.timestamp
    
    return results
