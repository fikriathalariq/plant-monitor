# Implementation Plan v3 — Fix Durasi Import + Cross-Day Batch

> Status: **DRAFT untuk evaluasi** (revisi dari `PLANNING_FIX_IMPORT_DURATION_AND_CROSSDAY.md`)
> Tanggal: 21 Agustus 2026
> Dasar: hasil audit ulang terhadap kode aktual di repo (bukan asumsi), lihat §0.

---

## §0. Ringkasan Perubahan dari Dokumen Draft Sebelumnya

Saya membaca ulang `import_dyeing_to_plan.py`, `batch_analyzer.py`, `process_batch_history.py`,
`api_report.py`, `api_batch_detail.py`, `views.py`, `api_planning.py`, `planningGeometry.js`, dan
`ProductionPlanning.jsx` untuk memverifikasi klaim di dokumen draft. Dua temuan penting:

1. **Klaim HEAT (✅ benar & terverifikasi di kode):**
   `real_heating_duration` memang dihitung sebagai `steady_start_time − heating_start_time`
   (lihat `process_batch_history.py:238-241`), dan **setiap** tempat report/analytics di kode
   (`api_report.py:913`, `api_batch_detail.py:98-99`, `views.py:1698`) memakai
   `real_heating_duration` untuk "heat_actual"/"heating_duration" — **bukan** `heating_duration`
   (yang cuma cacah menit dengan `thermal_state == 'HEAT'`, lihat `process_batch_history.py:270`).
   Fix HEAT di dokumen draft **valid, lanjutkan tanpa perubahan.**

2. **Klaim COOL (⚠️ tidak didukung kode saat ini — perlu klarifikasi sebelum eksekusi):**
   Dokumen draft mengklaim report memakai `cooling_start_time → end_time`, tapi di kode:
   - `api_report.py:915` → `cool_dur = process.cooling_duration or 0`
   - `api_batch_detail.py:140` → `"actual_cooling": process.cooling_duration`
   - `views.py:1916` (chart phase %) → `cool_dur = process.cooling_duration or 0`

   **Semua** tempat yang menampilkan angka COOL di report memakai field yang **sama persis**
   dengan yang sudah dipakai importer sekarang (`cooling_duration`). Jadi secara kode, tidak ada
   sumber selisih HEAT vs COOL yang simetris — kalau report benar-benar menunjukkan 127 menit
   sedangkan `cooling_duration` di DB untuk proses itu adalah 65 menit, maka salah satu dari ini
   yang terjadi:
   - (a) angka "127" di investigasi didapat dengan menghitung manual dari raw sensor log
     (`cooling_start_time` → `end_time`), bukan dari tampilan report yang sebenarnya — dan
     tampilan report yang sekarang **sebenarnya juga menunjukkan 65**, bukan 127; **atau**
   - (b) ada halaman/komponen report lain yang belum saya temukan yang menghitung ulang cooling
     dari timestamp mentah.

   **Rekomendasi:** jangan eksekusi fix COOL dulu sebelum ini dikonfirmasi. Cukup buka
   `/history/report/3025184` (atau route setara di SPA) sekali lagi dan **screenshot angka COOL
   yang tampil**, lalu bandingkan dengan nilai kolom `cooling_duration` di DB untuk proses yang
   sama. Kalau angkanya sama-sama 65 (bukan 127), maka **field COOL tidak perlu diubah** —
   cukup fix HEAT saja, dan importer otomatis jadi 100% konsisten dengan report. Ini juga
   membuat scope fix jadi lebih kecil dan lebih aman. Saya tidak bisa menjalankan Django shell
   di environment ini untuk mengecek nilai DB langsung (Python tidak tersedia di sandbox saat
   ini), jadi ini butuh verifikasi manual dari kamu — lihat §7 Pertanyaan Konfirmasi Q1.

3. **Cross-day (§ Bagian II) — scope-nya jauh lebih besar dari yang digambarkan di draft.**
   Draft hanya menyinggung "renderer perlu menangani overflow" dengan pseudo-code generik.
   Setelah membaca kode board yang sudah jalan (`ProductionPlanning.jsx`, `planningGeometry.js`,
   `api_planning.py`), ternyata **batas 1440 menit di-hardcode di banyak tempat**, termasuk
   **validasi backend yang secara aktif menolak overflow** (bukan cuma soal render frontend).
   Detail lengkap di §3.

---

## Bagian I — Fix Durasi Import (HEAT wajib, COOL kondisional)

### I.1 File: `monitoring/management/commands/import_dyeing_to_plan.py`

**Baris 86-88 saat ini:**
```python
heat = max(0, round(proc.heating_duration or 0))
steady = max(0, round(proc.steady_duration or 0))
cool = max(0, round(proc.cooling_duration or 0))
```

**Setelah fix (HEAT only, opsi COOL menyusul §7-Q1):**
```python
# HEAT: pakai real_heating_duration (rise time aktual), sama seperti yang
# ditampilkan di report (api_report.py, api_batch_detail.py, views.py).
heat = max(0, round(proc.real_heating_duration or 0))
steady = max(0, round(proc.steady_duration or 0))
# COOL: TETAP cooling_duration untuk saat ini — field ini SUDAH sama dengan
# yang dipakai report (lihat §0.2). Jangan ubah sampai Q1 di §7 dikonfirmasi.
cool = max(0, round(proc.cooling_duration or 0))
```

Kalau setelah verifikasi manual (Q1) ternyata report memang menunjukkan angka yang berbeda dari
`cooling_duration`, gunakan varian ini sebagai gantinya:
```python
if proc.cooling_start_time and proc.end_time:
    cool = max(0, round((proc.end_time - proc.cooling_start_time).total_seconds() / 60))
else:
    cool = max(0, round(proc.cooling_duration or 0))
```

### I.2 Guard tambahan yang belum ada di command saat ini

Command saat ini **tidak** memvalidasi `machine.operation_mode` — semua batch diimport dengan 3
blok `HEAT/STEADY/COOL`, walau `Machine.operation_mode == 'MANUAL'`. Ini perlu diselaraskan
dengan model AUTO/MANUAL yang sudah dibangun di v2, karena `_validate_batches_payload` di
`api_planning.py` mewajibkan struktur blok sesuai `operation_mode` (baris 103-113: mesin MANUAL
**wajib tepat 1 fase RUNNING**) — tapi **command ini menulis langsung ke DB lewat ORM, tidak
lewat endpoint API, jadi validasi itu tidak berlaku saat import**.

> ❌ **Koreksi balik (re-verifikasi sesi ini):** Update sebelumnya di dokumen ini mengklaim
> `detectModeMismatches` "tidak ada di kode sama sekali" — ini **salah**, kemungkinan grep-nya
> keliru (tidak scoped ke folder `frontend/src`, atau kena timeout). Grep ulang dengan scope yang
> benar menemukan fungsi ini persis di dua tempat:
> - **Didefinisikan** di `frontend/src/lib/planningGeometry.js:199-230`.
> - **Dipakai** di `frontend/src/pages/ProductionPlanning.jsx`: diimport (baris 27), dipanggil
>   lewat `refreshModeIssues()` (baris 401-407) yang langsung dieksekusi setiap kali plan
>   dimuat — baik saat pertama buka tanggal (`loadPlanForDate`, baris 424) maupun saat pindah
>   draft lewat dropdown (baris 816).
>
> Jadi klaim **awal** (sebelum revisi keliru ini) sudah benar dan berlaku, malah lebih parah dari
> yang disebutkan: begitu plan hasil import (mesin MANUAL dengan 3 fase HEAT/STEADY/COOL) dibuka
> di board, `modeIssues` langsung terisi dan:
> - Banner peringatan kuning langsung muncul (baris 863-910) meminta user "Konversi" atau "Hapus
>   batch" untuk tiap batch yang mismatch — **bukan cuma gagal pas klik Simpan**.
> - Tombol **Simpan** dan **Publish** langsung ter-disable (`disabled={... || modeIssues.length > 0}`,
>   baris 839 & 842) sampai semua mismatch diselesaikan manual satu per satu lewat banner itu.
>
> Artinya kalau §I.2 (cabang MANUAL di command import) **tidak** diimplementasikan, setiap plan
> hasil `import_dyeing_to_plan.py` yang punya mesin MANUAL akan langsung muncul sebagai board penuh
> peringatan yang harus dibersihkan manual satu-satu — bukan cuma soal gagal simpan belakangan.
> Ini memperkuat, bukan melemahkan, urgensi §I.2.


**Tambahan yang perlu masuk ke command:**
```python
if proc.machine.operation_mode == "MANUAL":
    total = max(0, round(proc.duration_effective or (heat + steady + cool)))
    blocks = [ProductionPlanBlock(batch=batch, phase='RUNNING', sequence=0, duration_minutes=total)]
else:
    blocks = [
        ProductionPlanBlock(batch=batch, phase='HEAT', sequence=0, duration_minutes=heat),
        ProductionPlanBlock(batch=batch, phase='STEADY', sequence=1, duration_minutes=steady),
        ProductionPlanBlock(batch=batch, phase='COOL', sequence=2, duration_minutes=cool),
    ]
```
(exact source field for MANUAL "on" duration perlu dicek — kemungkinan `duration_effective`
atau `(end_time - start_time)`; lihat §7-Q4.)

### I.3 Re-import

Sama seperti draft — hapus & re-import range yang diinginkan setelah fix di atas:
```bash
python manage.py import_dyeing_to_plan --date-from 2026-08-11 --date-to 2026-08-20 --overwrite --dry-run
python manage.py import_dyeing_to_plan --date-from 2026-08-11 --date-to 2026-08-20 --overwrite
```
Jalankan `--dry-run` dulu dan cek beberapa baris `--verbose` secara manual sebelum commit ke DB
sungguhan (lihat §7-Q3 soal timing re-import vs fix cross-day).

---

## Bagian II — Analisis Dampak Cross-Day (Batch Tidak Dipotong)

### II.1 Model & Migrasi — **tidak ada perubahan** ✅

`start_offset_minutes` tetap `PositiveIntegerField` 0–1439 (waktu mulai di hari itu), dan
`duration_minutes` blok tidak dibatasi 1440 di level model. Tidak perlu migrasi baru — sesuai
draft.

### II.2 Command import — hapus clamping (sesuai draft, §II.1-II.2 draft asli)

Baris 122-129 (`clamp_note`, pengurangan `cool`/`steady` saat overflow) **dihapus total**. Ganti
skip guard `total > MAX_BATCH_MINUTES` (baris 91-95) dengan pengecekan yang sama tapi TANPA
clamping — batch overflow "wajar" (mis. mulai 23:00, total 8 jam) tetap disimpan penuh; hanya
batch anomali (>1440 menit total) yang di-skip. Ini sudah persis seperti draft asli — tidak ada
revisi di titik ini.

### II.3 Backend API (`monitoring/api_planning.py`) — **bagian yang TIDAK disebut draft, tapi WAJIB diubah**

`_validate_batches_payload` baris 119-124 **secara aktif menolak** payload apa pun (baik dari
import maupun dari drag board) yang `start_offset_minutes + total > TOTAL_BUCKETS (1440)`:
```python
if batch.start_offset_minutes + total > TOTAL_BUCKETS:
    raise HttpError(400, f"Batch melewati batas shift 24 jam: ...")
```
Kalau ini tidak diubah, batch yang diimport oleh command (langsung ORM, bypass API) akan tersimpan
dengan overflow, tapi begitu user membuka plan itu di board dan menekan **Simpan** (yang memanggil
endpoint `PUT /planning/{id}` → `_validate_batches_payload`), request akan **selalu ditolak 400**
karena batch overflow itu ikut dikirim ulang dalam payload. Plan jadi "read-only" secara de facto.

**Perubahan wajib:**
```python
MAX_BATCH_MINUTES = TOTAL_BUCKETS  # batch tunggal tidak boleh > 24 jam (anomali)

# ganti baris 119-124:
if total > MAX_BATCH_MINUTES:
    raise HttpError(
        400,
        f"Durasi batch {batch.machine_code} melebihi 24 jam ({total} menit) — kemungkinan data anomali",
    )
# start_offset_minutes + total BOLEH > TOTAL_BUCKETS (meluber ke hari berikutnya)
```

**Overlap detection (baris 130-136) juga perlu direview:** logikanya sudah generik (interval
`[start, start+total)` per mesin, sort lalu cek `curr_start < prev_end`) — ini **sudah otomatis
benar** untuk kasus overflow karena `end` bisa > 1440 tanpa masalah, selama tidak ada asumsi lain
yang membatasi. Tidak perlu ubah bagian ini. ✅

**Konsekuensi query lain — sudah dicek, aman:** `_serialize_plan` (baris 139-178) menghitung
`start_pct`/`width_pct` pakai `minutes_to_pct(minutes, total=TOTAL_BUCKETS) → round(minutes/total*100, 4)`
(`shift_time.py:44-45`) — **tidak ada clamp ke 100%**, jadi `width_pct` untuk blok yang overflow
akan otomatis > 100% tanpa perubahan kode di fungsi ini. ✅ Tidak perlu disentuh.

### II.4 Steam heatmap cross-plan — gap arsitektur (revisi analisis, ternyata TIDAK perlu ubah kode kalkulasi)

**Revisi (sesi implementasi):** analisis awal saya soal "array plan A terpotong di menit 1440"
**keliru** setelah ditelusuri ulang baris demi baris. `compute_steam_timeline_from_plan_batches`
(`steam_calc.py:20-56`) dan versi JS-nya `computeSteamTimeline` (`planningGeometry.js:81-113`)
memang punya `total_minutes = 1440` (array cuma 1440 sel) — tapi array ini **memang cuma
merepresentasikan window plan A sendiri (jam 06:00 A → 06:00 A+1)**, jadi tidak ada "pemotongan
data" untuk plan A: kontribusi steam batch overflow selama menit 0–1439 **sudah lengkap dihitung**
(loop `for t in range(start, end)` dengan `end = min(cursor+dur, total_minutes)`), dan bagian yang
"tidak ikut dihitung" (menit ≥1440) memang secara konseptual **bukan** milik plan A — itu adalah
jam 00:00–sekian di plan **B** (hari berikutnya), bukan bagian dari heatmap hari A. Jadi **tidak
ada bug/pemotongan untuk plan A sendiri, dan tidak perlu ubah `steam_calc.py` atau
`computeSteamTimeline` sama sekali.**

Gap yang **sungguhan** cuma satu: **plan B tidak tahu ada mesin yang masih menyala dari sisa
batch overflow plan A** di jam-jam awal shift-nya (00:00–06:00 versi kalender, atau menit
0-sekian versi offset shift B). Ini murni gap Opsi 2 (join antar `ProductionPlan` per tanggal) —
**di luar scope v3 ini** (didokumentasikan sebagai limitation, sama seperti keputusan awal),
karena effort-nya besar (query cross-plan, cross date) untuk kasus yang jarang terjadi (biasanya
cuma beberapa jam saja yang overflow). Indikator overflow di §3 (badge `▶` + tooltip pada batch
block plan A) sudah cukup memberi sinyal visual ke user bahwa proses itu masih berlanjut, tanpa
perlu mengubah kalkulasi heatmap plan B.

**Kesimpulan: F3 di §4 dihapus dari rencana kerja** (tidak ada perubahan kode di
`steam_calc.py` / `computeSteamTimeline`) — hanya limitation plan B yang didokumentasikan di §5.

### II.5 Frontend — titik-titik hardcode 1440 yang harus diubah (lebih detail dari draft)

Draft cuma menyebut "renderer perlu overflow logic" secara umum. Berikut titik-titik konkret di
`ProductionPlanning.jsx` dan `planningGeometry.js` yang **harus** disentuh:

| # | Lokasi | Masalah saat ini | Perubahan |
|---|---|---|---|
| 1 | `planningGeometry.js: hasOverlap()` | `bEnd = b.startOffsetMinutes + batchTotalDuration(b)` — sudah generik, aman untuk overflow (`bEnd` boleh >1440). | Tidak perlu ubah. ✅ |
| 2 | `onMove` drag `move` (`ProductionPlanning.jsx:544-546`) | `next = clamp(next, 0, SHIFT_MINUTES - drag.duration)` — **secara aktif mencegah** user drag batch ke posisi yang bikin overflow. | Ganti clamp jadi `clamp(next, 0, SHIFT_MINUTES - 1)` (batch boleh overflow, hanya titik start yang dibatasi 0–1439, sesuai model). |
| 3 | `onMove` drag `resize-end` (`:580-586`) | **Revisi (sesi implementasi):** ternyata **tidak perlu diubah**. `minutes` yang dipakai untuk `end` selalu berasal dari posisi mouse relatif track lewat `pctFromTrack()`, yang di-clamp `[0, 100]%` — jadi `end` tidak akan pernah > `SHIFT_MINUTES` terlepas dari nilai upper-bound di `clamp(...)`. Resize lewat mouse-drag secara fisik memang tidak bisa membuat batch overflow (mouse tidak bisa "keluar" dari track 1-hari); overflow hanya bisa dibuat lewat modal edit (input angka manual, lihat #5) atau lewat `move` (#2). | Tidak ada perubahan kode. |
| 4 | Drag `create` (`onUp`, `:601-607`) | `end = Math.min(end, SHIFT_MINUTES)` — batch baru yang dibuat lewat drag **tidak bisa** dibuat overflow lewat cara ini (wajar, drag create dibatasi lebar track visual, hanya relevan untuk resize/move batch yang sudah ada atau via edit modal). | Biarkan seperti ini untuk drag-create (create tetap dalam 1 hari); overflow baru muncul lewat resize-end atau lewat modal edit (lihat #5). |
| 5 | `PlanningBatchEditModal.jsx: validate()` (`:77-79` lama) | **Konfirmasi:** memang ada blocking check `if (start + total > SHIFT_MINUTES) return 'Melewati batas shift...'` — ini satu-satunya jalur nyata untuk membuat batch overflow (lewat input angka manual), dan sebelumnya diblokir. | **Selesai.** Diganti jadi guard anomali `total > SHIFT_MINUTES` (24 jam), plus badge info "berlanjut Xm ke hari berikutnya" saat overflow terdeteksi. |
| 6 | `PlanningBatchBlock` render (`:212-215`) | `width = minutesToPct(total)` dihitung dari total durasi asli (tidak clamp) — **sudah otomatis lebar > 100%-left** untuk batch overflow. Masalahnya bukan di kalkulasi lebar, tapi **parent `<td data-chart-track>` tidak punya `overflow-hidden`**, jadi elemen absolute akan bleeding keluar row lalu ditangkap oleh `overflow-auto` di container terluar (`:916`) → user bisa scroll horizontal tak terduga, bukan "dipotong rapi di tepi" seperti Opsi A draft. | Tambah `overflow-hidden` pada `<td data-chart-track>` (`:313-317`) supaya batch overflow ter-clip rapi di tepi kanan track 1440-menit. Tambah elemen indikator `▶`/arrow terpisah (absolute, `right-0`, di atas track, z-index tinggi) yang muncul kalau `batchEndOffset > SHIFT_MINUTES`. |
| 7 | Tooltip (`title={batch.label...}` `:225`) | Statis, tidak menunjukkan durasi total / overflow. | Tambahkan info: `"${label} · total ${total}m · lanjut ${overflow}m ke hari berikutnya"` saat overflow. |
| 8 | `computeSteamTimeline` (`planningGeometry.js:81-113`) | `values = new Array(SHIFT_MINUTES).fill(0)`, loop `for t = start; t < end; t++` dengan `end = Math.min(cursor+dur, SHIFT_MINUTES)` — otomatis memotong kontribusi steam pas di menit 1440 (match backend `steam_calc.py`, konsisten client/server, tapi berarti keduanya perlu diperluas bareng kalau pilih Opsi 1 di §II.4). | Perluas panjang array sesuai keputusan §II.4 (misal jadi dinamis `SHIFT_MINUTES + maxOverflow` atau flat 2×). **Backend & frontend harus diubah bersamaan** supaya tetap konsisten (prinsip yang sudah dipegang sejak v1/v2). |

### II.6 Ringkasan File yang Berubah (v3, akurat per kode saat ini)

| File | Perubahan |
|---|---|
| `monitoring/management/commands/import_dyeing_to_plan.py` | HEAT: `heating_duration`→`real_heating_duration`; COOL: kondisional (§7-Q1); hapus blok clamping baris 122-129; tambah cabang MANUAL (blok `RUNNING` tunggal, §I.2) |
| `monitoring/api_planning.py` | `_validate_batches_payload`: hapus penolakan `start_offset + total > TOTAL_BUCKETS`, ganti dengan guard "total tunggal ≤ 1440" (anomali), overlap logic tetap |
| `frontend/src/pages/ProductionPlanning.jsx` | Poin #2, #3, #6, #7 di tabel §II.5: clamp drag move/resize-end, `overflow-hidden` + indikator arrow di track, tooltip overflow |
| `frontend/src/components/planning/PlanningBatchEditModal.jsx` | Audit & pastikan tidak ada clamp durasi tersembunyi yang mencegah overflow (§II.5 poin #5) |

---

## §3. Opsi UI Cross-Day — dikonfirmasi Opsi A (sesuai draft), detail render

Setuju dengan rekomendasi draft: **Opsi A** (batch di-clip di tepi kanan + indikator `▶`), bukan
Opsi B (canvas diperlebar). Alasan tambahan dari sisi kode: mengubah lebar canvas berarti mengubah
semua kalkulasi `pctFromTrack`, `minutesToPct`, `TimeGrid`, `TimeAxis` yang saat ini semuanya
berasumsi 1 track = 1 hari = 100% lebar — effort jauh lebih besar untuk value yang marginal
(kasus overflow "wajar" biasanya cuma beberapa jam, cukup diwakili indikator kecil).

Implementasi konkret Opsi A (menggantikan pseudo-code generik di draft dengan kode nyata):

```jsx
// PlanningBatchBlock — tambahan setelah menghitung `total`
const endOffset = batch.startOffsetMinutes + total;
const isOverflow = endOffset > SHIFT_MINUTES; // SHIFT_MINUTES = 1440
const overflowMinutes = isOverflow ? endOffset - SHIFT_MINUTES : 0;
// width tetap dihitung dari total asli (tidak dipotong) — pemotongan visual
// terjadi otomatis lewat `overflow-hidden` di parent <td data-chart-track>.
```
```jsx
// <td data-chart-track ...> tambah className overflow-hidden (poin #6 §II.5)
<td
  data-chart-track
  className="relative h-7 sm:h-6 p-0 w-full min-w-0 bg-slate-100 border-b border-gray-100 cursor-crosshair select-none overflow-hidden"
  ...
>
```
```jsx
// Indikator overflow — elemen terpisah, di dalam batch block, absolute right-0
{isOverflow && (
  <div
    className="absolute right-0 top-0 bottom-0 w-3 flex items-center justify-center bg-black/25 z-20 pointer-events-none"
    title={`Berlanjut ${overflowMinutes}m ke hari berikutnya (selesai ${offsetToClockLabel(endOffset % SHIFT_MINUTES)} besok)`}
  >
    <span className="text-white text-[9px]">▶</span>
  </div>
)}
```

---

## §4. Fase Implementasi (Revisi Estimasi)

| Fase | Estimasi | Isi | Definisi Selesai |
|---|---|---|---|
| **F0 — Verifikasi klaim COOL** | ~10 menit | Buka report utk 1-2 batch, bandingkan angka COOL tampilan vs `cooling_duration` DB | Q1 §7 terjawab, scope Bagian I final |
| **F1 — Fix script durasi** | ~30 menit | Update `import_dyeing_to_plan.py`: HEAT wajib, COOL sesuai F0, hapus clamping, tambah cabang MANUAL, `--dry-run` | Dry-run heat ID=3025184 ≈ 212 menit |
| **F2 — Backend validasi cross-day** | ~20 menit | `api_planning.py`: ganti guard 1440 jadi guard anomali per-batch (`minutes_to_pct` sudah aman, tidak perlu diubah) | Save plan dengan batch overflow lewat API tidak lagi 400 |
| ~~F3 — Steam cross-plan~~ | — | **Dihapus** — analisis ulang menunjukkan `steam_calc.py`/`computeSteamTimeline` sudah benar untuk window plan-nya sendiri, tidak perlu diubah (lihat §II.4 revisi) | — |
| **F4 — Re-import data** | ~10 menit | `--overwrite` | Batch terimport ulang dengan durasi benar, termasuk yang overflow (tidak clamp) |
| **F5 — Verifikasi durasi** | ~15 menit | Bandingkan manual 5 batch: plan vs report | Match |
| **F6 — Frontend cross-day** | ~1.5–2 jam | Poin §II.5 #2,3,6,7; audit modal §II.5 #5 | Batch malam→dini hari tampil utuh sampai tepi + indikator `▶`, drag/resize tidak lagi dibatasi ke 1440, tooltip informatif |
| **F7 — Regresi** | ~20 menit | Cek: batch normal (non-overflow) masih pas, overlap detection masih benar, publish/duplicate masih jalan | Tidak ada regresi pada plan yang sudah ada |

**Total estimasi: ~3.5–4.5 jam** (naik dari estimasi draft 2-3 jam karena scope backend
validasi + steam cross-plan yang draft belum cover).

---

## §5. Hal yang Sengaja TIDAK Diubah / Di Luar Scope

- **Opsi 2 di §II.4** (steam plan B ikut menghitung overflow dari plan A) — didokumentasikan
  sebagai limitation, bisa jadi iterasi selanjutnya jika dibutuhkan.
- **Drag-create tetap dibatasi 1 hari** — overflow hanya bisa terjadi lewat resize-end atau modal
  edit pada batch yang sudah ada dengan start_offset besar (misal drag-create dulu jam 22:00,
  lalu resize ujung kanan sampai melewati 06:00 besok).
- **Skip guard anomali >1440 menit** tetap ada di command import (batch >24 jam dianggap data
  rusak, bukan overflow wajar) — sama seperti draft.

---

## §8. Bug Ditemukan Setelah F6 "Selesai" — Indikator Overflow Tidak Pernah Terlihat

**Laporan user:** setelah F1/F2/F6 diimplementasikan dan dry-run sukses, batch `#1881
[DIPOTONG]` (label lama, dari sebelum fix) diedit manual lewat modal untuk membuat overflow,
tapi board tetap terlihat "terpotong" — tidak ada indikator `▶` yang muncul.

### Root Cause

Indikator overflow (`▶`) yang ditambahkan di F6 di-nest **di dalam** `<div data-batch-block>`
(container batch itu sendiri) dengan `className` termasuk `right-0` — posisinya relatif terhadap
div batch itu. Tapi div batch ini **sendiri** yang lebarnya (`width: {minutesToPct(total)}%`)
melebihi 100% saat overflow (mis. total 2000 menit di track 1440 menit → `width: 138.8%`). Jadi
sisi kanan div batch (tempat arrow diposisikan `right:0`) berada **jauh di luar area 100%** track
— dan karena `<td data-chart-track>` (parent) punya `overflow-hidden`, bagian itu (termasuk
arrow-nya) **ikut ter-clip dan tidak pernah dirender ke layar**. Yang terlihat oleh user cuma
batch yang berhenti tepat di tepi hari, identik dengan "dipotong" — walau data & lebar batch
sebenarnya sudah benar (tidak dipotong), cuma indikatornya yang tidak pernah nongol.

Analogi sederhana: menaruh tanda "lanjut baca di halaman 2" di baris terakhir halaman 3 dari
sebuah dokumen 3-halaman yang di-print cuma sampai halaman 1 — tandanya ada di kertas, tapi tidak
pernah ikut ter-print.

### Fix

Indikator overflow dipindah jadi **sibling langsung** dari batch-batch di dalam `<td
data-chart-track>` (bukan nested di dalam div batch), dengan posisi `right-0` relatif terhadap
**track**, bukan relatif terhadap div batch yang overflow. Karena track selalu tepat 100% = 1
hari (tidak ikut melebar), `right:0` di situ selalu berarti "ujung hari", persis yang dibutuhkan.

```jsx
// MachineRow — dihitung dari daftar batch di baris ini, BUKAN di dalam PlanningBatchBlock
const hasOverflowingBatch = (batches || []).some(
  (b) => b.startOffsetMinutes + batchTotalDuration(b) > SHIFT_MINUTES,
);
// ...
<td data-chart-track className="... overflow-hidden" ...>
  {batches.map((batch) => <PlanningBatchBlock ... />)}
  {hasOverflowingBatch && (
    <div className="absolute right-0 top-0 bottom-0 w-3 flex items-center justify-center bg-black/35 z-30 pointer-events-none">
      <span className="text-white text-[9px] leading-none">▶</span>
    </div>
  )}
</td>
```

`PlanningBatchBlock` sendiri tetap menghitung `isOverflow`/`overflowMinutes` **hanya untuk teks
tooltip (`title`)** — itu tidak kena masalah clipping karena `title` adalah atribut HTML biasa
(bukan elemen visual yang bisa ter-clip CSS).

**Status: sudah diperbaiki** di `frontend/src/pages/ProductionPlanning.jsx` (fungsi
`MachineRow` & `PlanningBatchBlock`).

### ⚠️ Kemungkinan Sebab Kedua yang Masih Perlu Dicek: Data Belum Di-reimport Sungguhan

Label `Batch #1881 [DIPOTONG]` yang disebut user **hanya diproduksi oleh command versi LAMA**
(sebelum fix F1) — command versi baru **tidak lagi** menambahkan suffix `[DIPOTONG]` apa pun
(clamping sudah dihapus total). Kalau label ini masih muncul di board, berarti batch ini **belum
diganti oleh re-import yang sesungguhnya** — kemungkinan besar baru `--dry-run` yang dijalankan
(yang tidak menulis apa pun ke DB), belum `--overwrite` tanpa `--dry-run`.

Kalau memang begitu, setelah menjalankan bug-fix arrow di atas, batch `#1881` yang lama (data
asli, sudah pernah di-clamp oleh command lama saat pertama diimport) **kemungkinan memang benar-
benar tidak overflow lagi** (durasinya sudah dipotong permanen saat itu) — jadi tidak akan
menunjukkan arrow apa pun sampai batch ini diganti lewat re-import sungguhan. Ini bukan bug,
tapi konsekuensi dari command lama yang sudah menulis data terpotong ke DB sebelum kita fix.

**Tindakan:** jalankan (bukan dry-run):
```bash
python manage.py import_dyeing_to_plan --date-from <tanggal_plan_#1881> --date-to <tanggal_plan_#1881> --overwrite --verbose
```
lalu reload board dan cek lagi apakah batch itu (sekarang datanya fresh dari command baru) memang
overflow atau tidak — dan kalau overflow, apakah arrow `▶` sekarang muncul di tepi kanan track.

---

## §9. Bug Baru: Mesin MANUAL (SPP 2, SSD 2, dst.) Tidak Terplot di Board Walau "Tersimpan"

**Laporan user:** setelah re-import sungguhan (bukan dry-run) untuk plan `#19 Aktual
2026-08-20 (Import)`, mesin **AUTO** (JD 1, JD 3, JD 4, JD 6) tampil benar dengan
Heat/Hold/Cool. Tapi mesin **MANUAL** (SPP 2, SSD 2, grup "Continuous Gedung Processing")
tampil **kosong sama sekali** — tidak ada blok apa pun — walau menurut user datanya "tersimpan".

### Root Cause: Ada DUA command import yang terpisah, dan yang untuk MANUAL belum pernah dijalankan

Ternyata di repo **sudah ada** command terpisah khusus untuk mesin MANUAL:
`monitoring/management/commands/import_manual_to_plan.py` — sudah ada **sebelum** sesi ini,
tidak saya buat. Command ini punya sumber data yang sama sekali berbeda dari
`import_dyeing_to_plan.py`:

| | `import_dyeing_to_plan.py` (AUTO) | `import_manual_to_plan.py` (MANUAL) |
|---|---|---|
| Sumber data | `DyeingProcess` (hasil analisis thermal HEAT/STEADY/COOL dari `process_batch_history.py`) | `MachineManualLog` (log status Running/Stop mentah per mesin) |
| Cara deteksi durasi | `real_heating_duration`, `steady_duration`, `cooling_duration` | Rekonstruksi sesi ON/OFF dari log status berurutan (`reconstruct_sessions`) |
| Cross-day | Batch tunggal, boleh meluber (setelah fix F1/F2/F6 sesi ini) | **Sudah** menangani multi-hari dengan cara **memecah** sesi ON yang panjang jadi 1 batch per shift-day di titik 06:00 (`split_session_to_shifts`) — desain lain, bukan overflow, tapi sudah benar untuk kasusnya (sesi ON bisa berhari-hari) |

Mesin `SPP 2`/`SSD 2` (continuous processing, bukan siklus dyeing bertahap) **tidak punya baris
`DyeingProcess`** yang berarti (proses deteksi HEAT/STEADY/COOL dari `batch_analyzer.py` tidak
relevan untuk mesin yang tidak punya siklus suhu) — jadi `import_dyeing_to_plan.py` yang sudah
dijalankan **memang benar tidak menghasilkan apa pun** untuk mesin-mesin ini (bukan bug). Data
yang benar untuk mesin ini ada di `MachineManualLog`, dan itu **hanya bisa diimpor lewat**
`import_manual_to_plan.py` — yang sampai sekarang **belum pernah dijalankan** di sesi kita.

**Soal "datanya tersimpan":** kemungkinan besar yang dimaksud user adalah plan/batch AUTO
(JD 1/3/4/6) yang memang berhasil tersimpan dan terlihat — bukan berarti data MANUAL juga sudah
tersimpan. Baris SPP 2/SSD 2 memang masih benar-benar kosong di DB.

### ⚠️ Efek Samping Berbahaya yang Perlu Diwaspadai: Urutan Eksekusi

`import_dyeing_to_plan.py --overwrite` **menghapus seluruh `ProductionPlan`** (`plans_to_delete.delete()`,
cascade ke SEMUA batch termasuk yang MANUAL) lalu membuat ulang plan itu dari nol. Sedangkan
`import_manual_to_plan.py --overwrite` **hanya menghapus batch bermesin MANUAL** di plan itu
(tidak menyentuh plan/batch AUTO). Artinya:

- **Urutan yang benar:** jalankan `import_dyeing_to_plan.py --overwrite` **dulu**, baru
  `import_manual_to_plan.py --overwrite` **setelahnya**.
- **Kalau kebalik / dyeing dijalankan lagi setelah manual:** semua batch MANUAL yang sudah
  diimpor sebelumnya akan **ikut terhapus** (karena plan-nya di-delete-recreate oleh command
  dyeing) dan harus di-*re-run* `import_manual_to_plan.py` lagi setelahnya.

### Rencana Tindakan

1. **Jalankan command MANUAL yang sudah ada** (tidak perlu kode baru untuk command ini):
   ```bash
   python manage.py import_manual_to_plan --date-from 2026-08-11 --date-to 2026-08-20 --dry-run --verbose
   # cek output, lalu:
   python manage.py import_manual_to_plan --date-from 2026-08-11 --date-to 2026-08-20 --overwrite --verbose
   ```
2. **Reload board** di `/production-planning` untuk tanggal 20/08 — baris SPP 2/SSD 2 seharusnya
   sekarang muncul blok hijau "ON" (RUNNING).
3. **Aturan baku ke depan:** setiap kali re-import ulang, jalankan **kedua** command secara
   berurutan (dyeing dulu, manual belakangan):
   ```bash
   python manage.py import_dyeing_to_plan  --date-from <A> --date-to <B> --overwrite --verbose
   python manage.py import_manual_to_plan  --date-from <A> --date-to <B> --overwrite --verbose
   ```
4. **Fix defensif kecil di kode (dilakukan sesi ini):** `import_dyeing_to_plan.py` sekarang
   secara eksplisit **mengecualikan mesin `operation_mode='MANUAL'`** dari query `DyeingProcess`-nya
   (bukan cuma "kebetulan tidak ada data"), dan cabang MANUAL yang saya tambahkan di §I.2
   (pakai `duration_effective`) **dihapus** — ternyata itu keliru/berlebihan karena jalur resmi
   untuk MANUAL sudah ada (`import_manual_to_plan.py`), dan membiarkan dua command menyentuh
   mesin yang sama berisiko menghasilkan batch ganda/konflik overlap kalau suatu saat memang ada
   baris `DyeingProcess` nyasar untuk mesin MANUAL. §I.2 dan §7-Q5 (field durasi MANUAL) dengan
   ini **tidak relevan lagi** — command yang benar untuk MANUAL sudah lama ada dan tidak perlu
   diubah.

---

## §10. Gap "Opsi 2" Dieksekusi — Batch Overflow Harus Muncul Sebagai Lanjutan di Plan Hari Berikutnya

**Laporan user (dengan screenshot):** JD 15, JD 18, JD 19 di plan **19/08** overflow (indikator
`▶` muncul di tepi kanan, sekitar 05:00-06:00). Tapi saat pindah ke plan **20/08**, baris JD 15/
18/19 di jam 06:00 (awal shift) **langsung kosong** — tidak ada blok "sisa Hold/Cool" dari batch
yang masih berjalan dari malam sebelumnya. Batch baru di 20/08 baru mulai lagi sekitar jam 07:00+
seolah-olah mesin itu benar-benar OFF dari 06:00 sampai batch baru dimulai. User juga menyoroti
dengan tepat: ini bikin **kalkulasi heatmap uap plan 20/08 di jam-jam awal shift jadi rancu**
(understated — tidak menghitung uap yang sebenarnya masih terpakai dari proses sisa semalam).

Ini **persis** gap yang saya sebut "Opsi 2" di §II.4 dan sengaja saya skip dulu di v3 karena
scope-nya besar (butuh join antar `ProductionPlan` berbeda tanggal). Sekarang user minta ini
dieksekusi. Analisis desain lengkap di bawah.

### Kenapa ini terjadi (root cause, bukan bug — gap desain yang disadari sejak awal)

Setiap `ProductionPlan` **independen per tanggal** (`shift_date`). Batch cuma "milik" satu plan
(FK `ProductionPlanBatch.plan`). Ketika batch di plan **A** (19/08) overflow ke menit >1440 (=
jam 06:00+ tanggal 20/08), **tidak ada baris data apa pun** yang dibuat di plan **B** (20/08) —
baik di `ProductionPlanBatch` maupun turunannya. Jadi saat `_serialize_plan(plan_B)` dipanggil,
query `plan.batches...` untuk plan B murni tidak tahu apa-apa soal proses yang masih menyala dari
plan A. Ini **sesuai desain** (batch memang sengaja tidak dipecah ke 2 plan, sesuai requirement
awal "batch tetap diasosiasikan dengan hari mulai") — tapi konsekuensinya, representasi visual
+ steam di plan B untuk jam-jam awal jadi tidak lengkap.

### Constraint penting yang menyederhanakan solusi

Karena guard anomali (`total per batch ≤ 1440 menit`, lihat §II.3) dan `start_offset_minutes`
selalu `< 1440`, **overflow maksimum yang mungkin terjadi < 1440 menit** (dibuktikan:
`overflow = start_offset + total - 1440 ≤ start_offset + 1440 - 1440 = start_offset < 1440`).
Artinya **overflow tidak akan pernah menembus ke hari ke-3** — cukup lihat **1 hari sebelumnya**
saja, tidak perlu rekursi/chain berhari-hari. Ini menyederhanakan implementasi secara signifikan.

### Desain: "Continuation Editable Proxy" (computed view, TIDAK ada tabel/migrasi baru)

> **Keputusan final (dikonfirmasi user):** continuation **editable langsung dari board hari
> ini** (bukan read-only) — edit ditulis-tembus ("write-through") ke batch ASLI di plan sumber.
> Continuation ditampilkan dari plan sumber **apa pun statusnya** (termasuk DRAFT, bukan cuma
> PUBLISHED). Style visual: opacity redup + indikator `◀` di kiri (mirror `▶` yang sudah ada).

Saat serialize plan **B**, backend **juga** mengambil batch-batch overflow dari plan **A** (hari
sebelumnya — dipilih via `_pick_plan_for_date`: prioritas PUBLISHED, kalau tidak ada pakai yang
paling baru diupdate), memotong bagian yang "sudah tampil" di plan A (menit 0-1439), dan sisanya
(bagian yang jatuh di menit ≥1440) disuguhkan sebagai entri di awal track plan B
(`start_offset_minutes = 0`), dengan flag `is_continuation: true` + referensi lengkap ke batch
asli (`source_plan_id`, `source_plan_version`, `source_batch_id`, `source_start_offset_minutes`,
`source_blocks` — struktur LENGKAP batch asli, bukan cuma potongan tail-nya).

**Karena editable, dibuatkan API baru yang mengedit satu batch langsung by id, lintas-plan:**
`PATCH /planning/batches/{batch_id}` dan `DELETE /planning/batches/{batch_id}`. Endpoint ini
menulis ke batch & plan ASLI-nya (plan A), pakai optimistic lock `version` milik plan A (bukan
plan B yang sedang dibuka). Ini murni **computed view** di sisi tampilan (tidak ada duplikasi
data tersimpan) — begitu plan A berubah (lewat endpoint ini ATAU lewat plan A dibuka & disimpan
langsung), continuation di plan B otomatis ikut berubah di fetch berikutnya.

**Interaksi yang didukung dari board hari ini (plan B) untuk batch continuation:**
- **Drag pindah (move)** → translate delta menit ke `source_start_offset_minutes` plan A.
- **Drag ujung (resize-end, Cool/Running)** → translate delta ke durasi blok TERAKHIR di
  `source_blocks` plan A (tail selalu = ekor dari blok terakhir source, jadi pemetaannya aman).
- **Hapus (×)** → `DELETE` batch asli di plan A.
- **Double-click edit (modal penuh)** → modal menampilkan struktur ASLI (`source_blocks`,
  `source_start_offset_minutes`, bukan cuma tail), simpan → `PATCH` ke plan A.
- **Resize batas fase (boundary, mis. Heat↔Hold)** → **TIDAK didukung** dari board hari ini
  (scope-nya ambigu karena tail mungkin cuma sebagian dari satu fase) — kalau perlu, edit dari
  plan A langsung. Handle boundary disembunyikan pada batch continuation.

**Validasi overlap saat edit continuation:** backend (`_check_single_batch_overlap`) cek
terhadap sibling batch DI PLAN A (bukan plan B) — sesuai konteks aslinya. Validasi overlap
client-side (di modal/drag preview) untuk continuation di-skip (karena sibling yang dimiliki
client adalah batch plan B, frame yang salah) — backend tetap otoritatif, error dari server
(400/409) ditampilkan ke user.

### Status implementasi §10: SELESAI

Semua poin di bawah sudah diimplementasikan (backend `manage.py check` OK, frontend
`npm run build` OK, tidak ada linter error baru):

| File | Perubahan |
|---|---|
| `monitoring/utils/steam_calc.py` | + `compute_carryover_blocks()`, `compute_carryover_steam_contribution()` |
| `monitoring/api_planning.py` | Refactor `_validate_batch_structure()` (dipakai ulang), + `_check_single_batch_overlap()`, + `_pick_plan_for_date()`, `_serialize_plan()` menyisipkan continuation + kontribusi uapnya, + endpoint `PATCH /planning/batches/{id}` & `DELETE /planning/batches/{id}` |
| `frontend/src/lib/planningGeometry.js` | `planFromApi` parse field continuation, `planToPayload` & `detectModeMismatches` skip continuation |
| `frontend/src/store/planningApi.js` | + `usePatchBatchMutation`, `useDeleteBatchMutation` |
| `frontend/src/components/planning/PlanningBatchEditModal.jsx` | Mode continuation: prefill dari `sourceBlocks`/`sourceStartOffsetMinutes`, skip validasi overlap client-side, badge info, label tombol hapus |
| `frontend/src/pages/ProductionPlanning.jsx` | Visual continuation (opacity + hatch + `◀`), drag move/resize-end di-commit langsung via `patchBatch`, hapus via `deleteBatch`, modal save via `patchBatch`, refetch plan setelah commit |

**Regresi yang perlu dicek user (F7, manual):**
1. Buka plan hari yang punya batch overflow (mis. 19/08 dgn JD15/18/19) → pindah ke hari
   berikutnya (20/08) → pastikan muncul blok continuation di jam 06:00 dgn style redup + `◀`.
2. Cek heatmap uap 20/08 di jam-jam awal ikut menghitung kontribusi continuation (tidak nol).
3. Drag-pindah continuation → cek berhasil tersimpan (refresh halaman, cek balik di 19/08 &
   20/08 apakah konsisten).
4. Drag ujung continuation (perpanjang/perpendek) → cek tersimpan.
5. Double-click continuation → edit via modal → Simpan → cek tersimpan ke plan sumber.
6. Hapus continuation dari board 20/08 → cek batch di plan 19/08 juga terhapus.
7. Coba bikin overlap (drag continuation ke posisi yang bentrok dengan batch lain di plan
   sumber) → harus ditolak dengan pesan error dari server.
8. Pastikan **Simpan**/**Publish** plan 20/08 TIDAK mengubah/menduplikasi batch continuation
   (karena `planToPayload` sudah memfilternya keluar).

#### Backend — `monitoring/utils/steam_calc.py` (tambah fungsi baru, jangan ubah yang lama)

```python
def compute_carryover_blocks(prev_batches, total_minutes=TOTAL_BUCKETS):
    """
    Dari batch-batch plan HARI SEBELUMNYA yang overflow (start_offset + total > total_minutes),
    hitung sisa blok yang "lanjut" di awal hari ini (offset 0+). Return:
        { machine_code: [{"batch_id", "label", "blocks": [{"phase","duration_minutes"}, ...]}] }
    Hanya utk batch yang benar overflow; batch normal diabaikan.
    """
    result = defaultdict(list)
    for batch in prev_batches:
        cursor = batch.start_offset_minutes
        tail_blocks = []
        for block in batch.blocks.all():
            dur = block.duration_minutes
            block_end = cursor + dur
            if block_end > total_minutes:
                tail_dur = block_end - max(cursor, total_minutes)
                if tail_dur > 0:
                    tail_blocks.append({"phase": block.phase, "duration_minutes": tail_dur})
            cursor = block_end
        if tail_blocks:
            result[batch.machine.code].append({
                "batch_id": batch.id,
                "label": batch.label,
                "blocks": tail_blocks,
            })
    return result
```

#### Backend — `monitoring/api_planning.py::_serialize_plan`

```python
prev_date = plan.shift_date - timedelta(days=1)
prev_plan = (
    ProductionPlan.objects.filter(shift_date=prev_date, status="PUBLISHED")
    .order_by("-updated_at").first()
)
carryover_by_machine = {}
if prev_plan:
    prev_batches = list(
        prev_plan.batches.select_related("machine").prefetch_related("blocks")
    )
    carryover_by_machine = compute_carryover_blocks(prev_batches)
```
Lalu untuk tiap machine di `group_map`, sisipkan entri continuation **di depan** list batch biasa
(`batches_by_machine.get(code, [])`), dengan `start_offset_minutes: 0`, `is_continuation: True`,
`source_plan_id: prev_plan.id`, `source_batch_id`. **Steam preview plan B** juga perlu
menghitung kontribusi continuation ini — cara paling gampang: bikin objek batch "semu" (bukan
model asli, cukup punya atribut `.machine_id`, `.machine`, `.start_offset_minutes=0`, dan
`.blocks` yang meniru interface `.blocks.all()`) lalu masukkan ke
`compute_steam_timeline_from_plan_batches` bersama `batches` asli — **atau** lebih simpel, buat
loop terpisah yang langsung menambah ke array `values` untuk fase aktif (pakai
`steam_active_phases_for_mode`), tanpa perlu bikin objek semu. Opsi kedua lebih ringan dan
kurang rawan bug duck-typing.

**Kenapa hanya cek plan `PUBLISHED`:** draft plan orang lain yang belum tentu final tidak
seharusnya "menghantui" plan hari berikutnya. Kalau prev-day plan belum di-publish, continuation
tidak ditampilkan (dianggap belum final, konsisten dengan cara `PublishedPlan` jadi acuan
"kebenaran" di tempat lain di codebase).

#### Frontend — `frontend/src/lib/planningGeometry.js::planFromApi`

Tambah parsing untuk entri `is_continuation`, taruh di posisi pertama array batch mesin itu,
tandai `isContinuation: true`, `clientId` unik berbasis `srv_carry_${source_batch_id}` (supaya
stabil antar render, tidak collide dgn batch asli).

`computeSteamTimeline` (client preview) **tidak perlu diubah** — dia hanya menghitung dari
`plan.batchesByMachine` yang sudah differetch dari server termasuk continuation-nya (asalkan
continuation ikut dimasukkan ke `batchesByMachine` seperti batch biasa, cukup dengan flag
pembeda) — array kalkulasi otomatis akurat tanpa logic tambahan di JS.

#### Frontend — `ProductionPlanning.jsx`

- `PlanningBatchBlock`: kalau `batch.isContinuation`, render dengan style beda (misal
  opacity 55%, pattern diagonal via CSS `background-image` garis-garis, atau border dashed),
  **nonaktifkan** semua `onMouseDown` (move/resize) dan tombol hapus, ganti `onDoubleClick`
  jadi info-only (tooltip/alert: "Lanjutan dari {label} @ plan {prev_date} — edit di plan itu").
  Tambah indikator `◀` di kiri (mirror dari `▶` di kanan) sebagai sinyal visual "datang dari
  kemarin".
- `hasOverlap` / drag-create / drag-move: continuation **harus tetap dihitung** sebagai
  penghalang overlap (supaya user tidak bisa membuat batch baru yang bertabrakan dengan sisa
  proses kemarin) — otomatis benar selama continuation tetap ada di `batchesByMachine` array yang
  dipakai `hasOverlap`.
- `planToPayload`: **wajib** filter keluar `batch.isContinuation` sebelum dikirim ke
  `PUT /planning/{id}` — continuation bukan milik plan ini, tidak boleh ikut tersimpan/terduplikasi.
- `handleRemove`/edit modal: pastikan tidak bisa dipanggil untuk continuation (guard di level
  `onDoubleClick`/`onRemove` handler, atau langsung tidak pasang handler-nya untuk continuation).

### Ringkasan File yang Berubah

| File | Perubahan |
|---|---|
| `monitoring/utils/steam_calc.py` | Tambah `compute_carryover_blocks()` (fungsi baru, tidak ubah yang lama) |
| `monitoring/api_planning.py` | `_serialize_plan`: query plan hari sebelumnya (PUBLISHED), sisipkan continuation per mesin, tambah kontribusinya ke `steam_preview` |
| `frontend/src/lib/planningGeometry.js` | `planFromApi`: parse `is_continuation` jadi `isContinuation` + `clientId` stabil |
| `frontend/src/pages/ProductionPlanning.jsx` | Render beda utk continuation (style + indikator `◀`, disable interaksi), `planToPayload`-nya sendiri sudah difilter di pemanggil sebelum kirim |

### Yang TIDAK berubah / di luar scope tambahan ini

- **Tidak ada migrasi DB baru** — semuanya computed on-the-fly saat fetch.
- **Draft (belum publish) tidak memengaruhi hari berikutnya** — hanya plan `PUBLISHED` yang jadi
  sumber continuation.
- **Rantai lebih dari 1 hari tidak mungkin terjadi** (dibuktikan di atas via guard 1440 menit),
  jadi tidak perlu rekursi ke H-2, H-3, dst.
- **Continuation tidak bisa diedit dari plan B** — kalau durasi aslinya salah, harus dibuka &
  diedit dari plan A (hari sebelumnya).

---

## §6. Riwayat Perubahan Dokumen

| Tanggal | Bagian | Perubahan |
|---|---|---|
| 21 Agu 2026 | — | Draft v1 dibuat berdasarkan investigasi 507 proses (dokumen `PLANNING_FIX_IMPORT_DURATION_AND_CROSSDAY.md`) |
| 21 Agu 2026 | Semua (v3, dokumen ini) | Audit ulang terhadap kode aktual: (1) koreksi klaim COOL yang tidak didukung kode — jadi kondisional menunggu verifikasi manual; (2) tambah scope backend validasi 1440 yang draft lewatkan; (3) tambah analisis gap steam heatmap cross-plan; (4) detail konkret titik hardcode 1440 di frontend dengan nomor baris; (5) revisi estimasi jadi 3.5–4.5 jam |
| 21 Agu 2026 | §I.2 | **Koreksi sempat salah, lalu diperbaiki lagi (sesi ini):** Sempat tercatat klaim bahwa `detectModeMismatches` "tidak ada di kode" — ini ternyata **keliru** (grep scope salah). Fungsi ini memang ada (`planningGeometry.js:199-230`, dipakai di `ProductionPlanning.jsx`) dan aktif memblokir Simpan/Publish + menampilkan banner **begitu plan dibuka**, bukan cuma saat klik Simpan. Klaim awal soal urgensi §I.2 dikonfirmasi benar dan diperkuat. |
| 21 Agu 2026 | §II.5 #6 | **Konfirmasi verifikasi (sesi ini):** `<td data-chart-track>` di baris 315 `ProductionPlanning.jsx` memang **tidak punya** `overflow-hidden` — klaim plan ini valid, perubahan wajib dilakukan. |
| 21 Agu 2026 | §II.5 #2,3 | **Konfirmasi verifikasi (sesi ini):** Line 546 (`clamp move`) dan line 579–582 (`clamp resize-end`) cocok persis dengan kode aktual — klaim valid. |
| 21 Agu 2026 | §II.3 | **Konfirmasi verifikasi (sesi ini):** `_validate_batches_payload` baris 119–124 di `api_planning.py` memang menolak `start_offset + total > TOTAL_BUCKETS` dengan `HttpError(400, ...)` — klaim valid, perubahan wajib. |


---

## §7. Pertanyaan Konfirmasi — **KEPUTUSAN FINAL (21 Agu 2026)**

| # | Keputusan |
|---|---|
| Q1 | **COOL = sama dengan report** → field COOL **tidak diubah**, tetap `cooling_duration`. Hanya HEAT yang di-fix (`heating_duration` → `real_heating_duration`). |
| Q2 | **Opsi A** dipakai (clip di tepi kanan + indikator `▶`). |
| Q3 | Overflow **bebas**, dibatasi hanya guard anomali (total per batch ≤ 1440 menit / 24 jam). |
| Q4 | Re-import **ditunda** sampai F6 (frontend cross-day) selesai — verifikasi UI sekali jalan. |
| Q5 | Field durasi MANUAL saat import = **`duration_effective`**. |

Detail pertanyaan asli (untuk referensi):

1. **[BARU, PALING PENTING] Verifikasi COOL:** Tolong buka report untuk 1-2 batch (termasuk
   ID=3025184 kalau masih ada) dan screenshot/catat angka COOL yang tampil, lalu saya bandingkan
   dengan nilai `cooling_duration` di DB. Kalau sama → COOL **tidak** diubah, cukup fix HEAT saja.
   Kalau beda → pakai formula `cooling_start_time → end_time` seperti draft asli.
2. **Cross-Day UI:** Opsi A (clip + `▶` di tepi, direkomendasikan) — sudah difinalkan di §3, atau
   masih ingin dipertimbangkan ulang?
3. **Drag cross-day:** Kalau user resize/geser batch AUTO/MANUAL sampai overflow, apakah dibiarkan
   overflow bebas (dibatasi hanya oleh guard anomali 1440 menit **total per batch**, bukan oleh
   batas hari), atau tetap mau ada batas maksimum overflow yang lebih kecil (misal maks +6 jam ke
   hari berikutnya)?
4. **Re-import timing:** Sekarang (setelah F1-F2 saja, sebelum frontend F6 selesai), atau tunggu
   F6 selesai supaya verifikasi UI sekali jalan? (Catatan: kalau import sekarang sebelum F2/F6,
   batch overflow hasil import akan **gagal disimpan ulang** dari board sampai F2 selesai — tidak
   masalah kalau memang belum akan dibuka di board dulu.)
5. **[BARU] Field durasi untuk MANUAL saat import (§I.2):** Untuk mesin `operation_mode=MANUAL`,
   field mana yang paling tepat dipakai sebagai durasi blok `RUNNING` tunggal —
   `duration_effective`, `(end_time - start_time)` total mentah, atau field lain? Ini belum ada
   di command sekarang sama sekali (semua proses diimport sebagai HEAT/STEADY/COOL 3-fase, tidak
   peduli `operation_mode` mesinnya).
