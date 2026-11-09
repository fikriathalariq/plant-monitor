# Plant Monitor — Analisis Mendalam & Rencana Perbaikan

> Dokumen ini merangkum hasil analisis mendalam terhadap aplikasi **Plant Monitor**
> (pemantauan energi pabrik tekstil / jet dyeing) yang berjalan di:
> - **Backend Django + Django-Ninja** pada port `8000`
> - **Frontend React + Vite** pada port `5173`
>
> Tujuannya: memberi peta kondisi saat ini, menemukan masalah dari sisi **rekayasa perangkat lunak (programming)** dan **fisika (energi/termodinamika)**, lalu menyusun rencana perbaikan yang bisa kita kerjakan bersama secara bertahap.

Terakhir diperbarui: 1 Juli 2026

---

## 1. Ringkasan Arsitektur Saat Ini

```
┌─────────────────┐     Modbus / JUMO      ┌──────────────────────┐
│  Sensor / PLC   │ ─────────────────────▶ │ management commands   │
│  (suhu, tekanan)│                        │ jumo_realtime.py      │
└─────────────────┘                        │ log_minute_history.py │
                                           └──────────┬───────────┘
                                                      │ tulis
                                                      ▼
┌───────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                     │
│  MachineMinuteLog, DyeingProcess, DyeingIdentity,               │
│  MachineStatusSnapshot, PlantHourly/DailySummary, dst.          │
└──────────────┬──────────────────────────────┬──────────────────┘
               │                               │
   Django Views (server-rendered)     Django-Ninja API (/api/v1)
   /grafik, /admin, /api/machines      /dashboard /report /history …
               │                               │
               ▼                               ▼
        Template + Bootstrap            React SPA (Vite, port 5173)
```

**Stack yang terdeteksi:**
- Backend: Django 5.2, Django-Ninja 1.3, PostgreSQL (psycopg3), WhiteNoise, CORS headers, `iapws` (properti uap), `pandas`/`numpy`/`scipy`, `pymodbus`.
- Frontend: React 19, Vite 8, TailwindCSS 4, Recharts 3, Axios, React Router 7. (Redux Toolkit + React-Redux terpasang tetapi **tidak dipakai** — otentikasi memakai React Context.)
- Pemrosesan sinyal: pipeline filter khusus (Outlier gate → EWMA → Kalman → gradien → klasifikasi state termal) di `gradient_processor.py` & `batch_analyzer.py`.

**Kesan umum:** Sistem ini **kaya fitur dan sudah cukup matang** (deteksi batch, analitik efisiensi, kalibrasi sensor, master kain, kontrol IP, audit log). Namun ada **hutang teknis** yang jika dibereskan akan meningkatkan akurasi angka energi, kepercayaan pengguna, keamanan, dan kemudahan perawatan.

---

## 2. Temuan Prioritas (TL;DR)

| # | Kategori | Temuan | Dampak | Prioritas |
|---|----------|--------|--------|-----------|
| P1 | Fisika | **3–4 nilai konstanta perpindahan panas (`k`/`UA_mCp`) yang berbeda** di modul berbeda → "waktu heating ideal" & "efisiensi" tidak konsisten (bisa berbeda ~9×) | Angka efisiensi tidak apple-to-apple | 🔴 Kritis |
| P2 | Data/Trust | **Grafik "Steam Traffic 24 jam" di dashboard memakai data acak (`random`)**, bukan data nyata | Menyesatkan operator | 🔴 Kritis |
| P3 | Keamanan | `SECRET_KEY`, password DB, `DEBUG=True`, `ALLOWED_HOSTS=*` sebagai default di kode; tidak ada `.gitignore` root (risiko `.env`/`venv` ikut ter-commit) | Risiko keamanan produksi | 🔴 Kritis |
| P4 | Fisika | **Estimasi pemakaian uap memakai konstanta `average_steam_usage` (kg/jam) statis**, bukan neraca energi (Q = m·cp·ΔT / h_fg). Field fisika (`c_machine`, `u_value`, `surface_area`, kapasitas air/kain) ada tapi tidak dipakai | Akurasi energi rendah | 🟠 Tinggi |
| P5 | Arsitektur | **Dua sistem API paralel** (Django views legacy + Django-Ninja) dengan logika terduplikasi (`sort_machines_custom`, kalkulasi steam) | Sulit dirawat, rawan drift | 🟠 Tinggi |
| P6 | Performa | `MachineMinuteLog.save()` melakukan query + tulis ke `Machine` **setiap baris** → N+1 & race saat ingest massal; endpoint dashboard tidak pakai cache/tabel rollup | Beban DB tinggi | 🟠 Tinggi |
| P7 | Frontend | `App.jsx` ±470 baris berisi banyak komponen inline; tak ada instance Axios terpusat, error boundary, atau layer data (React Query/RTK Query) | Sulit dikembangkan | 🟡 Menengah |
| P8 | Kualitas | Nyaris tanpa test otomatis; "magic code" mesin (`Oil_Temp`, `Steam_Pr`, `MC_BOILER`) tersebar hardcoded | Rawan regresi | 🟡 Menengah |

---

## 3. Analisis dari Sisi FISIKA

Ini adalah bagian yang paling menentukan **kebenaran** aplikasi pemantauan energi. Model yang dipakai adalah **lumped-capacitance (Newton's law of heating)** untuk jet dyeing dengan pemanas uap jenuh (saturated steam).

### 3.1 🔴 Konstanta perpindahan panas tidak konsisten antar-modul

Rumus "waktu heating ideal":

\[
t_{ideal} = \frac{1}{k}\,\ln\!\frac{T_{steam}-T_{start}}{T_{steam}-T_{target}}
\]

Nilai `k` (dan `T_steam`) berbeda di tiga tempat:

```136:136:monitoring/utils/gradient_processor.py
    UA_mCp: float = 4.3e-4  # per second
```
```679:680:monitoring/models.py
                    T_STEAM = 155.0
                    UA_mCp = 0.00385
```
```76:77:monitoring/utils/batch_analyzer.py
    DEFAULT_STEAM_TEMP: float = 150.0
    K_IDEAL_SEC: float = 7.324e-4
```

Ditambah docstring `gradient_processor.py` yang menyebut nilai lain lagi (`1.89 × 10⁻⁴ /s`).

**Konsekuensi** — konstanta waktu termal \( \tau = 1/k \):

| Sumber | `k` (/detik) | \( \tau \) | Ekivalen |
|--------|-------------|-----------|----------|
| Docstring `gradient_processor` | 1.89e-4 | ~5291 s | ~88 min |
| `ProcessingConfig.UA_mCp` | 4.3e-4 | ~2326 s | ~39 min |
| `batch_analyzer.K_IDEAL_SEC` (**yang tersimpan ke DB**) | 7.324e-4 | ~1365 s | ~23 min |
| `heating_efficiency_percent` (property model) | 3.85e-3 | ~260 s | ~4,3 min |

Selisih hingga **~9× (bahkan ~20× vs docstring)**. Artinya "efisiensi %" yang muncul di UI bergantung pada jalur kode mana yang menghitungnya — tidak bisa dibandingkan antar-halaman. Bahkan `help_text` field `ideal_heating_time` menulis `k=4.3e-4/sec` padahal nilainya diisi dengan `7.324e-4`.

**Rekomendasi:**
1. Buat **satu sumber kebenaran** untuk parameter fisika, idealnya di `GlobalSettings` (sudah ada tabelnya) atau satu modul `physics_constants.py`. Semua modul mengimpor dari sana.
2. Tetapkan `T_steam` **selalu dari tekanan uap terukur** via IAPWS (fungsi `pressure_to_steam_temp` sudah ada di `batch_analyzer.py`), bukan konstanta 150/155.
3. Perbarui docstring & `help_text` agar sesuai nilai riil, dan tulis dari mana nilai itu diturunkan (kalibrasi lapangan? regresi data historis?).

### 3.2 🟠 Estimasi pemakaian uap tidak berbasis neraca energi

Saat ini total pemakaian uap = jumlah `average_steam_usage` (kg/jam, konstanta per-mesin) untuk mesin yang aktif, dikali durasi:

```106:117:monitoring/api_report.py
        steam_total = 0.0
        for machine_code, snap_data in snapshot.snapshot_data.items():
            machine = machines_dict.get(machine_code)
            if machine:
                is_active = False
                if snap_data.get('mode') == 'MANUAL':
                    is_active = snap_data.get('status') == 'Running'
                else:
                    is_active = snap_data.get('detail') in ['HEAT', 'STEADY']
                if is_active:
                    steam_total += machine.average_steam_usage
```

Ini pendekatan "flat rate" — mesin dianggap memakai uap dengan laju tetap ketika aktif, terlepas dari ΔT, massa air, beban kain, tekanan uap, atau fase (heating vs steady). Padahal **semua parameter fisik yang diperlukan sudah ada di model** namun belum dipakai:

- `Machine.max_water_capacity` (L), `max_fabric_capacity` (kg), `c_machine` (kJ/K), `surface_area` (m²), `u_value` (W/m²·K), `batch_steam` (kg/batch), `losses_steam` (kg/jam).
- `GlobalSettings.water_specific_heat` (4,18 kJ/kg·K), `fabric_specific_heat` (1,05 kJ/kg·K), `water_density`, `standard_ambient_temp`.

**Model energi yang lebih benar** (per batch / per interval):

\[
Q_{total} = \underbrace{(m_w c_{p,w} + m_f c_{p,f} + C_{mesin})\,\Delta T}_{\text{pemanasan sensible}} \;+\; \underbrace{U A (T - T_{amb})\,\Delta t}_{\text{rugi permukaan (standby)}} \;+\; Q_{losses}
\]

Lalu massa uap:

\[
m_{steam} = \frac{Q_{total}}{h_{fg}(T_{sat})}
\]

di mana \( h_{fg} \) (kalor laten penguapan) juga bisa diambil dari **IAPWS** pada tekanan uap terukur.

**Rekomendasi:**
1. Tambahkan fungsi `estimate_steam_kg(process | interval)` yang menghitung Q dari neraca energi di atas dan membaginya dengan `h_fg` dari IAPWS.
2. Manfaatkan `u_value` × `surface_area` untuk **rugi panas standby** (kenapa mesin STEADY tetap makan uap) — saat ini fase STEADY tidak dibedakan konsumsinya dari HEAT.
3. Jadikan `average_steam_usage` sebagai **fallback** saja bila data fisik mesin belum diisi, dan tandai di UI mana angka "terukur" vs "estimasi kasar".

### 3.3 🟡 "Margin 50%" arbitrer pada laju pemanasan maksimum

```190:193:monitoring/utils/gradient_processor.py
        rate_per_min = self.UA_mCp * 60.0 * delta_T
        
        # Add 50% margin for real-world variations
        return rate_per_min * 1.5
```

Faktor `×1.5` adalah "fudge factor" tanpa dasar fisik yang terdokumentasi. Ini dipakai sebagai batas fisika untuk menolak lonjakan sensor. Sebaiknya faktor toleransi ini diturunkan dari **statistik noise sensor riil** (mis. dari data historis, gunakan `scipy` yang sudah terpasang) dan dijadikan parameter yang tercatat, bukan angka ajaib.

### 3.4 🟡 Pemodelan fase COOLING kurang berbasis fisika

Deteksi cooling memakai ambang gradien heuristik (mis. `avg_grad <= -1.0 °C/min`) dan `MAX_COOL_RATE = 2.0 °C/min` tetap. Padahal **pendinginan juga mengikuti Newton's law of cooling** terhadap suhu ambient/air pendingin. Efisiensi cooling saat ini hanya diukur dari durasi vs ideal program, bukan dari model termal. Peluang: model cooling analog dengan heating (dengan `T_sink` = suhu air pendingin / ambient) untuk deteksi anomali pendinginan (mis. katup pendingin bermasalah).

### 3.5 🟡 Target suhu hardcoded & threshold campur aduk

- `analyze_batch_details` memakai `target_temp = 70.0 if peak > 75 else 45.0` (hardcoded) untuk mengukur durasi cooling.
- Ambang `STEADY_TEMP`, `OFF_TEMP`, `GRAD_ON/OFF` berbeda antara `gradient_processor.py` (STEADY 53) dan `batch_analyzer.py` (STEADY 55). Sebaiknya diseragamkan & dijadikan konfigurasi per-tipe mesin.

### 3.6 ✅ Yang sudah baik secara fisika

- Penggunaan **IAPWS97** untuk konversi tekanan→suhu jenuh uap (akurat, bukan sekadar tabel kasar), lengkap dengan fallback empiris.
- Pipeline **EWMA + Kalman** untuk denoising suhu & gradien — pendekatan yang tepat untuk sensor industri berisik.
- Kalibrasi sensor polinomial kuadratik (`MachineCalibration`: `y = A·x² + B·x + C`) — fleksibel untuk koreksi span/offset/non-linearitas.
- Physics dT/dt limit yang bergantung suhu (laju pemanasan turun saat mendekati T_steam) — konsisten dengan realita.

---

## 4. Analisis dari Sisi PROGRAMMING

### 4.1 🔴 Data dummy/acak tampil sebagai data nyata

```77:90:monitoring/api_dashboard.py
    now = datetime.now()
    series = []
    for i in range(24, -1, -1):
        dt = now - timedelta(hours=i)
        # Bikin data melengkung (sinusoidal) untuk usage & pressure
        hour_factor = (dt.hour / 24.0) * 3.14 * 2
        base_usage = 1000 + (500 * (1 + random.random()))
        base_pressure = 3.0 + (1.0 * random.random())
```

Endpoint `/dashboard/steam-traffic` mengembalikan **grafik 24 jam yang isinya acak**. Untuk aplikasi pemantauan energi, ini fatal untuk kepercayaan pengguna. (Endpoint `get_daily_summary` juga masih punya `performance_goal = "102%"` hardcoded.)

**Rekomendasi:** ganti dengan agregasi nyata dari `MachineStatusSnapshot` + `PlantHourlySummary` (pola yang sudah benar dipakai di `api_report.get_daily_summary`). Hapus `import random`.

### 4.2 🔴 Keamanan konfigurasi

```43:52:plant_monitor/settings.py
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-e3n*&wbf...')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
...
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')
```
```193:193:plant_monitor/settings.py
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'suritex01'),
```

- `SECRET_KEY` dan **password DB nyata** ada sebagai default di kode.
- `DEBUG` default `True`, `ALLOWED_HOSTS` default `*`.
- **Tidak ada `.gitignore` di root** (hanya `frontend/` & `venv/` yang punya) — `venv/` dan `.env` berada di dalam folder proyek dan berisiko ikut ter-commit ke Git.
- `DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000000` — sangat tinggi (untuk bulk-delete admin), berpotensi DoS. Lebih baik pakai penghapusan berbasis queryset.

**Rekomendasi:**
1. Hapus semua nilai sensitif dari kode; wajibkan lewat `.env`. Untuk produksi, `DEBUG=False`, `ALLOWED_HOSTS` eksplisit.
2. Tambahkan **`.gitignore` root** (minimal: `venv/`, `.env`, `*.log`, `__pycache__/`, `media/`, `staticfiles/`, `frontend/node_modules/`, `bot_requests.log`). Rotasi `SECRET_KEY` & password DB karena sudah pernah ada di kode.
3. Aktifkan security checklist Django (`SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, dst.) saat `HTTPS_ENABLED`.

> Catatan: verifikasi apakah `.env`/`venv` benar-benar ter-track Git belum bisa dijalankan karena shell environment sedang bermasalah saat analisis; mohon cek manual dengan `git ls-files .env` dan `git ls-files "venv/*"`.

### 4.3 🟠 Dua sistem API paralel + duplikasi logika

`monitoring/urls.py` masih mengekspos banyak endpoint gaya lama (`/api/machines/`, `/api/chart/<code>/`, `/grafik/...`, dashboard server-rendered) sementara React SPA memakai `/api/v1/...` (Django-Ninja). Frontend bahkan melakukan hack untuk memanggil endpoint legacy:

```77:77:frontend/src/pages/Dashboard.jsx
        axios.get('/steam-usage-history/?hours=24', { baseURL: axios.defaults.baseURL.replace('/v1', '') }),
```

Fungsi `sort_machines_custom` dan blok kalkulasi steam **diduplikasi identik** di `api_report.py` dan `api_dashboard.py`.

**Rekomendasi:**
1. Pilih satu jalur (disarankan Django-Ninja untuk SPA) dan tandai endpoint legacy sebagai deprecated / migrasikan.
2. Pindahkan helper bersama (`sort_machines_custom`, kalkulasi steam, `get_machine_status_logic`) ke satu modul `monitoring/services/` dan impor dari sana.

### 4.4 🟠 `MachineMinuteLog.save()` terlalu berat & rawan race

Setiap penyimpanan satu baris log memicu: query log sebelumnya, rekonstruksi filter state, proses filter, lalu **menulis balik ke `Machine`** bila ini log terbaru:

```522:560:monitoring/models.py
        newer_exists = MachineMinuteLog.objects.filter(
            machine=self.machine, 
            timestamp__gt=self.timestamp
        ).exists()
        ...
            self.machine.save(update_fields=update_fields)
```

Saat ingest massal (ratusan mesin × per menit) ini menghasilkan banyak query & `Machine.save()` per baris — N+1 dan potensi race condition antar-proses ingest. `management/commands/log_minute_history.py` tampaknya sudah punya pipeline batch yang lebih baik; logika di `save()` menduplikasi & bertabrakan dengan itu.

**Rekomendasi:**
1. Pindahkan pemrosesan filter & sinkronisasi status `Machine` ke pipeline batch (satu tempat), bukan di `Model.save()`.
2. Gunakan `bulk_create`/`bulk_update` untuk ingest. Pertimbangkan **TimescaleDB** (ekstensi Postgres) untuk tabel time-series `MachineMinuteLog` yang akan tumbuh besar, plus kebijakan retensi/kompresi.

### 4.5 🟠 Endpoint dashboard tidak memanfaatkan cache & tabel rollup

Cache (LocMem/Redis) sudah dikonfigurasi dan ada tabel rollup (`PlantHourlySummary`, `PlantDailySummary`, `DailyPlantMetric`), tetapi endpoint dashboard menghitung ulang agregasi berat tiap request. `get_steam_sales` bahkan memanggil `get_daily_summary` di dalam loop (6+ kali), masing-masing memproses seluruh snapshot harian.

**Rekomendasi:** bungkus endpoint agregat dengan cache TTL pendek (`cache.get_or_set`), dan selalu baca dari tabel rollup untuk data historis; hitung "live" hanya untuk hari berjalan.

### 4.6 🟡 "Magic values" mesin tersebar hardcoded

Kode mesin seperti `"Oil_Temp"`, `"Steam_Pr"`, `"MC_BOILER"` dipakai di banyak file (`models.py`, `api_dashboard.py`, `api_report.py`, `log_minute_history.py`). Mengubah/menambah sensor berarti berburu string di seluruh repo.

**Rekomendasi:** tambahkan field peran pada `Machine` (mis. `role`: `PRODUCTION`/`STEAM_SENSOR`/`OIL_SENSOR`/`BOILER`) atau flag boolean (`is_sensor`, `is_boiler`). Ganti semua pengecekan string dengan flag tersebut.

### 4.7 🟡 Frontend: struktur & lapisan data

- `App.jsx` (±470 baris) memuat `AuthContext`, `Login`, `Layout`, `SnapshotHistory` sekaligus — sebaiknya dipecah ke `src/components/`, `src/context/`, `src/pages/`.
- Konfigurasi Axios ditulis inline di `App.jsx`; buat `src/lib/api.js` sebagai instance terpusat (baseURL, interceptor error 401→redirect login, dan penanganan endpoint legacy tanpa hack `replace('/v1','')`).
- Belum ada **error boundary**; kegagalan fetch hanya `console.error`. Tambahkan boundary + state error yang tampil ke pengguna.
- Polling `setInterval` manual di tiap halaman. Karena **Redux Toolkit sudah terpasang tapi tak dipakai**, pertimbangkan **RTK Query** (atau TanStack Query) untuk caching, dedup, retry, dan polling terkelola — sekaligus menghapus dependensi yang menganggur.

### 4.8 🟡 Kualitas & keandalan

- `monitoring/tests.py` praktis kosong → tidak ada jaring pengaman regresi, padahal logika fisika/deteksi batch kompleks. Prioritaskan **unit test** untuk `gradient_processor`, `batch_analyzer` (kasus: heating, steady, cooling, gap data, outlier), dan `pressure_to_steam_temp`.
- `BotBlockerMiddleware.BLOCKED_UA_PATTERNS`: karena penggabungan string tanpa `|`, pola `...okhttp|axios/` menyatu menjadi `axios/scanbot` (bukan `axios/` lalu `scanbot`). Efeknya UA `axios/` tak benar-benar terblok — sebuah bug regex yang sebaiknya diperbaiki (dan pastikan tidak memblokir klien sah).
- `MachineManualLog.__str__` tidak `return` string (hanya mengevaluasi f-string) → repr default. Sepele tapi mudah diperbaiki.
- Logging aktivitas & upsert IP memakai `threading.Thread` per request. Untuk beban tinggi, pertimbangkan queue/`async` agar tidak menghabiskan thread.

---

## 5. Rencana Perbaikan Bertahap (Roadmap)

### Fase 0 — Pengamanan cepat (1–2 hari)
- [ ] Tambah `.gitignore` root; keluarkan `venv/`, `.env`, log, `node_modules/` dari tracking. Rotasi `SECRET_KEY` & password DB.
- [ ] `DEBUG`/`ALLOWED_HOSTS`/rahasia wajib dari `.env`; matikan default berbahaya.
- [ ] Ganti data acak `/dashboard/steam-traffic` dengan agregasi nyata; hapus `performance_goal` hardcoded (atau beri sumber nyata).

### Fase 1 — Konsistensi fisika (fondasi kepercayaan angka) (3–5 hari)
- [ ] Buat satu sumber konstanta fisika (`GlobalSettings`/`physics.py`); satukan `k`, `T_steam`, ambang state.
- [ ] Selalu turunkan `T_steam` dari tekanan terukur via IAPWS.
- [ ] Perbaiki docstring & `help_text` yang menyesatkan.
- [ ] Tulis unit test untuk pipeline filter & perhitungan waktu ideal.

### Fase 2 — Energi berbasis neraca (akurasi) (1–2 minggu)
- [ ] Implementasi `estimate_steam_kg()` berbasis Q = m·cp·ΔT + rugi UA·A + losses, dibagi h_fg (IAPWS).
- [ ] Manfaatkan `u_value`, `surface_area`, kapasitas air/kain, `c_machine`.
- [ ] Bedakan konsumsi uap fase HEAT vs STEADY; tandai "terukur vs estimasi" di UI.

### Fase 3 — Konsolidasi backend & performa (1–2 minggu)
- [ ] Satukan helper duplikat ke `services/`; deprecate endpoint legacy.
- [ ] Pindahkan pemrosesan dari `MachineMinuteLog.save()` ke pipeline batch; `bulk_create/update`.
- [ ] Cache endpoint agregat; baca dari tabel rollup. Evaluasi TimescaleDB + retensi.
- [ ] Ganti string mesin ajaib dengan field peran.

### Fase 4 — Modernisasi frontend (1–2 minggu)
- [ ] Pecah `App.jsx`; buat instance Axios + interceptor terpusat.
- [ ] Adopsi RTK Query/TanStack Query; hapus dependensi menganggur.
- [ ] Tambah error boundary, skeleton loading, dan penanganan sesi kedaluwarsa.

### Fase 5 — Kualitas berkelanjutan
- [ ] Cakupan test naik bertahap; tambahkan CI (lint + test).
- [ ] Perbaiki bug kecil (`__str__`, regex UA middleware).

---

## 6. Daftar "Quick Wins" (dampak besar, usaha kecil)
1. Hapus `import random` & data dummy di `api_dashboard.py`.
2. Tambah `.gitignore` root.
3. Satukan konstanta `k`/`T_steam` (langsung menaikkan konsistensi semua metrik efisiensi).
4. Perbaiki `MachineManualLog.__str__` (tambah `return`).
5. Cache `get_daily_summary` (hindari perhitungan berulang di `get_steam_sales`).

---

## 7. Pertanyaan untuk Didiskusikan Bersama
1. **Nilai `k` mana yang benar secara lapangan?** Apakah pernah dikalibrasi dari data batch nyata, atau perlu kita regresi ulang dari historis `MachineMinuteLog`?
2. Apakah setiap mesin sudah punya data fisik (`u_value`, `surface_area`, kapasitas air/kain, `c_machine`) terisi? Ini prasyarat untuk model energi berbasis neraca.
3. Apakah endpoint legacy (`/grafik`, `/api/machines`, dashboard server-rendered) masih dipakai pihak lain (mis. Google Sheets via `send_google_steam`, APIDOG)? Menentukan seberapa agresif kita boleh deprecate.
4. Target deployment produksi: tetap DevTunnel, atau ada domain/VM tetap? Menentukan setelan keamanan & TLS.
5. Prioritas Anda: **akurasi angka energi (fisika)** dulu, atau **kecepatan/pengalaman UI** dulu?

---

*Dokumen ini bersifat hidup — silakan tandai bagian yang ingin kita kerjakan lebih dulu, dan kita bisa turunkan menjadi task-task konkret beserta perubahan kodenya.*
