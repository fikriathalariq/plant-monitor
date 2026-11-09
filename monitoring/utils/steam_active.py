STEADY_TEMP_THRESHOLD = 90.0
GRADIENT_MIN = -0.1

def is_steam_active_from_snapshot(snap_data: dict) -> bool:
    if snap_data.get('mode') == 'MANUAL':
        return snap_data.get('status') == 'Running'
    
    detail = snap_data.get('detail')
    gradient = snap_data.get('gradient')
    has_valid_gradient = gradient is not None and gradient > GRADIENT_MIN
    
    if detail == 'HEAT':
        return has_valid_gradient
    elif detail == 'STEADY':
        temp = snap_data.get('temperature')
        return has_valid_gradient and temp is not None and temp >= STEADY_TEMP_THRESHOLD
    return False

def is_steam_active_from_machine(machine) -> bool:
    if machine.operation_mode == 'MANUAL':
        return machine.manual_status == 'Running' or machine.last_status == 'Running'
    
    has_valid_gradient = (
        machine.temperature_gradient is not None 
        and machine.temperature_gradient > GRADIENT_MIN
    )
    
    if machine.last_thermal_status == 'HEAT':
        return has_valid_gradient
    elif machine.last_thermal_status == 'STEADY':
        return has_valid_gradient and machine.temperature is not None and machine.temperature >= STEADY_TEMP_THRESHOLD
    return False
