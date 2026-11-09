# Tech Lead Deep-Dive Audit: Roadmap Menuju Skor > 9.0 / 10

Dokumen ini menyajikan bedah kode (*codebase audit*) secara mendalam terhadap proyek **Plant-Monitor** berdasarkan inspeksi langsung pada struktur direktori, file backend Django, layanan *Physics-Informed Neural Network* (PINN), serta komponen frontend React.

Fokus utama dokumen ini adalah **tiga kategori yang saat ini memiliki skor di bawah 7.0**, mengapa ketiganya menahan potensi portofolio Anda, dan langkah rekayasa konkret untuk mendongkrak masing-masing kategori ke **> 9.0 / 10**.

---

## Ringkasan Target Transformasi Skor

| Kategori | Skor Saat Ini | Target Skor | Akar Masalah Utama Saat Ini | Kunci Utama Menuju > 9.0 |
| :--- | :---: | :---: | :--- | :--- |
| **1. Clean Code & Modularity** | **5.5 / 10** | **9.2 / 10** | *God Files* (file 2.500–4.200 baris), 67 model dalam 1 file, logika bisnis tercampur di *views/API*, duplikasi halaman React (`*1.jsx`). | Modularisasi paket per domain (*Domain-Driven Package*), ekstraksi *Service Layer*, pemecahan komponen UI & *custom hooks*. |
| **2. Repository Hygiene & Cleanliness** | **4.5 / 10** | **9.5 / 10** | **270 file di root** (195 skrip `.py` ad-hoc, dump SQL 207 MB, log 202 MB, binary `tailwindcss.exe` 129 MB), tanpa `README.md` utama. | Karantina skrip riset ke `scripts/`, hapus/ignore binary & dump besar, standarisasi `.gitignore`, dokumentasi `README.md` arsitektural. |
| **3. Testing & Quality Assurance** | **4.0 / 10** | **9.1 / 10** | Hanya 1 file tes formal (`test_url_auto_login.py`); kalkulasi vital (uap, listrik, PINN) belum teruji otomatis. | *Unit test* deterministik pada mesin kalkulasi fisika/energi, *API contract tests*, dan pipeline GitHub Actions CI. |

---

## Kategori 1: Clean Code & Modularity (5.5 ➔ 9.2)

### A. Temuan Spesifik di Codebase Saat Ini

#### 1. Monolitik Ekstrem pada Backend (*The "God Files"*)
Empat file inti di dalam modul `monitoring/` menampung beban kode yang terlalu masif:
* `monitoring/api_report.py` — **4.194 baris** (~202 KB). Mencampur *permission guard*, fungsi kalkulasi tarif listrik (`_compute_batch_electricity_metrics`), analisis *changeover* (`_compute_changeover_stats`), analitik celup, hingga agregasi kalender boiler (`get_boiler_monthly_calendar`).
* `monitoring/admin.py` — **3.863 baris** (~168 KB).
* `monitoring/views.py` — **3.677 baris** (~163 KB).
* `monitoring/models.py` — **3.320+ baris** (~128 KB) yang menampung **67 class Model Django** sekaligus dari berbagai domain yang sebenarnya terpisah:
  * **Telemetri & Mesin:** `MachineGroup`, `Machine`, `MachineMinuteLog`, `JumoDevice`, `JumoChannel`.
  * **Proses Celup & Fisika:** `MachinePhysicsProfile`, `DyeingProcess`, `DyeingIdentity`, `BoilerDailyMetric`.
  * **Master Tekstil & Flow Finishing:** `MasterAnyaman`, `MasterKain`, `BenangLusi`, `BaseFlowProcess`.
  * **Engineering CMMS & Kolaborasi:** `SparePart`, `FieldInspection`, `EngineerIssue`, `DirectMessage`.

#### 2. Monolitik & Duplikasi File pada Frontend React
* Komponen halaman utama berukuran raksasa:
  * `frontend/src/pages/MachineDailyReport.jsx` — **4.253 baris** (196 KB).
  * `frontend/src/pages/Dashboard.jsx` — **2.506 baris** (159.8 KB).
  * `frontend/src/pages/ProcessReport.jsx` — **2.368 baris** (139.6 KB).
* **Duplikasi File Versi Lama (`*1.jsx`):** Terdapat pasangan file kembar seperti `DailyReport.jsx` bersama `DailyReport1.jsx`, serta `MachineDailyAnalytics.jsx` bersama `MachineDailyAnalytics1.jsx`. Di mata Tech Lead, penamaan `File1.jsx` menandakan keraguan menggunakan *version control* (Git branching).
* **Hardcoded Domain Logic & Formatter di UI:** Fungsi `formatRp`, `numFmt`, dan `formatMachineCaption` ditulis ulang di dalam file halaman alih-alih diekstrak ke `frontend/src/lib/formatters.js`.

#### 3. Hardcoded Konfigurasi Spesifik Lingkungan di `settings.py`
Pada `plant_monitor/settings.py` (baris 84–114), URL spesifik seperti `p21l80fh-5173.asse.devtunnels.ms`, `ggv4kdwz-8000.asse.devtunnels.ms`, dan IP lokal `192.168.11.110` tertanam langsung di dalam kode sumber. Selain itu, angka tarif listrik default `lwbp_rate=1035.8` dan rasio `wbp_rate = lwbp_rate * 1.4` tertanam langsung di parameter fungsi `_compute_batch_electricity_metrics`.

---

### B. Strategi Refactoring Menuju Skor > 9.0

#### Langkah 1: Pecah `models.py` Menjadi Package `monitoring/models/` Tanpa Merusak Migrasi Django
Anda **tidak perlu membuat ulang migrasi database** saat memecah `models.py` selama semua model tetap di-re-export di `monitoring/models/__init__.py`:

```python
# monitoring/models/__init__.py
from .machines import (
    MachineGroup, Machine, MachineSensorProfile, MachineSensorMapping,
    MachineMinuteLog, MachineStatusSnapshot, MachineManualLog,
    JumoDevice, JumoChannel,
)
from .dyeing import (
    MachinePhysicsProfile, DyeingProcess, UserFavoriteBatch,
    ProgramMaster, DyeingIdentity, DyeingAnalytics,
    DyeingExecutiveSummary, DailyBatchOverview, RawDataFile,
)
from .energy_metrics import (
    MachineCalibration, PlantHourlySummary, PlantDailySummary,
    DailyPlantMetric, BoilerDailyMetric,
)
from .textile_finishing import (
    MasterAnyaman, MasterKain, BenangLusi, BenangPakan, RevisiKain,
    StandardFlowProcess, BaseFlowProcess, FlowProcessGreige,
    FlowProcessCreeping, FlowProcessDryer, FlowProcessPreset,
    FlowProcessWR, FlowProcessCelup, FlowProcessDryerFinal,
    FlowProcessFinalSet, ObatAntistatic, ObatSoftener,
)
from .planning_cmms import (
    ProductionPlan, ProductionPlanBatch, ProductionPlanBlock,
    InspectionTemplate, SparePart, FieldInspection, EngineerIssue,
    EngineerNote, SparePartUsageLog, CalculationSession,
    MeetingNote, ActionItem,
)
from .iam_anomaly import (
    Shift, PagePermission, Position, CompanyProfile, OperatorProfile,
    Alert, UserActivityLog, IPAccessControl, GlobalSettings,
    DataAnomaly, AnomalyThresholdMaster, AnomalyThresholdProposal,
    AnomalyRuleConfig, AnomalySeverityLevel, DirectConversation, DirectMessage,
)
```

Dengan pola `__init__.py` di atas, seluruh perintah `from monitoring.models import Machine, DyeingProcess` di ratusan file lain **tetap berjalan 100% kompatibel** tanpa perlu mengubah *import* atau membuat migrasi baru.

#### Langkah 2: Pisahkan Logika Kalkulasi dari `api_report.py` ke `monitoring/services/`
Jangan biarkan router HTTP menghitung rumus bisnis secara langsung. Pindahkan fungsi murni seperti `_compute_batch_electricity_metrics`, `_compute_changeover_stats`, dan `_compute_boiler_kpi_summary` ke `monitoring/services/energy_metrics_service.py` dan gunakan `dataclass` atau `TypedDict` yang memiliki *type hint* jelas.

#### Langkah 3: Modularisasi Komponen React & Hapus File Duplikat (`*1.jsx`)
1. Hapus `DailyReport1.jsx` dan `MachineDailyAnalytics1.jsx` setelah memastikan tidak ada rute aktif di `App.jsx` yang memakainya.
2. Ekstrak konstanta UI (`GRADE_STYLES`, `DIAGNOSIS_TONES`) dan helper (`formatRp`, `numFmt`, `formatMachineCaption`) dari `MachineDailyReport.jsx` ke `frontend/src/lib/formatters.js` dan `frontend/src/constants/reportTheme.js`.
3. Pecah halaman > 2.000 baris menjadi sub-komponen terfokus:
   * `MachineKpiHeader.jsx`
   * `MachineScatterMatrixChart.jsx`
   * `BatchAnomalyTable.jsx`
   * `useMachineDailyReportData.js` (*custom hook* untuk fetching & caching state).

---

## Kategori 2: Repository Hygiene & Cleanliness (4.5 ➔ 9.5)

### A. Temuan Spesifik di Codebase Saat Ini

Inspeksi pada direktori utama (`c:\Users\HP\Documents\Plant-Monitor\plant-monitor`) menunjukkan adanya **270 file langsung di level root**:

1. **File Raksasa yang Berbahaya Jika Ter-push ke GitHub:**
   * `backup_kilat.sql` — **207,4 MB** (Database dump mentah yang berisiko membocorkan data operasional internal perusahaan dan melampaui batas ukuran file GitHub 100 MB!).
   * `bot_requests.log` — **202,4 MB** & `bot_requests_full.txt` — **1,2 MB**.
   * `tailwindcss.exe` — **129,1 MB** (Binary eksekusi Windows yang tidak boleh masuk ke repositori Git).
   * `dyeing_process_logs_2026.csv` — **11,2 MB**.
2. **195 File Python Satu Kali Pakai (*Scratch/Diagnostic Scripts*) di Root:**
   * 50 file `check_*.py`, 35 file `analyze_*.py` (contoh: `analyze_jd03.py`, `analyze_deep2.py`), 13 file `query_*.py`, 8 file `patch_*.py`, 6 file `fix_*.py`.
3. **File Artefak Tak Sengaja & Duplikasi Konfigurasi:**
   * File bernama `null` (42 bytes) dan `true` (7.371 bytes) di root (biasanya muncul akibat perintah terminal `> null` di Windows).
   * Tiga versi daftar dependensi: `requirements.txt`, `requirements_clean.txt`, dan `requirements_fixed.txt`.
   * File teks salinan kode lama: `old_api_report.txt`, `old_daily_report.txt`, `old_daily_report_2.txt`, `step_873_output.txt`.
   * Di dalam `frontend/`: terdapat 15+ skrip patch CommonJS (`fix.cjs`, `fix_messy.cjs`, `fix_messy2.cjs`, `apply_segmented.cjs`) dan folder build ganda (`dist_blue`, `dist_green`).
4. **Absennya `README.md` di Root Proyek:**
   * Hanya ada `frontend/README.md` bawaan template Vite, sementara root proyek sama sekali tidak memiliki `README.md`.

---

### B. Strategi Pembersihan Menuju Skor > 9.0

#### Langkah 1: Perbarui `.gitignore` agar Kedap File Sampah & Binary Besar
Perbarui `.gitignore` Anda menjadi seperti ini:

```gitignore
# Secrets & Environment
.env
.env.*
!.env.example

# Python & Django
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
staticfiles/
media/
db.sqlite3

# Database Dumps, Logs & Raw Datasets (KRITIS!)
*.sql
*.sql.gz
*.dump
*.log
*.csv
bot_requests*.txt
step_*_output.txt
old_*.txt
scratch*.txt
debug.json
db_dump*.json
*_report.json
*_comparison.json

# Binaries & Local Runtime Artifacts
*.exe
null
true
.active_slot.txt
.snapshots/
scratch/

# Frontend Build & Node
node_modules/
frontend/node_modules/
frontend/dist/
frontend/dist_*/
```

#### Langkah 2: Skrip PowerShell Otomatis untuk Merapikan 250+ File Root dalam 5 Detik
Anda tidak perlu memindahkan 250 file satu per satu. Jalankan skrip organisasi struktur direktori berikut dari PowerShell untuk memindahkan file riset/diagnostik ke dalam folder terstruktur `scripts/` dan `docs/`:

```powershell
# Buat struktur direktori arsip & utilitas yang rapi
$dirs = @(
    "scripts/diagnostics",
    "scripts/patches",
    "scripts/ops",
    "docs/plans",
    "docs/analysis",
    "archive/legacy_txt"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# 1. Pindahkan skrip Python diagnostik/analisis dari root (kecuali manage.py)
Get-ChildItem -Path . -Filter "*.py" -File | Where-Object { $_.Name -ne "manage.py" } | ForEach-Object {
    if ($_.Name -match "^(patch|fix|append|unlink)_") {
        Move-Item $_.FullName -Destination "scripts/patches/" -Force
    } else {
        Move-Item $_.FullName -Destination "scripts/diagnostics/" -Force
    }
}

# 2. Pindahkan skrip operasional (.bat, .ps1) ke scripts/ops/
Get-ChildItem -Path . -Include "*.bat", "*.ps1" -File | Move-Item -Destination "scripts/ops/" -Force

# 3. Pindahkan dokumen rencana & analisis (.md) ke docs/
Get-ChildItem -Path . -Filter "*.md" -File | Where-Object { $_.Name -ne "README.md" } | ForEach-Object {
    if ($_.Name -match "PLAN") {
        Move-Item $_.FullName -Destination "docs/plans/" -Force
    } else {
        Move-Item $_.FullName -Destination "docs/analysis/" -Force
    }
}

# 4. Bersihkan skrip patch sementara (.cjs) di frontend
New-Item -ItemType Directory -Force -Path "scripts/frontend_codemods" | Out-Null
Get-ChildItem -Path "frontend" -Filter "*.cjs" -File | Move-Item -Destination "scripts/frontend_codemods/" -Force

# 5. Hapus file artefak salah ketik
Remove-Item -Path "null", "true" -ErrorAction SilentlyContinue
```

---

## Kategori 3: Testing & Quality Assurance (4.0 ➔ 9.1)

### A. Temuan Spesifik (Termasuk Bug Nyata yang Ditemukan Saat Audit!)

Saat ini hanya ada 1 file pengujian otomatis formal yaitu `monitoring/tests/test_url_auto_login.py` (136 baris). Sementara itu, mesin kecerdasan utama proyek Anda belum memiliki *unit test* otomatis.

**Temuan Bug Nyata pada `PINNSteamPredictor.predict_three_layers`:**  
Saat menginspeksi `monitoring/services/pinn_engine.py` (baris 309–318), terlihat kode berikut:
```python
def predict_three_layers(self, dyeing_process,
                         own_profile, best_profile,
                         own_weights, best_weights) -> dict:
    own_weights = None
    best_weights = None
    l1 = self.predict(dyeing_process, own_profile.to_physics_dict(), own_weights)
```
Parameter `own_weights` dan `best_weights` yang dikirim ke fungsi tersebut **ditimpa paksa menjadi `None`** di baris 316–317! Akibatnya, *neural network weights* hasil *training* tidak pernah terpakai saat `predict_three_layers` dipanggil, dan sistem selalu jatuh ke perhitungan ODE murni.  
**Inilah alasan mengapa Tech Lead sangat menilai tinggi keberadaan Unit Test:** satu pengujian sederhana akan langsung mendeteksi *silent override* seperti ini sebelum masuk ke produksi.

---

### B. Strategi Pengujian Menuju Skor > 9.0

Fokuslah pada **High-Value Unit Tests** pada 3 area inti:

#### 1. Unit Test Mesin Fisika & PINN (`monitoring/tests/test_pinn_engine.py`)
Menguji rumus entalpi uap (`get_hfg`), struktur dimensi *forward pass* MLP (`4 -> 32 -> 32 -> 1`), dan memastikan `predict_three_layers` menghormati parameter bobot neural network:

```python
import numpy as np
from django.test import SimpleTestCase
from monitoring.services.pinn_engine import PINNSteamPredictor


class PINNSteamPredictorTests(SimpleTestCase):
    def setUp(self):
        self.predictor = PINNSteamPredictor()

    def test_get_hfg_decreases_with_pressure_and_clips_negative(self):
        # Pada tekanan 0 bar, hfg = 2257 kJ/kg
        self.assertEqual(self.predictor.get_hfg(0.0), 2257.0)
        # Tekanan negatif harus di-clip ke 0.0
        self.assertEqual(self.predictor.get_hfg(-2.5), 2257.0)
        # Pada tekanan 4 bar: 2257 - 37 * 4 = 2109 kJ/kg
        self.assertAlmostEqual(self.predictor.get_hfg(4.0), 2109.0)

    def test_mlp_forward_pass_output_shape_and_non_negative_softplus(self):
        temps = np.linspace(30.0, 130.0, 20)
        pressures = np.full(20, 4.2)
        dTdt = np.gradient(temps)

        X = self.predictor._build_inputs(temps, pressures, dTdt)
        self.assertEqual(X.shape, (20, 4))

        weights = np.zeros(self.predictor.N_PARAMS)
        out = self.predictor._forward(X, weights)
        self.assertEqual(out.shape, (20,))
        # Output Softplus harus selalu > 0
        self.assertTrue(np.all(out > 0))
```

#### 2. Unit Test Kalkulasi Energi Listrik & Allowance Kain (`monitoring/tests/test_electricity_metrics.py`)
Menguji fungsi `_compute_batch_electricity_metrics` untuk memvalidasi batas *fabric allowance* maksimal 45 menit, perhitungan tarif LWBP/WBP, dan efisiensi daya:

```python
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from django.test import SimpleTestCase
from monitoring.api_report import _compute_batch_electricity_metrics


class BatchElectricityMetricsTests(SimpleTestCase):
    def test_fabric_allowance_capped_at_45_minutes(self):
        t_70c = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        # Berhenti 90 menit setelah mencapai <70C (melebihi batas 45 menit)
        t_end = t_70c + timedelta(minutes=90)

        dummy_process = SimpleNamespace(
            reached_70c_time=t_70c,
            end_time=t_end,
            program_ideal_duration_mins=120.0,
            machine_nominal_power=30.0,
            power_consumption_kwh=95.0,
            power_consumption_lwbp_kwh=95.0,
            power_consumption_wbp_kwh=0.0,
            power_cost_lwbp=None,
            power_cost_wbp=None,
            power_cost_total=None,
            ideal_power_consumption_kwh=None,
        )
        dummy_program = SimpleNamespace(durasi_ideal=120.0)

        res = _compute_batch_electricity_metrics(dummy_process, program=dummy_program, lwbp_rate=1000.0)

        self.assertEqual(res["late_stop_mins"], 90.0)
        self.assertEqual(res["fabric_allowance_mins"], 45.0)
        # Durasi ideal listrik = 120 + 45 = 165 menit (2.75 jam)
        self.assertEqual(res["elec_ideal_duration_mins"], 165.0)
        # Ideal kWh = 2.75 jam * 30 kW = 82.5 kWh
        self.assertEqual(res["ideal_kwh"], 82.5)
        self.assertEqual(res["pos_loss_kwh"], 12.5)
```

#### 3. Tambahkan GitHub Actions CI Workflow (`.github/workflows/ci.yml`)
Buat file `.github/workflows/ci.yml` berukuran ~35 baris agar setiap kali Anda melakukan `git push`, GitHub secara otomatis menjalankan `python manage.py check`, `python manage.py test`, dan `npm run build` di frontend. Munculnya *badge* hijau **CI Passing** di halaman depan repositori GitHub adalah sinyal kualitas nomor satu bagi Tech Lead.
