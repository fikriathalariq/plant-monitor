"""
Utility to identify active cooling machines from status snapshots or machine records.
Mesin pencelupan (Jet Dyeing, Jet Relax, Mesin Jet Printing) menggunakan air pendingin
dari cooling tower / booster pump pabrik saat proses cooling berlangsung.
"""

COOLING_MIN_TEMP = 40.0   # Suhu di atas 40°C saat pendinginan aktif
COOLING_MAX_GRADIENT = 0.05  # Gradien suhu negatif atau tidak naik drastis

def is_cooling_dyeing_machine(machine_code: str) -> bool:
    """
    Cek apakah kode mesin adalah mesin batch pencelupan yang menggunakan sistem air pendingin (cooler/HE).
    Yaitu mesin grup Jet Dyeing (JD_*), Jet Relax (JR_*), dan Jet Printing (ZET_*).
    """
    if not machine_code:
        return False
    u = machine_code.upper()
    return u.startswith('JD_') or u.startswith('JR_') or u.startswith('ZET_')


def is_cooling_active_from_snapshot(snap_data: dict, machine_code: str = None) -> bool:
    """
    Menentukan apakah suatu mesin sedang aktif menyerap air pendingin pada snapshot tertentu.
    """
    if not snap_data or not isinstance(snap_data, dict):
        return False

    if machine_code and not is_cooling_dyeing_machine(machine_code):
        return False

    # Status thermal state
    t_state = snap_data.get('thermal_state') or snap_data.get('detail')
    if t_state != 'COOL':
        return False

    # Suhu masih di atas ambang dingin (bukan mesin mati/idle dingin)
    temp = snap_data.get('filtered_temp')
    if temp is None:
        temp = snap_data.get('temperature')
    if temp is not None and temp < COOLING_MIN_TEMP:
        return False

    # Gradien suhu
    gradient = snap_data.get('gradient')
    if gradient is not None and gradient > COOLING_MAX_GRADIENT:
        return False

    return True
