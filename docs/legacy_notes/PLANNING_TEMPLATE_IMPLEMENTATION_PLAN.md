# Implementation Plan — Production Planning Template ("Perencanaan Proses" Drag Board)

> Status: **DRAFT untuk evaluasi** — belum ada baris kode yang diubah. Dokumen ini dibuat sebelum implementasi dimulai, sesuai permintaan, agar desain bisa dikoreksi lebih dulu.
>
> Konteks lingkungan (hasil investigasi):
> - Backend: Django 5.2 + Django-Ninja pada port `8000` (dijalankan via Waitress).
> - Frontend "Port 8002" = React 19 + Vite SPA (`frontend/`), lihat komentar di `frontend/vite.config.js`: *"Port 8002 dipakai untuk staging pengganti Django SSR di port 8000"*.
> - Halaman referensi yang dimaksud user: `frontend/src/pages/SnapshotHistoryPivot.jsx`, dikonsumsi lewat `frontend/src/store/snapshotsApi.js`, disuplai oleh `monitoring/api_snapshots.py` (`GET /api/snapshots/timeline`).

Keputusan scope yang sudah dikonfirmasi bersama user sebelum dokumen ini ditulis:

| Keputusan | Pilihan yang dipilih |
|---|---|
| Cakupan | **Papan kapasitas multi-mesin** — drag blok Heat/Hold/Cool per mesin di timeline horizontal, gaya sama seperti Snapshot History tapi untuk rencana masa depan |
| Persistensi | **Disimpan ke database** (model baru `ProductionPlan` + turunannya), bukan sekadar alat visual sementara |
| Kalkulasi uap | **Reuse field statis** `Machine.average_steam_usage` (kg/h) saat fase HEAT/HOLD — konsisten dengan cara `api_snapshots.py` menghitung `steam_heatmap` sekarang |
| Hubungan ke `ProgramMaster` | **Independen** — durasi diisi manual per blok, tidak auto-fill dari `ProgramMaster` (bisa jadi enhancement lain hari) |
| Pengguna & lingkup | **Planner/supervisor produksi**, merencanakan **semua mesin** dalam satu papan per shift/hari |

---

## 1. Tujuan & Non-Tujuan

### 1.1 Tujuan
1. Planner bisa membuat rencana produksi per shift/hari dalam bentuk papan Gantt horizontal (mirip `SnapshotHistoryPivot`), satu baris per mesin.
2. Planner bisa **menambah "proses"** (satu siklus Heat → Hold → Cool) ke baris mesin tertentu dengan drag di timeline, lalu mengatur durasi tiap fase dengan drag batas antar-fase / ujung blok.
3. Planner bisa **menghapus proses** (menghapus 1 siklus penuh) atau menghapus fase individual bila perlu penyesuaian.
4. Ada **indikator total pemakaian uap (kg/h) yang dinamis** — baris heatmap di atas tabel yang otomatis re-render setiap kali blok ditambah/dihapus/diresize/dipindah, tanpa perlu klik "Refresh" atau submit form.
5. Rencana yang dibuat **disimpan ke database** sehingga bisa dibuka lagi, diedit, dibandingkan dengan histori aktual (`snapshot-history`), dan dilihat oleh shift lain.
6. Ada validasi dasar (tidak boleh dobel-booking 1 mesin pada waktu yang sama, durasi tidak boleh negatif/nol, blok tidak boleh keluar dari batas shift 24 jam).

### 1.2 Non-Tujuan (secara sadar dikeluarkan dari versi awal ini, jadi item "Fase Selanjutnya" di §9)
- **Tidak** mengintegrasikan `ProgramMaster` sebagai sumber default durasi (keputusan: independen).
- **Tidak** membangun kalkulasi uap berbasis fisika (`Q = m·cp·ΔT / h_fg`) — pakai `average_steam_usage` statis dulu.
- **Tidak** membangun scheduler otomatis/optimasi (algoritma penjadwalan otomatis, deteksi kapasitas boiler maksimum, dsb.) — ini murni alat *manual drag planning* + indikator agregat.
- **Tidak** membangun sinkronisasi real-time multi-user (WebSocket/live co-editing). Kolaborasi ditangani lewat model status Draft/Published + "last updated by" biasa (optimistic locking sederhana), bukan operational-transform.
- **Tidak** mengubah/menghapus fungsi `snapshot-history` yang sudah ada — keduanya akan hidup berdampingan, saling melengkapi (rencana vs. aktual).

---

## 2. Analisis Referensi: Apa yang Direuse dari `SnapshotHistoryPivot`

| Elemen di Snapshot History | Bisa direuse langsung? | Catatan adaptasi |
|---|---|---|
| Grid 30-menit + `TimeAxis` + `TimeGrid` (`HALF_HOURS=48`, `SHIFT_MINUTES=1440`) | ✅ Ya, hampir 1:1 | Rencana juga berbasis shift 06:00–06:00, 24 jam. Tetap tampilkan snapping ke grid 15 menit untuk drag (lebih presisi dari 30 menit tampilan). |
| Struktur tabel sticky (`sticky-col`, group rows per `MachineGroup`) | ✅ Ya | Sama persis, tinggal ganti isi baris dari "segments read-only" jadi "blocks yang bisa didrag". |
| `SteamHeatmap` (canvas per-menit, skala warna tetap) | ✅ Ya, dipakai ulang sebagai komponen bersama | Pindahkan ke `frontend/src/components/SteamHeatmap.jsx` supaya dipakai baik oleh Snapshot History maupun Planning (hindari duplikasi kode kanvas). |
| Interaksi drag-to-select (long-press 400ms → drag range → `rangeSelect`) | ⚠️ Sebagian — pola *pointer tracking* di `document` (bukan di elemen) dipakai ulang, tapi tujuannya beda: di Snapshot History untuk *memilih rentang waktu untuk dibaca*, di Planning untuk *membuat/mengubah blok*. Perlu state machine drag baru (§5.3). |
| `PHASE_COLORS` (`HEAT`/`STEADY`/`COOL`) | ✅ Ya, reuse dari `frontend/src/lib/phaseColors.js` | Tambahkan alias label "Hold" untuk `STEADY` khusus di konteks planning (di data historis disebut "Keeping", di planning user bilang "hold" — cukup ubah label tampilan, key tetap `STEADY` agar warna & logika konsisten). |
| Backend: `_hour_axis_labels()`, `_current_shift_start()`, `TOTAL_BUCKETS=1440` | ✅ Ya, pindahkan ke modul util bersama `monitoring/utils/shift_time.py` supaya dipakai oleh `api_snapshots.py` **dan** `api_planning.py` tanpa duplikasi. | Ini refactor kecil, tidak mengubah behavior snapshot-history. |
| Backend: perhitungan steam per-bucket (`_log_is_steam_active`, sum `average_steam_usage`) | ✅ Konsep direuse, tapi input datanya beda | Snapshot History membaca dari `MachineMinuteLog` (data historis nyata). Planning membaca dari `ProductionPlanBlock` (data rencana yang diinput manual). Rumus agregasinya sama. |
| Print (`handlePrint`, CSS `@media print`) | ✅ Ya, pola yang sama dipakai untuk cetak rencana produksi | |

**Kesimpulan:** ini bukan "tiru tampilan dari nol", tapi **refactor-and-extend** — komponen genuinely-shared (`SteamHeatmap`, `TimeAxis`, `TimeGrid`, util shift-time backend) diekstrak agar dipakai 2 halaman, sisanya (interaksi drag buat-blok, model data rencana) dibangun baru.

---

## 3. Model Data (Backend)

### 3.1 Entity baru

```python
# monitoring/models.py (rencana penambahan)

class ProductionPlan(models.Model):
    """Header rencana produksi untuk satu shift (06:00–06:00)."""
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]
    shift_date = models.DateField(help_text="Tanggal awal shift (jam 06:00), sama makna dgn shift_date di snapshot-history")
    name = models.CharField(max_length=150, blank=True, help_text="Nama rencana, misal: 'Rencana Shift A - 21 Agu'")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="production_plans_created")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="production_plans_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1, help_text="Dinaikkan setiap update tersimpan; untuk optimistic locking sederhana")

    class Meta:
        indexes = [models.Index(fields=["shift_date", "status"])]
        ordering = ["-shift_date", "-created_at"]

    def __str__(self):
        return f"{self.name or 'Rencana'} — {self.shift_date} ({self.status})"


class ProductionPlanBatch(models.Model):
    """
    Satu 'proses' (siklus Heat→Hold→Cool) yang ditempatkan pada satu mesin.
    Ini adalah unit atomik yang ditambah/dihapus lewat drag ('tambah/hapus proses').
    """
    plan = models.ForeignKey(ProductionPlan, on_delete=models.CASCADE, related_name="batches")
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="plan_batches")
    label = models.CharField(max_length=100, blank=True, help_text="Label bebas, misal: 'Batch 12 - PO-2231'")
    order = models.PositiveIntegerField(default=0, help_text="Urutan tampil bila >1 batch pada mesin yang sama")
    start_offset_minutes = models.PositiveIntegerField(help_text="Menit sejak shift_start (0–1439)")

    class Meta:
        ordering = ["machine_id", "start_offset_minutes"]
        indexes = [models.Index(fields=["plan", "machine"])]

    def __str__(self):
        return f"{self.machine.code} @ +{self.start_offset_minutes}m ({self.label or 'Batch'})"

    @property
    def total_duration_minutes(self):
        # ⚠️ CATATAN IMPLEMENTASI: property ini memicu query DB setiap dipanggil.
        # Endpoint GET /planning/plans/{id} WAJIB memakai prefetch_related('batches__blocks')
        # agar tidak terjadi N+1 query saat iterasi batches untuk membangun response.
        # Contoh: ProductionPlan.objects.prefetch_related('batches__blocks').get(pk=pk)
        return sum(b.duration_minutes for b in self.blocks.all())


class ProductionPlanBlock(models.Model):
    """Satu fase (Heat / Hold / Cool) di dalam sebuah ProductionPlanBatch."""
    PHASE_CHOICES = [
        ("HEAT", "Heating"),
        ("STEADY", "Hold / Keeping"),   # key disamakan dgn PHASE_COLORS.STEADY di frontend
        ("COOL", "Cooling"),
    ]
    batch = models.ForeignKey(ProductionPlanBatch, on_delete=models.CASCADE, related_name="blocks")
    phase = models.CharField(max_length=10, choices=PHASE_CHOICES)
    sequence = models.PositiveSmallIntegerField(help_text="0=Heat, 1=Hold, 2=Cool — urutan tetap dalam satu batch")
    duration_minutes = models.PositiveIntegerField()

    class Meta:
        ordering = ["batch_id", "sequence"]
        unique_together = [("batch", "sequence")]

    def __str__(self):
        return f"{self.batch} · {self.phase} · {self.duration_minutes}m"
```

**Kenapa 3 level (`Plan` → `Batch` → `Block`)** dan bukan 1 tabel flat berisi `phase` langsung di bawah `Plan`?
- Sesuai permintaan user: *"setiap kita menambahkan atau menghapus suatu proses"* — "proses" = 1 siklus Heat-Hold-Cool. Kalau modelnya flat, "hapus 1 proses" harus query 3 baris dengan asumsi implisit pengelompokan by-time — rawan bug saat ada 2 proses yang bersebelahan di mesin yang sama. Dengan `Batch` sebagai unit eksplisit, "hapus proses" = 1 query `DELETE ProductionPlanBatch` (cascade ke bloknya), dan drag "geser seluruh proses" jadi 1 operasi ubah `start_offset_minutes` di `Batch`, bukan 3 baris `Block` yang harus disinkronkan manual.
- `duration_minutes` disimpan per-`Block`, sedangkan posisi waktu absolut (`start_offset_minutes`) hanya disimpan sekali di `Batch` — dihitung derivatif: `block[0]` mulai di `batch.start_offset_minutes`, `block[1]` mulai di `+ block[0].duration`, dst. Ini mencegah state yang tidak konsisten (misal Hold mulai sebelum Heat selesai).

### 3.2 Field yang **tidak** ditambahkan (dan alasannya, untuk mencegah over-engineering)
- Tidak ada `steam_usage_kg_h` yang disimpan per-`Block`. Nilai ini **selalu dihitung dari `machine.average_steam_usage`** saat request (read-time), sesuai keputusan "reuse static". Kalau field mesin ini diubah admin di kemudian hari, semua rencana lama & baru otomatis konsisten — trade-off: rencana lama tidak "snapshot" nilai historisnya. Ini didokumentasikan sebagai keputusan sadar di §8 (Risiko).
- Tidak ada FK ke `ProgramMaster` (sesuai keputusan independen).
- Tidak ada `color` custom per block — warna murni derivasi dari `phase` (konsisten dgn `PHASE_COLORS`), supaya tidak ada opsi yang bikin bingung secara visual dibanding halaman lain.

### 3.3 Migrasi
- File baru: `monitoring/migrations/0069_production_planning.py` (nomor lanjut dari `0068_machine_last_status_no_signal.py`, migrasi terakhir yang terdeteksi).
- Tambahan data migration kecil di migrasi yang sama atau migrasi terpisah `0070_add_production_planning_page_permission.py`:
  ```python
  PagePermission.objects.get_or_create(
      code="production_planning",
      defaults={"name": "Perencanaan Produksi", "url_name": "production_planning"},
  )
  ```
  (Konsisten dengan pola `PagePermission` yang sudah ada — lihat `monitoring/models.py:308` dan penggunaannya di `decorators.user_can_access_page`.)
- Setelah migrasi, **wajib langkah manual**: assign page `production_planning` ke `Position` yang relevan (misal `SUPV`) lewat admin — didokumentasikan di README/checklist rilis (§10), supaya tidak lupa (ini pola yang sama dipakai fitur lain, jadi bukan hal baru).

### 3.4 Constraint & validasi di level model/serializer (server-side)
1. `start_offset_minutes + total_duration_minutes(batch) <= 1440` (tidak boleh melewati batas shift 24 jam). Jika melebihi, tolak dengan error jelas — **tidak** auto-clamp diam-diam.
2. Tidak boleh ada 2 `ProductionPlanBatch` pada `machine` yang sama dalam `plan` yang sama dengan rentang waktu overlap (dicek di endpoint save, bukan di `Meta.constraints` DB karena overlap-check butuh logika, bukan unique constraint sederhana).
3. `duration_minutes` per `Block` minimal 1 menit (menolak 0/negatif — `PositiveIntegerField` sudah menolak negatif, tapi 0 perlu validasi eksplisit di serializer).
4. `sequence` harus 0,1,2 lengkap per batch (tidak boleh skip fase) — disederhanakan: setiap `Batch` **selalu** dibuat dengan 3 `Block` sekaligus (Heat+Hold+Cool) saat dibuat. Durasi 0 bermakna **"fase ini non-aktif/dilewati"** dan **hanya bisa diset lewat tombol eksplisit** ("Hapus fase ini" di tooltip blok), **bukan via drag** (drag di-clamp ke minimum 1 menit seperti dijelaskan di §7). Validasi `duration_minutes >= 0` di serializer (bukan `>= 1`) untuk mengizinkan nilai 0 yang sah dari aksi eksplisit tersebut.

   > ⚠️ **Implikasi UI:** Block dengan `duration_minutes = 0` **tidak boleh dirender sebagai sliver 0px** (akan membingungkan dan tidak bisa diklik). Tampilkan sebagai badge kecil "fase tidak aktif" di pinggir batch, atau sembunyikan sepenuhnya dengan indikator "○" di toolbar batch. Tentukan perilaku ini secara eksplisit di P5 agar tidak ambigu saat implementasi.

---

## 4. Desain API (Django-Ninja)

Ikuti pola yang sudah ada di `monitoring/api.py` (setiap fitur = 1 router file, didaftarkan dengan prefix).

```python
# monitoring/api_planning.py
planning_router = Router(tags=["Production Planning"])
PAGE_CODE = "production_planning"
```

| Method | Path | Fungsi |
|---|---|---|
| `GET` | `/planning/meta` | Daftar groups + machines (dengan `average_steam_usage`) untuk sidebar/legend — mirror `get_snapshot_meta` |
| `GET` | `/planning/plans?shift_date=YYYY-MM-DD` | List `ProductionPlan` untuk tanggal tsb (biasanya 0-1, tapi bisa >1 draft) |
| `POST` | `/planning/plans` | Buat `ProductionPlan` baru (kosong) untuk `shift_date` tertentu |
| `GET` | `/planning/plans/{id}` | Detail penuh: semua `batches` + `blocks`, plus **`steam_preview`** terhitung (lihat §6) — bentuk response mirror `get_snapshot_timeline` (grup→mesin→segments) agar frontend bisa reuse komponen tampilan yang sama |
| `PUT` | `/planning/plans/{id}` | **Bulk replace** seluruh `batches`/`blocks` dalam satu request (lihat §4.1 kenapa bulk, bukan CRUD granular per-block) + optimistic lock via `version` |
| `POST` | `/planning/plans/{id}/publish` | Ubah status `DRAFT` → `PUBLISHED` |
| `DELETE` | `/planning/plans/{id}` | Hapus rencana (hanya jika `DRAFT`, atau perlu permission tambahan jika `PUBLISHED`) |
| `POST` | `/planning/plans/{id}/duplicate` | Duplikat rencana ke `shift_date` lain (memudahkan "copy rencana kemarin") |

Registrasi di `monitoring/api.py`:
```python
from monitoring.api_planning import planning_router
api.add_router("/planning", planning_router)
```

### 4.1 Kenapa "bulk replace" (`PUT` seluruh plan), bukan REST granular (`POST`/`PATCH`/`DELETE` per-block)?
Drag-and-drop planning menghasilkan banyak perubahan kecil berurutan (drag durasi, pindah blok, tambah/hapus proses) dalam waktu singkat. Dua opsi:
- **(A) Granular**: setiap drag-end memicu 1 request API. Risiko: request storm saat resize (mousemove cepat), race condition antar-request, kompleksitas retry/undo.
- **(B) Bulk replace + client-side state**: semua editing terjadi di state React lokal (instan, tanpa network), lalu tombol **"Simpan"** eksplisit mengirim seluruh struktur `batches[]` sekali jalan; backend menghapus & membuat ulang batch/block dalam 1 transaksi (`transaction.atomic()`), increment `version`.

**Keputusan: opsi (B)**, karena:
1. Selaras dengan sifat alat ini — perencanaan, bukan sistem transaksional real-time. Tidak masalah kalau belum tersimpan sampai user klik Simpan (dengan indikator "unsaved changes" + `beforeunload` guard).
2. Jauh lebih sederhana untuk 90% interaksi (drag berkali-kali sebelum akhirnya "pas").
3. Auto-save sebagai **debounced background PUT tiap ~5 detik ketika ada perubahan** (bukan tiap gesture) bisa ditambahkan di fase lanjutan sebagai enhancement (opsional), tanpa mengubah kontrak API.

> ⚠️ **Catatan efisiensi untuk fase P8 (autosave):** Strategi "hapus semua → insert ulang" sangat efisien untuk Simpan manual (jarang terjadi). Namun bila autosave debounce ditambahkan di P8, setiap 5 detik akan terjadi DELETE + INSERT hingga 90+ baris untuk plan besar (30 batch × 3 block). Pada saat itu, pertimbangkan upgrade ke **upsert**: update baris yang ada (cocokkan via `clientId` yang dikirim di payload), hapus yang hilang, insert yang baru. Ini tidak perlu mengubah kontrak API — `clientId` sudah ada di model state client (§5.2) dan bisa ditambahkan ke request body tanpa breaking change.

### 4.2 Skema request/response `PUT /planning/plans/{id}` (indikatif)
```jsonc
// Request body
{
  "version": 3,                 // optimistic lock — backend tolak (409) kalau version mismatch
  "name": "Rencana Shift A - 21 Agu",
  "notes": "",
  "batches": [
    {
      "machine_code": "JD03",
      "label": "Batch 12 - PO-2231",
      "start_offset_minutes": 120,
      "blocks": [
        { "phase": "HEAT",   "duration_minutes": 45 },
        { "phase": "STEADY", "duration_minutes": 90 },
        { "phase": "COOL",   "duration_minutes": 30 }
      ]
    }
  ]
}
```
```jsonc
// Response (setelah save) — reuse struktur mirip get_snapshot_timeline
{
  "id": 17,
  "version": 4,
  "shift_date": "2026-08-21",
  "status": "DRAFT",
  "groups": [
    {
      "group_name": "Proses Continuous",
      "machines": [
        {
          "code": "JD03", "name": "Jet Dyeing 03",
          "batches": [
            {
              "id": 101, "label": "Batch 12 - PO-2231",
              "start_offset_minutes": 120,
              "blocks": [
                { "phase": "HEAT", "start_pct": 8.33, "width_pct": 3.13, "duration_minutes": 45 },
                { "phase": "STEADY", "start_pct": 11.46, "width_pct": 6.25, "duration_minutes": 90 },
                { "phase": "COOL", "start_pct": 17.71, "width_pct": 2.08, "duration_minutes": 30 }
              ]
            }
          ]
        }
      ]
    }
  ],
  "steam_preview": { "values": [/* 1440 angka kg/h */], "max_kg_h": 5400.0, "unit": "kg/h" },
  "conflicts": []   // list mesin+rentang yang overlap, jika ada (di edge case race antar-tab)
}
```

---

## 5. Desain Frontend

### 5.1 Struktur file baru
```
frontend/src/
  pages/
    ProductionPlanning.jsx        # halaman utama (baru)
  store/
    planningApi.js                # RTK Query slice (baru)
  components/
    SteamHeatmap.jsx              # diekstrak dari SnapshotHistoryPivot.jsx (shared)
    TimeGridAxis.jsx              # diekstrak (TimeGrid + TimeAxis, shared)
    planning/
      PlanningBatchBlock.jsx      # 1 batch (Heat+Hold+Cool) sebagai unit draggable/resizable
      PlanningToolbar.jsx         # tombol Simpan, Publish, Duplikat, tanggal, dst
      PlanningMachineRow.jsx      # 1 baris mesin (drop target + render batches)
  lib/
    planningGeometry.js           # fungsi murni: pctToMinutes, minutesToPct, snapToGrid, overlapCheck (unit-testable, tanpa React)
```
Route baru di `App.jsx`:
```jsx
{ path: '/production-planning', element: <ProductionPlanning />, pageCode: 'production_planning' },
```
Menu baru di `Layout.jsx` → `NAV_ITEMS` (icon misal `CalendarClock` dari `lucide-react`, sudah dependency).

### 5.2 Model state di client (sebelum disave)
```js
// Bentuk in-memory, 1:1 dengan payload PUT, plus field UI-only (id sementara utk batch baru = uuid client)
plan = {
  id, version, shiftDate, name, notes,
  batchesByMachine: {
    JD03: [
      { clientId: 'b_abc', id: 101, label: '', startOffsetMinutes: 120,
        blocks: [
          { phase: 'HEAT', durationMinutes: 45 },
          { phase: 'STEADY', durationMinutes: 90 },
          { phase: 'COOL', durationMinutes: 30 },
        ] },
    ],
  },
  isDirty: true,
}
```
Disimpan di **local component state** (`useState`/`useReducer`), **bukan** Redux store global — karena ini working-draft yang hidupnya hanya selama halaman terbuka (mirip form editor), sedangkan Redux/RTK Query dipakai murni untuk data-fetching layer (`useGetPlanQuery`, lalu di-`useEffect` sekali untuk seed reducer lokal). Ini konsisten dengan komentar di `apiSlice.js`: RTK Query dipakai untuk caching/fetch, bukan sebagai state-management form.

Rekomendasi: gunakan `useReducer` dengan actions eksplisit (`ADD_BATCH`, `REMOVE_BATCH`, `MOVE_BATCH`, `RESIZE_PHASE_BOUNDARY`, `RESIZE_BATCH_END`) — supaya setiap perubahan mudah diuji unit (reducer murni) dan mudah ditambah "undo" di masa depan (fase lanjutan) karena actions sudah terstruktur.

### 5.3 Interaksi Drag (state machine)

Empat gesture berbeda pada 1 baris-mesin, dibedakan dari **target elemen** yang di-`mousedown`:

| Target elemen | Gesture | Efek |
|---|---|---|
| Area kosong di track mesin (bukan di atas blok manapun) | Klik lalu drag horizontal | **Buat proses baru**: preview blok semi-transparan mengikuti pointer; saat mouse-up, buat `Batch` baru dengan durasi default (misal Heat 30m / Hold 60m / Cool 20m — total durasi awal = jarak drag, dibagi proporsional 30/60/20 sebagai starting point yang lalu bisa diresize) pada offset = titik mousedown, snap ke grid 15 menit |
| Badan blok (bagian tengah salah satu fase, bukan di ujung) | Drag horizontal | **Pindahkan seluruh batch** (geser waktu mulai), durasi internal tidak berubah; snap ke grid 15 menit; dibatasi tidak boleh keluar 0–1440 dan tidak overlap batch lain di mesin yang sama (live-highlight merah bila akan overlap, mouse-up dibatalkan/snap-back bila masih overlap) |
| Garis batas antar-fase (misal antara Heat dan Hold) — handle selebar ±4px | Drag horizontal | **Redistribusi durasi**: durasi fase kiri & kanan berubah berlawanan (misal Heat -5m, Hold +5m), total durasi batch & waktu mulai batch tidak berubah. Dibatasi minimum 1 menit per fase supaya tidak collapse ke 0 secara tidak sengaja (kalau user memang mau mematikan fase Hold, sediakan cara eksplisit: tombol kecil "hapus fase ini" di tooltip blok, bukan lewat drag ke 0) |
| Ujung kanan blok Cool (ujung terakhir batch) | Drag horizontal | **Perpanjang/perpendek total durasi** dengan menambah/mengurangi durasi Cool saja (fase lain tetap) |
| Klik kanan pada blok, atau tombol "×" yang muncul saat hover blok | Klik | **Hapus seluruh proses (batch)** — dengan konfirmasi ringan (misal toast "Batch dihapus, Ctrl+Z untuk batalkan" 5 detik, bukan modal blocking) |

Semua drag memakai pola yang **sama** dengan `SnapshotHistoryPivot` (`document.addEventListener('mousemove'/'mouseup', ...)` di `useEffect`, bukan listener per-elemen) supaya drag tidak putus saat pointer keluar dari elemen asal — ini pelajaran yang sudah "battle-tested" di kode existing (`dragRef` pattern, baris 436–532 `SnapshotHistoryPivot.jsx`), akan diadaptasi 1:1 strukturnya.

**Snap-to-grid**: semua posisi/durasi dibulatkan ke kelipatan 15 menit secara default (`GRID_MINUTES = 15`), dengan indikator visual grid vertikal setiap 15 menit saat sedang men-drag (lebih rapat dari `TimeGrid` biasa yang hanya per 30 menit) — bisa dibuat togglable ("mode presisi 5 menit") sebagai nice-to-have, bukan wajib di v1.

**Mobile/touch**: v1 fokus desktop (mouse) mengikuti pola existing yang juga desktop-first (long-press 400ms dipakai utk membedakan klik vs drag di Snapshot History, tapi touch events tidak terlihat di-handle eksplisit di sana). Dicatat sebagai keterbatasan yang diketahui (§8), bukan blocker.

### 5.4 Rendering
- Baris mesin: sama seperti `TimelineBar`, tapi `machine.segments` (read-only) diganti `machine.batches[].blocks[]` yang masing-masing dirender sebagai `<div>` absolute-positioned dengan `left/width` dalam persen (bukan flex seperti existing, karena posisi sekarang punya gap antar-batch yang harus direpresentasikan — beda dari Snapshot History yang segmennya selalu contiguous 100%).
- Boundary handle & drag-move menggunakan `cursor: ew-resize` / `cursor: grab` sesuai target, dan `onMouseDown` men-set `dragRef.current = { mode: 'move'|'resize-boundary'|'resize-end'|'create', ... }`.
- Baris **"Uap (kg/h)"** di atas tabel: komponen `SteamHeatmap` (shared, lihat §2) menerima `values` yang dihitung **client-side, sinkron di setiap render** (bukan nunggu network) — lihat §6.1. Ini yang membuat indikator "dinamis" sesuai requirement user: tiap dispatch reducer (`ADD_BATCH`/`REMOVE_BATCH`/resize) → state berubah → `useMemo` steam values dihitung ulang → canvas re-paint, tanpa round-trip ke server.

### 5.5 Wireframe (tekstual)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ [Tanggal: ◀ 21 Agu 2026 ▶]  [Status: DRAFT]  [Simpan] [Publish] [Duplikat] │
├────────────────────────────────────────────────────────────────────────────┤
│ Mesin        │ 06  07  08  09  10  11  12  13  14 ... (grid jam, sticky)   │
├──────────────┼──────────────────────────────────────────────────────────── │
│ Uap (kg/h)   │ ░░░▓▓▓▓▓████████░░░░░░░░▓▓▓▓░░░░ (heatmap, live update)     │
├──────────────┼──────────────────────────────────────────────────────────── │
│ Proses Cont. │ (group header)                                             │
│ JD03         │   [Heat|Hold|Cool]         [Heat|Hold|Cool]                │
│              │   ← drag badan = pindah, drag pinggir = resize, klik empty │
│              │     area = buat proses baru →                             │
│ JD05         │                  [Heat|Hold|Cool]                         │
├──────────────┴──────────────────────────────────────────────────────────── │
│ Legend: 🟥 Heat 🟧 Hold 🟦 Cool   Uap: 0 3k 4k 5k 6k 7k 8k+                │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Kalkulasi Indikator Uap Dinamis

### 6.1 Formula (identik dengan yang sudah dipakai `api_snapshots.py`, lihat `_log_is_steam_active`)
Untuk setiap menit `t` dalam shift (0..1439):

```
steam(t) = Σ machine.average_steam_usage
           untuk setiap Batch aktif pada menit t
           dengan fase saat itu ∈ {HEAT, STEADY}   // Cooling TIDAK memakai uap
```

- Dihitung **client-side** di `frontend/src/lib/planningGeometry.js` (`computeSteamTimeline(batchesByMachine, machinesByCode)`), murni JS, `O(machines × minutes)` yang untuk skala pabrik ini (puluhan mesin × 1440 menit) masih sangat ringan (<100k operasi) — tidak perlu web worker.
- Dibungkus `useMemo(() => computeSteamTimeline(...), [batchesByMachine])` di `ProductionPlanning.jsx` supaya hanya dihitung ulang saat state batch benar-benar berubah, bukan setiap render karena hover, dsb.
- **Backend juga menghitung ulang** nilai yang sama persis (`steam_preview` di response `GET/PUT /planning/plans/{id}`) — dipakai untuk: (a) tampilan awal sebelum interaksi apapun (SSR-first-paint), (b) sumber kebenaran saat cetak/export, (c) sanity-check saat QA (bandingkan hasil client vs server, harus identik — jadikan test case).
- Kode kalkulasi backend ini **wajib** diletakkan di 1 fungsi shared (`monitoring/utils/steam_calc.py`, dipakai baik oleh `api_planning.py` maupun — sebagai refactor — oleh `api_snapshots.py`) supaya rumus tidak drift antara 2 tempat, mengingat `IMPROVEMENT_PLAN.md` sudah mencatat masalah serupa (P5: "logika terduplikasi").

### 6.2 Skala warna
Reuse `STEAM_HEAT_SCALE` yang sudah ada (0/3k/4k/5k/6k/7k/8k+) — **tidak** dibuat skala baru, supaya operator yang biasa baca Snapshot History langsung paham indikator di halaman Planning tanpa belajar ulang.

### 6.3 Indikator tambahan yang disarankan (opsional, murah untuk ditambahkan sekalian)
- Angka **peak kg/h** dan **jam terjadinya peak** ditampilkan sebagai teks kecil di sebelah heatmap (`max_kg_h` sudah dihitung, tinggal render).
- Badge peringatan jika `max_kg_h` melebihi kapasitas boiler yang dikonfigurasi (kalau ada nilai referensi di `GlobalSettings`/`BoilerDailyMetric` — perlu dicek lebih lanjut apakah ada field "kapasitas maksimum boiler"; jika tidak ada, ini jadi **open question** di §8, jangan diasumsikan sembarangan).

---

## 7. Validasi & Edge Cases

| Kasus | Perilaku yang diharapkan |
|---|---|
| Drag batch sampai overlap batch lain di mesin yang sama | Highlight merah selama drag; saat mouse-up, batch snap-back ke posisi sebelumnya (tidak commit) |
| Drag batch sampai keluar batas shift (offset+durasi > 1440) | Clamp ke batas 1440 saat drag (tidak error, langsung dibatasi visual) |
| Resize boundary antar-fase sampai salah satu fase jadi < 1 menit | Clamp di 1 menit sebagai minimum, tidak sampai 0 lewat drag (0 hanya lewat aksi eksplisit "hapus fase") |
| User menutup tab/browser saat ada `isDirty=true` | `window.onbeforeunload` menampilkan konfirmasi browser native |
| Dua tab membuka & edit `ProductionPlan` yang sama | `version` mismatch saat `PUT` → response `409 Conflict` → frontend tampilkan modal "Rencana sudah diubah pihak lain, muat ulang?" (bukan auto-merge, terlalu kompleks utk v1) |
| Mesin dengan `average_steam_usage = 0` (belum dikalibrasi) atau `is_active=False` | Tetap muncul di papan (agar tidak "hilang" tanpa penjelasan), tapi diberi badge "belum ada data uap" pada baris tersebut, kontribusi ke heatmap = 0 |
| `ProductionPlan` untuk `shift_date` yang sama dibuat 2x oleh user berbeda | Diizinkan (multi-draft), tapi UI menampilkan list draft yang ada utk tanggal tsb agar user tidak tidak sadar sudah ada draft lain (mencegah kerja duplikat) |
| Publish rencana yang punya machine dengan `is_active=False` di tengah plan | Tampilkan warning non-blocking saat publish ("mesin X sudah tidak aktif"), tidak mem-block |

---

## 8. Risiko & Pertanyaan Terbuka (perlu keputusan/eksplorasi lanjutan)

1. **Snapshot nilai `average_steam_usage`**: karena tidak disimpan per-block (§3.2), rencana lama akan "berubah" retroaktif kalau admin mengubah kalibrasi mesin. *Rekomendasi: terima trade-off ini untuk v1 (lebih simple), tapi tambahkan `updated_at` mesin ke response supaya UI bisa kasih badge "kalibrasi steam mesin ini diubah setelah rencana dibuat" di fase lanjutan.*
2. **Kapasitas boiler maksimum**: belum ditemukan field eksplisit "kapasitas boiler (kg/h)" di model saat investigasi awal (`BoilerDailyMetric` berisi data historis konsumsi, bukan kapasitas nominal). Perlu konfirmasi ke user apakah nilai ini ada di tempat lain (`GlobalSettings`?) sebelum badge peringatan §6.3 dibangun.
3. **Siapa yang boleh `publish`/`delete` rencana yang sudah `PUBLISHED`?** Perlu keputusan permission granular (apakah cukup 1 page-code `production_planning`, atau perlu 2 level seperti `production_planning_edit` vs `production_planning_view`)? Untuk v1 disarankan 1 page-code saja (sederhana), granularity lebih halus jadi fase lanjutan bila terbukti dibutuhkan.
4. **Touch/tablet support** belum masuk scope v1 (§5.3) — perlu dikonfirmasi apakah planner benar-benar hanya pakai desktop/laptop di lapangan.
5. **Retensi data**: apakah rencana `DRAFT` lama (misal >90 hari, tidak pernah di-publish) perlu auto-archive/cleanup job? Belum ada keputusan, dicatat sebagai follow-up housekeeping, bukan blocker rilis v1.
6. **⚠️ Ketidakselarasan dengan IMPROVEMENT_PLAN Fase 2 (model energi berbasis neraca fisika)**: Dokumen `IMPROVEMENT_PLAN.md` menetapkan Fase 2 adalah upgrade kalkulasi uap ke model neraca energi (`Q = m·cp·ΔT / h_fg`) menggantikan `average_steam_usage` statis. Planning ini **secara sadar memilih `average_steam_usage` statis** (konsisten dengan kondisi saat ini), tapi tanpa koordinasi eksplisit akan timbul konflik: saat Fase 2 dieksekusi, heatmap uap di `SnapshotHistoryPivot` (data aktual) akan berbasis neraca fisika, sementara heatmap di `ProductionPlanning` (rencana) masih `average_steam_usage` — operator membaca dua angka dengan metodologi berbeda tanpa tahu. *Rekomendasi: saat IMPROVEMENT_PLAN Fase 2 dieksekusi, revisit `steam_calc.py` yang dibuat di P2 dan putuskan apakah Planning juga ikut upgrade ke neraca fisika (lebih akurat, tapi butuh data field mesin terisi) atau tetap pakai statis (lebih simpel, tapi beda metodologi). Keputusan ini harus dibuat eksplisit, bukan dibiarkan drift diam-diam.*

---

## 9. Fase Implementasi (Roadmap Bertahap)

Rekomendasi dieksekusi berurutan (masing-masing bisa jadi 1 PR/commit terpisah, dapat diverifikasi sendiri-sendiri sebelum lanjut):

| Fase | Estimasi | Isi | Definisi selesai |
|---|---|---|---|
| **P0 — Refactor shared components** | ~½ hari | Ekstrak `SteamHeatmap`, `TimeGrid`/`TimeAxis` dari `SnapshotHistoryPivot.jsx` ke `components/` bersama; ekstrak util shift-time backend ke `monitoring/utils/shift_time.py`. **Tidak ada perubahan behavior** halaman Snapshot History (regresi harus nol). | Snapshot History tetap identik secara visual & fungsional; kode siap dipakai ulang |
| **P1 — Model & migrasi backend** | ~1 hari | Tambah `ProductionPlan`, `ProductionPlanBatch`, `ProductionPlanBlock` + migrasi + admin registration (read-only dulu di Django admin, untuk debugging) + `PagePermission` baru | `python manage.py migrate` sukses; bisa create/lihat data lewat `/admin/` |
| **P2 — API backend (read + write dasar)** | ~2 hari | `api_planning.py` lengkap (§4), termasuk `steam_calc.py` shared, unit test kalkulasi steam & overlap-validation | Endpoint bisa dites lewat Swagger/Ninja docs (`/api/docs`), test kalkulasi lulus |
| **P3 — Frontend read-only view** | ~1 hari | Halaman `ProductionPlanning.jsx` menampilkan papan (tanpa drag interaktif dulu) dari data API, termasuk heatmap uap | Bisa lihat rencana existing di UI, cocok dgn data API |
| **P4 — Drag: create & move batch** | ~2 hari | Implementasi gesture "buat proses baru" & "pindahkan proses" (state machine §5.3, subset dulu) | Bisa tambah/pindah proses, tersimpan lewat tombol Simpan, muncul lagi setelah reload |
| **P5 — Drag: resize (boundary & ujung) + hapus** | ~2 hari | Sisa gesture (§5.3), termasuk hapus batch & hapus fase individual (via tombol eksplisit — bukan drag ke 0), validasi overlap/clamp, render block `duration=0` (§3.4) | Semua interaksi di §5.3 & §7 berfungsi sesuai tabel |
| **P6 — Dinamisasi indikator uap real-time** | ~½ hari | Pastikan `computeSteamTimeline` client-side terpanggil di setiap perubahan state (§6.1), termasuk optimasi `useMemo` | Heatmap berubah instan saat drag/tambah/hapus, tanpa lag terasa & tanpa network call tambahan |
| **P7 — Publish, duplicate, print, permission wiring** | ~1 hari | Tombol publish/duplicate, layout cetak A4, assign `PagePermission` ke `Position`, entri menu di `Layout.jsx` | Fitur end-to-end bisa dipakai planner sungguhan dari menu utama |
| **P8 (opsional/lanjutan)** | ~3–5 hari | Autosave debounce (+ evaluasi upsert, lihat §4.1), undo/redo, badge "kalibrasi berubah", integrasi `ProgramMaster` sebagai default (jika nanti diputuskan), kapasitas boiler warning, dukungan touch | Sesuai kebutuhan setelah v1 dipakai nyata |

**Rekomendasi rilis:** P0–P3 bisa digabung 1 milestone ("papan bisa dilihat"), P4–P6 milestone kedua ("papan bisa diedit + indikator dinamis" — ini inti requirement user), P7 milestone ketiga ("siap dipakai operasional").

---

## 10. Checklist Rilis (jangan sampai terlupa, berdasarkan pola yang sudah ada di repo)

- [ ] Migrasi dijalankan di environment yang benar (`python manage.py migrate`)
- [ ] `PagePermission` baru (`production_planning`) di-assign ke `Position` yang sesuai lewat `/admin/`
- [ ] Entri menu ditambahkan di `Layout.jsx` `NAV_ITEMS`
- [ ] Route ditambahkan di `App.jsx` `ROUTES`
- [ ] `apiSlice.js` tagTypes ditambah `'ProductionPlanning'`
- [ ] Test manual: 2 user berbeda edit rencana yang sama → cek behavior `409 Conflict`
- [ ] Test manual: bandingkan angka `steam_preview` dari backend vs hasil hitung client (`computeSteamTimeline`) — harus identik
- [ ] Regresi: halaman `/snapshot-history` masih berfungsi sama setelah refactor P0

---

## 11. Ringkasan Perubahan File (estimasi)

**Backend**
- `monitoring/models.py` — tambah 3 model baru
- `monitoring/migrations/0069_production_planning.py` (baru)
- `monitoring/migrations/0070_add_production_planning_page_permission.py` (baru, data migration)
- `monitoring/utils/shift_time.py` (baru — hasil ekstraksi dari `api_snapshots.py`)
- `monitoring/utils/steam_calc.py` (baru — shared formula §6.1)
- `monitoring/api_snapshots.py` — refactor kecil untuk pakai util shared (tanpa ubah behavior)
- `monitoring/api_planning.py` (baru — router lengkap §4)
- `monitoring/api.py` — daftarkan `planning_router`
- `monitoring/admin.py` — register 3 model baru (read-only inlines untuk debug)
- `monitoring/decorators.py` — tidak berubah (sudah generic, tinggal dipakai dgn `PAGE_CODE` baru)

**Frontend**
- `frontend/src/pages/ProductionPlanning.jsx` (baru)
- `frontend/src/store/planningApi.js` (baru)
- `frontend/src/store/apiSlice.js` — tambah tagType
- `frontend/src/components/SteamHeatmap.jsx` (baru, hasil ekstraksi)
- `frontend/src/components/TimeGridAxis.jsx` (baru, hasil ekstraksi)
- `frontend/src/components/planning/PlanningBatchBlock.jsx`, `PlanningToolbar.jsx`, `PlanningMachineRow.jsx` (baru)
- `frontend/src/lib/planningGeometry.js` (baru — fungsi murni, unit-testable)
- `frontend/src/pages/SnapshotHistoryPivot.jsx` — refactor kecil (pakai komponen shared, behavior tidak berubah)
- `frontend/src/App.jsx` — tambah route
- `frontend/src/components/Layout.jsx` — tambah menu

---

## 12. Yang Perlu Anda Evaluasi Sebelum Implementasi Dimulai

Mohon konfirmasi/koreksi hal-hal berikut sebelum saya mulai coding (bagian paling rawan salah asumsi):

1. **Struktur 3-level `Plan → Batch → Block`** (§3.1) — apakah "1 proses = 1 siklus Heat-Hold-Cool" ini benar sesuai maksud Anda, atau ada kasus proses yang tidak selalu 3 fase (misal ada proses tanpa Cool, atau dengan fase tambahan seperti "Rinse")?
2. **Snap grid 15 menit** (§5.3) — cukup presisi, atau butuh 5 menit / bebas (tanpa snap)?
3. **Model penyimpanan "bulk save via tombol Simpan"** (§4.1) — apakah workflow ini oke, atau Anda menginginkan autosave otomatis dari awal (setiap perubahan langsung tersimpan tanpa tombol)?
4. **Cakupan v1 (P0–P6)** di §9 — apakah publish/permission (P7) memang bisa menyusul di iterasi berikutnya, atau harus sekaligus di rilis pertama?
5. Apakah ada nilai **kapasitas boiler maksimum (kg/h)** di tempat lain yang saya lewatkan saat investigasi (§8 poin 2), untuk dipakai sebagai referensi warning di indikator uap?

Setelah poin-poin di atas dikonfirmasi, saya akan mulai dari **Fase P0** (refactor shared components, zero-risk terhadap fitur existing) lalu berlanjut sesuai roadmap §9.

---

## 13. Riwayat Perubahan Dokumen

| Tanggal | Bagian | Perubahan |
|---|---|---|
| 2026-08-20 | §3.1 (`total_duration_minutes`) | Tambah catatan peringatan **wajib `prefetch_related('batches__blocks')`** di endpoint GET untuk mencegah N+1 query saat iterasi batches. |
| 2026-08-20 | §3.4 poin 4 | Perjelas **kontradiksi `duration=0` vs drag clamp 1 menit**: durasi 0 = fase non-aktif, hanya via tombol eksplisit (bukan drag). Tambahkan panduan render UI untuk block `duration=0` agar tidak jadi sliver 0px yang membingungkan. Dipindahkan sebagai item eksplisit di checklist P5. |
| 2026-08-20 | §4.1 | Tambah catatan **efisiensi bulk replace vs upsert**: strategi "hapus semua → insert ulang" OK untuk Simpan manual, tapi harus dievaluasi ke upsert saat autosave debounce ditambahkan di P8 (karena bisa 90+ DELETE+INSERT setiap 5 detik). |
| 2026-08-20 | §8 (risiko baru #6) | Tambah risiko **ketidakselarasan model energi Planning vs `IMPROVEMENT_PLAN` Fase 2** (neraca fisika `Q = m·cp·ΔT / h_fg`). Tanpa koordinasi eksplisit, dua halaman akan tampilkan angka uap dengan metodologi berbeda saat Fase 2 dieksekusi. |
| 2026-08-20 | §9 (roadmap) | Tambah kolom **estimasi durasi** per fase (P0–P8) agar bisa diprioritasi saat ada resource/deadline constraint. Total P0–P7 estimasi ~9½ hari kerja. P8 tambahan ~3–5 hari. |
