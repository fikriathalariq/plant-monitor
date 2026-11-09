import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open('C:\\Users\\HP\\.gemini\\antigravity\\brain\\1e9962ba-7a25-45ee-a57c-a47da29c5cc7\\IMPLEMENTATION_PLAN.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Modify the logic block in section 3 to include the manual check
new_logic = '''        prev_log = MachineMinuteLog.objects.filter(machine=machine).order_by('-timestamp').first()
        is_machine_on = prev_log.is_machine_on if prev_log else False
        is_energy_consuming = prev_log.is_energy_consuming if prev_log else False
        
        # [NEW] Prioritas Input Operator untuk Mesin MANUAL
        if machine.operation_mode == "MANUAL":
            is_machine_on = (data.get('manual_status') == "Running")
            is_energy_consuming = is_machine_on
        
        for mapping in mappings:
            # Bypass TRIGGER_OP dan TRIGGER_ENERGY untuk mesin MANUAL (karena sudah diset di atas)
            if machine.operation_mode == "MANUAL" and mapping.role in ["TRIGGER_OP", "TRIGGER_ENERGY"]:
                continue'''

text = text.replace('''        prev_log = MachineMinuteLog.objects.filter(machine=machine).order_by('-timestamp').first()
        is_machine_on = prev_log.is_machine_on if prev_log else False
        is_energy_consuming = prev_log.is_energy_consuming if prev_log else False
        
        for mapping in mappings:''', new_logic)

new_section = '''
---

## 4. Evaluasi Eksplisit: Mesin AUTO vs Mesin MANUAL

Sangat krusial untuk membedakan perlakuan antara mesin yang beroperasi secara AUTO (dengan sensor telemetri JUMO) dan MANUAL (input operator).

### A. Mesin AUTO (e.g., JD, JR, ZET, CDR)
* **Karakteristik:** Status ketersediaan (Running/Stop) harus disimpulkan murni dari bacaan sensor fisik, karena tidak ada tombol operasional operator.
* **Logika Evaluasi:** is_machine_on dan is_energy_consuming dikalkulasi 100% dari evaluasi pemetaan sensor (TRIGGER_OP dan TRIGGER_ENERGY).
* **Ketergantungan:** Mesin tipe ini **wajib** memiliki sensor TRIGGER_OP dengan eval_method yang sesuai (THERMAL_STATE_BASED atau STATIC_HYSTERESIS).

### B. Mesin MANUAL (e.g., Steamer, Stenter, Monfong, Flat)
* **Karakteristik:** Status "Running" atau "Stop" ditentukan langsung oleh operator melalui UI (manual_status). 
* **Logika Evaluasi:** Tahap evaluasi sensor untuk trigger **dilewati (bypassed)**. Sistem langsung mengambil status operasional: is_machine_on = (machine.manual_status == "Running"). Status energi (is_energy_consuming) secara *default* akan mengikuti status operasional ini.
* **Fungsi Mapping (Kekuatan Utama):** Meskipun logika TRIGGER di-bypass, mesin MANUAL **tetap secara aktif memanfaatkan mapping sensor** untuk dua peran vital:
  1. **QUALITY**: Menautkan suhu/mutu dari sensor fisik (yang mungkin terdaftar sebagai mesin AUTO yang berbeda, contoh: *Temp Steamer 1*).
  2. **UTILITY_RESOURCE**: Membebankan konsumsi energi ke boiler utilitas global (*Steam_Pr*, *Oil_Temp*) saat mesin MANUAL tersebut berstatus "Running".

---

## 5. Keunggulan Adaptasi Ekstrem (Extreme Precision)'''

text = text.replace('## 4. Keunggulan Adaptasi Ekstrem (Extreme Precision)', new_section)

with open('C:\\Users\\HP\\.gemini\\antigravity\\brain\\1e9962ba-7a25-45ee-a57c-a47da29c5cc7\\IMPLEMENTATION_PLAN.md', 'w', encoding='utf-8') as f:
    f.write(text)
