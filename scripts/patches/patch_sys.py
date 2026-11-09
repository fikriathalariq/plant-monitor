import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open('C:\\Users\\HP\\.gemini\\antigravity\\brain\\1e9962ba-7a25-45ee-a57c-a47da29c5cc7\\unified_machine_system.md', 'r', encoding='utf-8') as f:
    text = f.read()

new_intro = '''# Sistem Standardisasi Pemantauan Mesin (Unified Machine Monitoring System)

## 1. Konsep Dasar: "Role-Based Sensor Mapping"
Untuk menghindari _hardcoding_ logika spesifik pada setiap mesin, kita menggunakan pendekatan **Pemetaan Peran Sensor (Role-Based Mapping)**. 

Setiap mesin memiliki konfigurasi parameternya sendiri. Sistem secara cerdas mengevaluasi "peran" dari sensor tersebut, dan arsitekturnya sepenuhnya mendukung pemetaan **Satu Mesin ke Banyak Sensor Energi (1-to-N)**.

### Mode Operasi: AUTO vs MANUAL
Sebelum mengevaluasi peran sensor, sistem membedakan sumber kebenaran (*source of truth*) dari status operasional mesin berdasarkan operation_mode:
- **Mesin AUTO (Sensor-Driven):** Status RUNNING/STOP dan konsumsi energi didikte sepenuhnya oleh telemetri sensor (dievaluasi lewat mapping TRIGGER_OP dan TRIGGER_ENERGY).
- **Mesin MANUAL (Operator-Driven):** Status RUNNING/STOP ditentukan murni dari tombol di UI oleh operator (manual_status). Sistem akan me-bypass evaluasi TRIGGER_OP dan TRIGGER_ENERGY sensor. Namun, mesin ini **tetap** menggunakan pemetaan untuk menautkan metrik QUALITY dan UTILITY_RESOURCE.

### Peran Sensor (Sensor Roles):
1. **Trigger_Operation (Penentu Mesin ON/OFF & Listrik)**
   - *(Hanya dievaluasi untuk mesin AUTO)*
   - **CDR:** Sensor *Speed* (Mesin dianggap ON/Availability berjalan saat Speed > 0).
   - **JD/JR:** Sensor *Temperature* (Sistem batch membaca pola kenaikan suhu).
2. **Trigger_Energy (Penentu Konsumsi Energi Lokal)**
   - *(Hanya dievaluasi untuk mesin AUTO)*
   - **CDR:** *Pressure Direct & Indirect* (Penentu apakah mesin sedang menyedot utilitas global).
   - **JD/JR:** *Temperature*.
3. **Metric_Quality (Parameter Kualitas)**
   - *(Berlaku untuk SEMUA Mesin - AUTO & MANUAL)*
   - Mengambil data *Temperature* ruang proses dari entitas sensor fisik.
4. **Utility_Resource (Sumber Energi Multi-Utilitas)**
   - *(Berlaku untuk SEMUA Mesin - AUTO & MANUAL)*'''

text = text.replace('''# Sistem Standardisasi Pemantauan Mesin (Unified Machine Monitoring System)

## 1. Konsep Dasar: "Role-Based Sensor Mapping"
Untuk menghindari _hardcoding_ logika spesifik pada setiap mesin, kita menggunakan pendekatan **Pemetaan Peran Sensor (Role-Based Mapping)**. 

Setiap mesin memiliki konfigurasi parameternya sendiri. Sistem secara cerdas mengevaluasi "peran" dari sensor tersebut, dan arsitekturnya sepenuhnya mendukung pemetaan **Satu Mesin ke Banyak Sensor Energi (1-to-N)**.

### Peran Sensor (Sensor Roles):
1. **Trigger_Operation (Penentu Mesin ON/OFF & Listrik)**
   - **CDR:** Sensor *Speed* (Mesin dianggap ON/Availability berjalan saat Speed > 0).
   - **JD/JR:** Sensor *Temperature* (Sistem batch membaca pola kenaikan suhu).
2. **Trigger_Energy (Penentu Konsumsi Energi Lokal)**
   - **CDR:** *Pressure Direct & Indirect* (Penentu apakah mesin sedang menyedot utilitas global).
   - **JD/JR:** *Temperature*.
3. **Metric_Quality (Parameter Kualitas)**
   - **Semua Mesin:** *Temperature*.
4. **Utility_Resource (Sumber Energi Multi-Utilitas)**''', new_intro)

# Flowchart update for Logic Engine
new_flow = '''    subgraph LogicEngine [Evaluation Engine]
        direction TB
        EvalType{Mode Mesin?}
        
        EvalManual[Logika MANUAL <br> <i>Ambil m.manual_status dari Operator</i><br><i>Bypass Trigger Sensor</i>]
        EvalAutoBatch[Logika AUTO (BATCH) <br> <i>Evaluasi Trigger_Operation (Temp)</i>]
        EvalAutoCont[Logika AUTO (CONTINUOUS) <br> <i>Evaluasi Trigger_Operation (Speed)</i><br><i>Evaluasi Trigger_Energy (Pressure)</i>]
        
        EvalType -->|MANUAL| EvalManual
        EvalType -->|AUTO: BATCH| EvalAutoBatch
        EvalType -->|AUTO: CONTINUOUS| EvalAutoCont
    end

    subgraph Output [Unified Metrics / Dashboard]
        O1[Machine Status: RUNNING/STOP]
        O2[Energy Status: CONSUMING/IDLE]
        O3[Quality Metrics]
        O4[Grafik Dinamis Multi-Axis: <br>Quality vs {Steam + Oil + Air}]
    end

    S1 & S2 & S3 & U1 & U2 & U3 --> Map
    Map --> LogicEngine
    EvalManual & EvalAutoBatch & EvalAutoCont --> O1
    EvalManual & EvalAutoBatch & EvalAutoCont --> O2'''

old_flow = '''    subgraph LogicEngine [Evaluation Engine]
        direction TB
        EvalType{Tipe Mesin?}
        
        EvalBatch[Logika BATCH <br> <i>Evaluasi Trigger_Operation (Temp)</i>]
        EvalCont[Logika CONTINUOUS <br> <i>Evaluasi Trigger_Operation (Speed)</i><br><i>Evaluasi Trigger_Energy (Pressure)</i>]
        
        EvalType -->|BATCH| EvalBatch
        EvalType -->|CONTINUOUS| EvalCont
    end

    subgraph Output [Unified Metrics / Dashboard]
        O1[Machine Status: RUNNING/STOP]
        O2[Energy Status: CONSUMING/IDLE]
        O3[Quality Metrics]
        O4[Grafik Dinamis Multi-Axis: <br>Quality vs {Steam + Oil + Air}]
    end

    S1 & S2 & S3 & U1 & U2 & U3 --> Map
    Map --> LogicEngine
    EvalBatch & EvalCont --> O1
    EvalBatch & EvalCont --> O2'''

text = text.replace(old_flow, new_flow)

with open('C:\\Users\\HP\\.gemini\\antigravity\\brain\\1e9962ba-7a25-45ee-a57c-a47da29c5cc7\\unified_machine_system.md', 'w', encoding='utf-8') as f:
    f.write(text)
