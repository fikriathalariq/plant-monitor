# Implementation Plan v2 — Popup Edit Form, Integrasi ProgramMaster, Mode AUTO vs MANUAL

> Status: **DRAFT untuk evaluasi** — belum ada baris kode yang diubah untuk dokumen ini. Melanjutkan `PLANNING_TEMPLATE_IMPLEMENTATION_PLAN.md` (v1) yang **sudah diimplementasikan** (halaman `/production-planning` sudah bisa drag buat/pindah/resize proses + indikator uap dinamis).
>
> Dokumen ini **merevisi 1 keputusan v1** dan **menambah 2 kapabilitas baru**:
> 1. ~~Hubungan ke `ProgramMaster`: Independen~~ → **direvisi jadi terhubung** (durasi bisa auto-fill dari program yang dipilih).
> 2. **Baru:** Form popup (double-click) untuk mengedit batch secara presisi, sebagai pelengkap drag.
> 3. **Baru:** Pembedaan render/interaksi untuk mesin `operation_mode=AUTO` (Heat/Hold/Cool, seperti sekarang) vs `operation_mode=MANUAL` (on/off sederhana, selaras `mesin-aktif`/`ManualMachineUsage` yang sudah ada).

---

## 1. Rekap Permintaan User (verbatim, diterjemahkan ke requirement teknis)

| Permintaan user | Requirement teknis |
|---|---|
| "selain drag ada yang pop up juga... tekan dua kali, muncul pop up form, kita bisa ubah durasi-durasinya" | Tambah interaksi **double-click** pada sebuah batch → buka **modal edit** dengan input numerik durasi per fase (bukan hanya drag pixel-perfect) |
| "durasinya juga terhubung aja dengan Master Program... ada program yang ditargetkan, bisa langsung dimasukkan" | Modal punya **dropdown pilih `ProgramMaster`** → saat dipilih, auto-fill `durasi_heating_ideal` / `durasi_keeping_ideal` / `durasi_cooling_ideal` ke form (tetap bisa diedit manual setelahnya) |
| "auto machines nya, pake yang heat hold cool. Sedangkan yang manual, nanti pakai on off biasa aja (sama seperti sistem yang manual sekarang)" | Render papan **bercabang per `machine.operation_mode`**: AUTO → 3-fase (seperti sekarang), MANUAL → 1 blok on/off, konsisten dengan `Machine.MANUAL_STATUS_CHOICES` / `ManualMachineUsage.jsx` yang sudah ada |

---

## 2. Kondisi Saat Ini (v1, sudah live) — Baseline

Yang sudah berjalan dan **tidak akan diubah kecuali disebutkan eksplisit**:
- Model: `ProductionPlan` → `ProductionPlanBatch` → `ProductionPlanBlock` (3 blocks tetap: HEAT/STEADY/COOL, urutan 0/1/2).
- API: `monitoring/api_planning.py` (`/api/planning/...`), validasi `_validate_batches_payload` mewajibkan **selalu 3 blocks HEAT→STEADY→COOL** per batch untuk **semua mesin** (belum bercabang AUTO/MANUAL).
- Frontend: `ProductionPlanning.jsx` — drag-create (klik/drag di track kosong), drag-move (badan blok), drag-resize (batas fase & ujung Cool), hapus lewat tombol "×". Semua mesin (termasuk mesin `MANUAL`) saat ini **diperlakukan sama** — ini yang akan diperbaiki di v2.
- Steam calc (client `planningGeometry.js` & server `steam_calc.py`): aktif kalau `phase ∈ {HEAT, STEADY}`, tidak peduli `operation_mode` mesin.
- `Machine.operation_mode` sudah ada di model (`AUTO`/`MANUAL`), sudah dikirim di beberapa endpoint lain (`api_machines.py`), **tapi belum dikirim** di `/api/planning/meta` — perlu ditambahkan.
- `ProgramMaster` (`nama`, `suhu_max`, `durasi_ideal`, `durasi_heating_ideal`, `durasi_keeping_ideal`, `durasi_cooling_ideal`) sudah ada sebagai model independen, **belum ada relasi apapun** ke Planning.
- Sistem manual existing (referensi wajib disamakan): `Machine.MANUAL_STATUS_CHOICES` (`Stop`/`Running`/`Standby`/dst, tergantung `status_type`), tapi endpoint on/off cepat (`api_machines.py` toggle & `ManualMachineUsage.jsx`) **hanya memakai biner Running vs Stop** (`MANUAL_STATUS_RUNNING`/`MANUAL_STATUS_STOP` dari `monitoring/utils/manual_status.py`). → Ini pola yang direplikasi di Planning: **cukup ON (Running) vs tidak digambar (Stop)**, bukan 8 pilihan status manual penuh (`Standby`, `Preset...`, dst.) — sesuai kata user "on off biasa aja".

---

## 3. Perubahan Model Data

### 3.1 `ProductionPlanBatch` — tambah FK opsional ke `ProgramMaster`
```python
class ProductionPlanBatch(models.Model):
    ...
    program = models.ForeignKey(
        "ProgramMaster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_batches",
        help_text="Program target yang dipilih saat batch dibuat/diedit (opsional, hanya untuk mesin AUTO). "
                   "Disimpan untuk histori/pelaporan — durasi aktual tetap di ProductionPlanBlock, "
                   "TIDAK auto-sync kalau ProgramMaster diubah admin di kemudian hari.",
    )
```
**Kenapa disimpan sebagai referensi (bukan cuma dipakai sesaat untuk isi form)?**
Supaya nanti bisa dijawab "batch ini direncanakan pakai program apa" saat lihat papan/print, dan sebagai basis analitik masa depan (bandingkan rencana vs `ProgramMaster` vs `DyeingProcess` aktual). Trade-off yang sama seperti `average_steam_usage` di v1 (§8 v1): kalau `ProgramMaster` diedit setelah batch dibuat, batch **tidak** ikut berubah (snapshot di titik pemilihan, bukan live-link) — durasi sudah "lepas" begitu masuk ke `ProductionPlanBlock`.

### 3.2 `ProductionPlanBlock` — tambah pilihan fase `RUNNING` untuk mesin manual
```python
PHASE_CHOICES = [
    ("HEAT", "Heating"),
    ("STEADY", "Hold / Keeping"),
    ("COOL", "Cooling"),
    ("RUNNING", "Running (Manual On)"),   # BARU — khusus mesin operation_mode=MANUAL
]
```
- Untuk batch pada mesin **AUTO**: tetap wajib **persis 3 block** `HEAT, STEADY, COOL` (`sequence` 0/1/2) — **tidak berubah dari v1**.
- Untuk batch pada mesin **MANUAL**: wajib **persis 1 block** `RUNNING` (`sequence` 0) — durasinya = lama mesin menyala.
- `unique_together = [("batch", "sequence")]` tetap valid untuk kedua kasus (manual hanya punya sequence 0).
- **Tidak** ada migrasi skema DB yang wajib untuk field `choices` (Django biasanya membuat migrasi kosmetik `AlterField` saat `choices` berubah, tidak mengubah kolom fisik apa pun di PostgreSQL — aman, tidak butuh backfill).
- `duration_minutes` tetap `PositiveIntegerField` (Django secara resmi mengizinkan nilai `0` — non-negatif, bukan "positif ketat"). Tidak perlu `AlterField` ke `IntegerField`; cukup pastikan serializer/validasi API mengizinkan `>= 0` (fase non-aktif = 0) sesuai keputusan v1 §3.4.

### 3.3 Migrasi
- `monitoring/migrations/0071_planning_program_and_manual_phase.py`:
  - `AddField` `ProductionPlanBatch.program` (FK nullable ke `ProgramMaster`).
  - `AlterField` `ProductionPlanBlock.phase` (tambah pilihan `RUNNING` — kosmetik).

### 3.4 Validasi baru di `_validate_batches_payload` (`monitoring/api_planning.py`)
Ganti validasi "selalu 3 blocks" jadi **bercabang berdasarkan `machine.operation_mode`** (dicek dari DB, **bukan** dari klaim client, untuk keamanan):

```
untuk setiap batch:
    machine = machine_by_code[batch.machine_code]   # sudah di-query server-side
    if machine.operation_mode == "AUTO":
        wajib len(blocks) == 3 dan phase berurutan [HEAT, STEADY, COOL]
    elif machine.operation_mode == "MANUAL":
        wajib len(blocks) == 1 dan blocks[0].phase == "RUNNING"
    else:
        tolak (mode tidak dikenal)
```
Overlap-check, batas 1440 menit, dan optimistic-lock (`version`) **tidak berubah** — berlaku sama untuk kedua mode.

> ⚠️ **Proteksi race condition `operation_mode`:** Ada jeda antara waktu query `machine_by_code` dan waktu `transaction.atomic()` melakukan write. Jika admin mengubah `operation_mode` mesin tepat di antaranya, validasi bisa membaca mode lama tapi data tersimpan berdasarkan mode baru. Untuk menutup celah ini: query mesin di dalam `transaction.atomic()` menggunakan `Machine.objects.select_for_update().filter(code__in=machine_codes)` — ini mengunci baris mesin selama transaksi berlangsung dan mencegah admin memperbarui mode saat PUT sedang diproses. Biaya performa minimal karena transaksi ini singkat.

---

## 4. Perubahan API

### 4.1 `GET /planning/meta` — tambah field yang dibutuhkan frontend
```jsonc
{
  "groups": [...],
  "machines": [
    {
      "code": "JD03", "name": "Jet Dyeing 03", "group": "PRC",
      "average_steam_usage": 3200.0,
      "operation_mode": "AUTO"        // BARU
    },
    {
      "code": "MC12", "name": "Mesin Cont. 12", "group": "PRT",
      "average_steam_usage": 1800.0,
      "operation_mode": "MANUAL"      // BARU
    }
  ],
  "programs": [                       // BARU
    {
      "id": 5, "nama": "Program Dispers 130°C",
      "suhu_max": 130.0,
      "durasi_heating_ideal": 45.0,
      "durasi_keeping_ideal": 90.0,
      "durasi_cooling_ideal": 30.0
    }
  ],
  "grid_minutes": 15,
  "shift_minutes": 1440
}
```
`programs` diambil dari `ProgramMaster.objects.all().order_by("nama")` — daftar ini kemungkinan tidak besar (puluhan), aman di-fetch penuh sekali di meta (sama pola dengan `groups`/`machines`).

### 4.2 `GET/PUT /planning/plans/{id}` — sertakan `program` di response/payload batch
```jsonc
// response batch
{
  "id": 101, "label": "Batch 12", "start_offset_minutes": 120,
  "program_id": 5, "program_name": "Program Dispers 130°C",   // BARU (nullable)
  "blocks": [ ... ]
}
```
```jsonc
// request PUT payload batch
{
  "machine_code": "JD03",
  "label": "Batch 12 - PO-2231",
  "program_id": 5,                       // BARU (opsional, null jika tidak dipilih / mesin MANUAL)
  "start_offset_minutes": 120,
  "blocks": [
    { "phase": "HEAT", "duration_minutes": 45 },
    { "phase": "STEADY", "duration_minutes": 90 },
    { "phase": "COOL", "duration_minutes": 30 }
  ]
}
```
Untuk mesin `MANUAL`, payload batch jadi:
```jsonc
{
  "machine_code": "MC12",
  "label": "",
  "program_id": null,
  "start_offset_minutes": 480,
  "blocks": [
    { "phase": "RUNNING", "duration_minutes": 180 }
  ]
}
```

### 4.3 Tidak ada endpoint baru murni untuk "edit form"
Popup edit form di frontend **tetap memakai kontrak `PUT /planning/plans/{id}` (bulk-save) yang sama** seperti drag — modal hanya cara lain untuk mengubah state client sebelum tombol "Simpan" (sesuai keputusan v1 §4.1: bulk-replace, bukan granular). Ini menjaga 1 sumber kebenaran, tidak menambah kompleksitas backend.

---

## 5. Perubahan Frontend

### 5.1 Komponen baru: `PlanningBatchEditModal.jsx`
```
frontend/src/components/planning/PlanningBatchEditModal.jsx
```
**Trigger:** `onDoubleClick` pada elemen batch (bukan pada track kosong — double-click di track kosong tidak melakukan apa-apa, hanya single-click/drag yang membuat batch baru, sesuai perilaku v1 yang sudah ada).

**Isi form (bercabang menurut `operation_mode` mesin pemilik batch):**

**Untuk mesin AUTO:**
| Field | Tipe | Catatan |
|---|---|---|
| Label | text, opsional | "Batch 12 - PO-2231" |
| Program target | `<select>` dari `meta.programs`, opsional | Saat dipilih → isi otomatis 3 field durasi di bawah (lihat §5.2) |
| Jam mulai | time input (`HH:mm`, snap 15 menit) atau tampilkan sebagai "menit ke-X sejak 06:00" | Divalidasi 0–1439 |
| Durasi Heat (menit) | number input, min 0 | |
| Durasi Hold (menit) | number input, min 0 | |
| Durasi Cool (menit) | number input, min 0 | |
| Total (readonly) | dihitung otomatis dari 3 durasi | Info saja, bukan input |
| [Hapus proses] · [Batal] · [Simpan] | button | "Simpan" hanya commit ke **state client** (`dispatch`), *bukan* langsung ke server — tetap ikut alur "tombol Simpan" global di toolbar (v1 §4.1) |

**Untuk mesin MANUAL:**
| Field | Tipe | Catatan |
|---|---|---|
| Label | text, opsional | |
| Jam mulai | time input | |
| Durasi Running (menit) | number input, min 0 | Satu field saja — "on/off biasa" |
| [Hapus] · [Batal] · [Simpan] | button | |

**Validasi di modal (client-side, sebelum dispatch):**
- Semua durasi ≥ 1 menit kalau fase itu aktif, atau tepat 0 kalau fase mau ditiadakan (AUTO saja — konsisten §3.4 v1: Cool/Heat boleh 0 lewat aksi eksplisit). **Catatan:** minimum 1 menit (bukan 15) dipilih agar selaras dengan constraint server-side (`duration >= 0` di serializer, minimum 1 untuk fase aktif yang tidak boleh micro-duration) — kalau minimum di modal lebih besar dari server, user akan mendapat penolakan dari modal untuk nilai yang sebetulnya valid di server, yang membingungkan. Snap-to-grid 15 menit adalah *perilaku drag*, bukan batas minimum absolut — keduanya boleh berbeda.
- `start + total <= 1440`.
- Overlap check terhadap batch lain di mesin yang sama (pakai `hasOverlap` yang sudah ada di `planningGeometry.js`) — kalau bentrok, tampilkan pesan error inline, tombol Simpan disabled, **tidak** auto-clamp diam-diam (beda dari drag yang snap-back; di sini form harus dikoreksi manual dulu).

> 📝 **Input "Jam mulai": default sementara ke `HH:mm`** (sesuai keputusan yang belum dikonfirmasi di §10 poin 2). Alasan: lebih natural dibaca operator dibanding "menit ke-X", dan bisa ditampilkan langsung dari `shiftStart + startOffsetMinutes`. Tampilkan shift-start (06:00) sebagai label konteks di bawah input. Jika dikonfirmasi sebaliknya, hanya 1 baris konversi yang berubah.

### 5.2 Perilaku auto-fill dari `ProgramMaster`
- Saat dropdown "Program target" berubah (AUTO saja):
  - Isi `durasiHeat = program.durasi_heating_ideal ?? 0`, dst untuk Hold & Cool.
  - **Timpa langsung nilai form yang sedang diedit** (bukan cuma kalau kosong) — karena ini aksi eksplisit user memilih program, wajar kalau field ikut berubah. Kalau user sudah sempat mengetik manual lalu ganti pilihan program, tetap ditimpa (tidak ada "confirm dialog" tambahan — biar simpel; kalau nanti user komplain "kaget ketimpa", ini yang pertama direvisi).
  - `start_offset_minutes` (jam mulai) **tidak ikut berubah** oleh pemilihan program — hanya durasi.
  - Field durasi tetap **bisa diedit manual setelah auto-fill** (program hanya starting point, bukan lock).
- Saat form dibuka untuk **batch yang sudah ada** `program_id`-nya: dropdown pre-selected ke program itu, tapi durasi tetap menampilkan nilai `ProductionPlanBlock` tersimpan saat ini (bukan re-fetch dari `ProgramMaster` — karena bisa jadi sudah diedit manual setelah auto-fill pertama, dan `ProgramMaster` bisa sudah berubah sejak itu, lihat trade-off §3.1).
- Kalau dropdown diubah ke **"(Tidak ada program)"**: `program_id` diset `null`, durasi **tidak** direset ke 0 (tetap seperti sebelumnya) — melepas "label" program saja, bukan mengosongkan rencana.

### 5.3 Perubahan render papan: cabang AUTO vs MANUAL
Di `MachineRow` / `PlanningBatchBlock` (`ProductionPlanning.jsx`):

| Aspek | Mesin AUTO (tidak berubah dari v1) | Mesin MANUAL (baru) |
|---|---|---|
| Warna blok | 3 segmen warna beda (`PHASE_COLORS.HEAT/STEADY/COOL`) | **1 warna solid** `PHASE_COLORS.RUNNING` (emerald — sudah ada, dipakai di Snapshot History juga untuk mesin manual, jadi konsisten) |
| Handle resize | Ada garis batas antar-fase (2 handle internal) + handle ujung Cool | **Hanya 1 handle** di ujung kanan (perpanjang/perpendek durasi Running) — tidak ada batas internal karena cuma 1 fase |
| Drag-create default | Split 30/60/20 (`splitDefaultPhases`) | Langsung 1 block `RUNNING` durasi = jarak drag (atau default 60 menit kalau klik tanpa drag) — fungsi baru `createManualBlock(duration)` |
| Badge di dalam blok | Label fase kecil ("Heat"/"Hold"/"Cool") | Label "ON" atau nama batch saja |
| Double-click | Buka modal versi AUTO (3 field durasi + program) | Buka modal versi MANUAL (1 field durasi) |
| Kontribusi ke steam heatmap | HEAT & STEADY dihitung, COOL tidak | RUNNING dihitung (mirror `is_manual_on` / `MANUAL_STATUS_RUNNING` di sistem existing) |

**Deteksi mode:** dari `machinesByCode[code].operation_mode` (hasil `/planning/meta`, §4.1) — dipakai di level `MachineRow` untuk memilih varian render & drag-handler, diteruskan sebagai prop `mode` ke `PlanningBatchBlock`.

### 5.4 Perubahan `planningGeometry.js`
- `splitDefaultPhases(total)` — tetap ada, khusus AUTO.
- **Baru:** `createRunningBlock(total)` → `[{ phase: 'RUNNING', durationMinutes: total }]`, khusus MANUAL.
- **Baru:** `STEAM_ACTIVE_PHASES_BY_MODE = { AUTO: new Set(['HEAT','STEADY']), MANUAL: new Set(['RUNNING']) }` — dipakai di `computeSteamTimeline(batchesByMachine, machinesByCode)`: untuk tiap mesin, pilih set aktif berdasarkan `machinesByCode[code].operation_mode`, bukan hardcode `{HEAT, STEADY}` seperti v1.
- Perubahan yang sama (bercabang per mode) di `monitoring/utils/steam_calc.py::compute_steam_timeline_from_plan_batches` — **wajib sinkron** dengan versi client (sesuai prinsip v1 §6.1: rumus client & server harus identik, jadi test case).

> ⚠️ **Wajib: test guard sinkronisasi client vs server untuk mode MANUAL.** Dari v1 §6.1, sudah ada prinsip "bandingkan `steam_preview` dari backend vs `computeSteamTimeline` client — harus identik", tapi di Q1/Q5 di §9 tidak ada checkpoint eksplisit untuk ini. Tambahkan ke checklist Q5: *"jalankan skenario test plan dengan kombinasi mesin AUTO+MANUAL → bandingkan angka steam per-menit dari `steam_calc.py` vs `computeSteamTimeline` — harus identik untuk setiap mode"*. Tanpa test ini, perubahan `STEAM_ACTIVE_PHASES_BY_MODE` di salah satu sisi bisa lolos ke produksi diam-diam.

### 5.5 Perubahan `planFromApi` / `planToPayload`
- `planFromApi`: baca `program_id`/`program_name` dari response batch, simpan di state client (`batch.programId`, `batch.programName`).
- `planToPayload`: kirim `program_id: batch.programId ?? null` di setiap batch AUTO; untuk batch MANUAL selalu kirim `program_id: null` (tidak relevan, diabaikan backend juga karena mesin MANUAL).

---

## 6. Interaksi Gesture — Update Tabel Lengkap (menggantikan §5.3 v1)

| Target elemen | Mode mesin | Gesture | Efek |
|---|---|---|---|
| Track kosong | AUTO / MANUAL | Klik tanpa gerak (atau drag <2 grid) | Buat batch baru durasi default (AUTO: split 30/60/20 dari 60 menit; MANUAL: 1 block RUNNING 60 menit) |
| Track kosong | AUTO / MANUAL | Klik + drag horizontal | Buat batch baru, durasi = jarak drag (AUTO: displit proporsional; MANUAL: langsung 1 block) |
| Badan blok | AUTO / MANUAL | Drag horizontal | Pindah seluruh batch (waktu mulai berubah, durasi tetap) — **tidak berubah dari v1** |
| Badan blok | AUTO / MANUAL | **Double-click** | **[BARU]** Buka modal edit (§5.1) |
| Batas antar-fase (Heat\|Hold, Hold\|Cool) | **AUTO saja** | Drag | Redistribusi durasi kiri/kanan — **tidak berubah dari v1** |
| — (tidak ada batas internal) | MANUAL | — | N/A, hanya 1 fase |
| Ujung kanan blok terakhir | AUTO (Cool) / MANUAL (Running) | Drag | Perpanjang/perpendek durasi fase terakhir — **tidak berubah secara konsep**, cuma target fasenya beda |
| Tombol "×" / klik-kanan | AUTO / MANUAL | Klik | Hapus seluruh batch — **tidak berubah dari v1** |

**Catatan implementasi double-click vs mousedown-drag:** Browser tetap mengirim `mousedown`→`mouseup`→`mousedown`→`mouseup`→`dblclick` untuk sebuah double-click. Karena `onMouseDown` di badan blok saat ini langsung memulai mode "move" (v1 §5.3), setiap double-click akan **memicu 2× drag-move dengan jarak ~0px dulu** (harmless, hasil akhirnya batch tetap di posisi semula) sebelum `dblclick` akhirnya membuka modal. Ini **tidak berbahaya** tapi perlu 1 pengaman kecil: modal dibuka dari handler `onDoubleClick` terpisah yang memanggil `e.stopPropagation()` supaya tidak bentrok dengan `dragRef` yang masih aktif dari mousedown terakhir — `dragRef.current = null` harus di-reset saat modal dibuka.

---

## 7. Edge Cases Tambahan (v2)

| Kasus | Perilaku yang diharapkan |
|---|---|
| `ProgramMaster` dihapus admin setelah dipakai di suatu batch | FK `on_delete=SET_NULL` → `program` jadi `null` di batch tersebut, durasi yang sudah tersimpan **tidak berubah**, label "program" hilang dari tampilan (tidak error) |
| User pilih program di mesin yang ternyata `MANUAL` | Dropdown "Program target" **tidak ditampilkan sama sekali** untuk mesin MANUAL (bukan disembunyikan-tapi-ada, benar-benar tidak dirender) — mencegah kebingungan |
| Modal dibuka untuk batch yang sedang di-drag (race) | Double-click membatalkan drag yang sedang berjalan (`dragRef.current = null` sebelum modal dibuka) — state terakhir sebelum modal dibuka yang jadi nilai awal form |
| User ubah durasi di modal jadi overlap dengan batch lain | Tombol "Simpan" (di modal) disabled + pesan error inline, **beda dari drag** yang snap-back otomatis — di sini form harus dikoreksi manual dulu |
| Mesin pindah `operation_mode` (AUTO→MANUAL) di admin, padahal sudah ada batch AUTO lama tersimpan untuk mesin itu | Saat plan lama itu diedit lagi: backend akan menolak `PUT` kalau payload batch mesin itu masih berbentuk 3-block (karena mode sekarang MANUAL, validasi §3.4 menuntut 1-block RUNNING). **Rekomendasi revisi:** tampilkan **warning blocking** (modal/dialog, bukan toast) saat plan di-load dengan isi: *"Mode mesin [X] berubah dari AUTO → MANUAL sejak rencana ini dibuat. Batch lama [X] tidak bisa disimpan dalam format AUTO. Pilih salah satu: [Konversi ke 1 block RUNNING (total durasi lama)] / [Hapus batch ini] / [Lihat saja tanpa bisa disimpan]"*. Jangan auto-convert diam-diam karena ini **kehilangan informasi fase yang permanen** (Heat/Hold/Cool terpisah jadi 1 blok) tanpa persetujuan user. |

---

## 8. Ringkasan Perubahan File (v2)

**Backend**
- `monitoring/models.py` — `ProductionPlanBatch.program` (FK baru), `ProductionPlanBlock.PHASE_CHOICES` (+`RUNNING`)
- `monitoring/migrations/0071_planning_program_and_manual_phase.py` (baru)
- `monitoring/api_planning.py` — `_validate_batches_payload` bercabang AUTO/MANUAL, `_serialize_plan` sertakan `program_id`/`program_name` & `operation_mode`, `get_planning_meta` sertakan `operation_mode` & `programs`
- `monitoring/utils/steam_calc.py` — `compute_steam_timeline_from_plan_batches` bercabang set fase aktif per `operation_mode`
- `monitoring/admin.py` — tambahkan `program` ke `ProductionPlanBatchAdmin` readonly fields (untuk konsistensi tampilan admin)

**Frontend**
- `frontend/src/components/planning/PlanningBatchEditModal.jsx` (baru)
- `frontend/src/pages/ProductionPlanning.jsx` — wiring `onDoubleClick`, passing `operation_mode` & `programs` ke modal, reducer actions baru (`OPEN_EDIT_MODAL` state lokal cukup `useState`, bukan reducer plan; commit hasil modal lewat action existing `MOVE_BATCH`-like generic `UPDATE_BATCH`)
- `frontend/src/lib/planningGeometry.js` — `createRunningBlock`, `STEAM_ACTIVE_PHASES_BY_MODE`, update `computeSteamTimeline`
- `frontend/src/store/planningApi.js` — tidak berubah (kontrak endpoint sama, hanya payload/response field baru yang transparan lewat JSON)

---

## 9. Fase Implementasi v2

| Fase | Estimasi | Isi | Definisi selesai |
|---|---|---|---|
| **Q0** | ~1 hari | Migrasi backend: `program` FK + `RUNNING` phase choice (lihat §3.2–3.3); update `get_planning_meta` (`operation_mode`, `programs`); update `_serialize_plan` | `/api/planning/meta` mengembalikan `operation_mode` & `programs`; `/api/planning/plans/{id}` mengembalikan `program_id` |
| **Q1** | ~1 hari | Validasi backend bercabang AUTO/MANUAL di `_validate_batches_payload` (dengan `select_for_update`, lihat §3.4) + `steam_calc.py` bercabang | Test manual: kirim payload MANUAL 3-block → ditolak; kirim payload AUTO 1-block RUNNING → ditolak |
| **Q2** | ~1½ hari | Render papan bercabang: mesin MANUAL tampil sebagai blok 1-warna, handle resize disesuaikan, drag-create pakai `createRunningBlock` | Papan menampilkan mesin AUTO & MANUAL dengan visual berbeda sesuai §5.3 |
| **Q3** | ~2 hari | `PlanningBatchEditModal` — versi AUTO (3 durasi + program) & versi MANUAL (1 durasi), trigger double-click + reset `dragRef` (lihat §6 catatan) | Double-click batch AUTO/MANUAL membuka form yang sesuai, bisa ubah durasi & tersimpan lewat tombol Simpan global |
| **Q4** | ~½ hari | Auto-fill dari `ProgramMaster` saat pilih program di modal (§5.2) | Pilih program → 3 field durasi terisi otomatis, tetap bisa diedit manual |
| **Q5** | ~½ hari | Steam timeline client (`computeSteamTimeline`) bercabang per mode, konsisten dengan Q1 + **wajib: jalankan test sinkronisasi client vs server untuk skenario AUTO+MANUAL gabungan** (lihat §5.4) | Heatmap uap benar untuk kombinasi mesin AUTO+MANUAL; angka client == angka server untuk setiap mode |
| **Q6** | ~1 hari | Edge cases §7 (terutama warning blocking saat mode mesin berubah setelah plan dibuat) + polish (validasi inline modal, disabled state, label "jam mulai" format `HH:mm` §5.1) | Semua kasus di §7 teruji manual |

---

## 10. Yang Perlu Anda Evaluasi Sebelum Implementasi v2 Dimulai

1. **Auto-fill "selalu timpa" (§5.2)** — apakah oke field durasi selalu ditimpa saat pilih program baru (tanpa dialog konfirmasi), atau Anda mau ada konfirmasi kalau field sudah diisi manual sebelumnya?
2. **Jam mulai via time-input `HH:mm` vs "menit ke-X"** — mana yang lebih natural buat planner di form popup?
3. **Mesin MANUAL: benar-benar cuma 1 status (Running/on) tanpa "Standby"/status lain?** — dari investigasi, sistem manual existing (`ManualMachineUsage`, toggle cepat) memang hanya biner Running/Stop meskipun model `Machine` punya opsi status lebih granular (`Standby`, `Preset...` untuk `status_type` 3). Konfirmasi: Planning cukup ikuti pola biner ini (bukan granular), sesuai kata Anda "on off biasa aja"?
4. **`program` di `ProductionPlanBatch` disimpan sebagai snapshot-reference (§3.1)**, bukan live-link — apakah ini sudah sesuai ekspektasi, atau Anda maunya kalau `ProgramMaster` diubah, batch lama ikut ter-update juga (lebih rumit & berisiko "berubah diam-diam", tidak direkomendasikan)?
5. **Edge case mesin ganti mode AUTO↔MANUAL setelah plan dibuat (§7 baris terakhir)** — apakah skenario ini realistis terjadi di lapangan (cukup sering untuk layak ditangani khusus di Q6), atau bisa diabaikan (biarkan gagal-save dengan pesan error saja, tanpa auto-convert)?

Setelah dikonfirmasi, saya lanjut dari **Fase Q0**.

---

## 11. Riwayat Perubahan Dokumen

| Tanggal | Bagian | Perubahan |
|---|---|---|
| 2026-08-20 | §3.2 | ~~Tambah peringatan bug `PositiveIntegerField` menolak 0~~ — **dibatalkan**: Django `PositiveIntegerField` resmi mengizinkan 0 (non-negatif). Field tetap `PositiveIntegerField`; tidak perlu AlterField. |
| 2026-08-20 | §3.3 | ~~Tambah `AlterField duration_minutes`~~ — **dibatalkan** (lihat koreksi §3.2). Migrasi `0071` hanya: `program` FK + `RUNNING` choice. |
| 2026-08-20 | §3.4 | Tambah catatan **proteksi race condition `operation_mode`**: wajib pakai `select_for_update()` di dalam `transaction.atomic()` saat query machine untuk validasi — mencegah mode berubah di tengah request PUT. |
| 2026-08-20 | §5.1 (validasi modal) | Perbaiki inkonsistensi **minimum durasi: dari ≥ 15 menit (GRID_MINUTES) jadi ≥ 1 menit** — agar selaras dengan constraint server-side. Snap-to-grid 15 menit adalah perilaku drag, bukan batas minimum absolut untuk form. Tambahkan juga keputusan default sementara format input jam mulai: `HH:mm` (sambil menunggu konfirmasi §10 poin 2). |
| 2026-08-20 | §5.4 | Tambah catatan **wajib test guard sinkronisasi client vs server** untuk `STEAM_ACTIVE_PHASES_BY_MODE` mode MANUAL — tanpa checkpoint eksplisit ini, drift bisa lolos ke produksi diam-diam. Cross-referenced ke definisi selesai Q5 di §9. |
| 2026-08-20 | §7 (edge case terakhir) | Ubah rekomendasi mode mesin berubah dari **"warning non-blocking + auto-convert"** jadi **"warning blocking dengan pilihan eksplisit user"** — auto-convert diam-diam menyebabkan hilangnya informasi fase (Heat/Hold/Cool → 1 blok Running) tanpa persetujuan. |
| 2026-08-20 | §9 (roadmap) | Tambah kolom **estimasi durasi** per fase (Q0–Q6). Total estimasi ~6½ hari kerja. Cross-reference `select_for_update` ke Q1, test sync ke Q5, warning blocking ke Q6. |
