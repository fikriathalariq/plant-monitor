# Implementation Plan — Print Production Planning (samakan dgn Snapshot History)

## I. Analisis Mendalam

### I.1 Cara kerja print di aplikasi ini (arsitektur umum)

Print di app ini **tidak** memakai `window.print()` polos + `@media print` generik. Setiap
halaman yang butuh cetak A4 custom (Snapshot History, Analytics Grafik, Process Report) memakai
pola yang sama:

1. Saat tombol cetak diklik, `handlePrint()`:
   - Menambahkan elemen `<style>` berisi `@page { size: ...; margin: ...; }` ke `<head>`.
   - **Menambahkan class penanda** ke `<html>`/`<body>`, misal `printing-snapshot`,
     `printing-grafik`, `printing-process-report`.
   - (Snapshot) menunggu 2x `requestAnimationFrame` lalu memanggil `window.print()`, supaya
     browser sempat re-layout dulu dengan class baru sebelum snapshot cetak diambil.
   - Saat event `afterprint`, class penanda + `<style>` dilepas lagi (cleanup).
2. Di `index.css`, ada **rule global default** (baris 65-88) yang berbunyi kurang lebih:
   > "Kalau `<body>` TIDAK punya salah satu class `printing-snapshot` / `printing-grafik` /
   > `printing-process-report`, maka **SEMUA elemen disembunyikan (`visibility:hidden`)
   > kecuali** elemen dengan class `.print-area` beserta anak-anaknya."
3. Lalu ada blok `@media print` **khusus per class penanda** (mis. `html.printing-snapshot ...`)
   yang mengatur ulang layout: `position:static`, `overflow:visible`, lebar kolom, dsb, supaya
   tabel timeline bisa mengalir alami ke banyak halaman A4 landscape.

### I.2 Root cause: Production Planning BELUM ikut pola ini sama sekali

Cek `ProductionPlanning.jsx` (`handlePrint`, sekitar baris 784-792):

```javascript
const handlePrint = () => {
  const style = document.createElement('style');
  style.id = 'planning-print-style';
  style.textContent = '@page { size: A4 landscape; margin: 8mm; }';
  document.head.appendChild(style);
  const cleanup = () => style.remove();
  window.addEventListener('afterprint', cleanup, { once: true });
  window.print();
};
```

Ini **hanya** mengatur ukuran kertas — **tidak pernah menambahkan class penanda apa pun** ke
`<html>`/`<body>`. Akibatnya, saat dicetak:

- Rule global default di §I.1 poin 2 aktif (karena tidak ada `printing-snapshot`/
  `printing-grafik`/`printing-process-report` di body).
- Rule itu men-set `visibility:hidden` ke **SEMUA** elemen, kecuali `.print-area`.
- Halaman Production Planning **tidak punya elemen `.print-area` sama sekali** (grep
  membuktikan `print-area` hanya dipakai halaman lain seperti Dyeing Analytics).

**Kesimpulan: hasil cetak Production Planning saat ini kemungkinan besar BLANK / kosong total**
(bukan cuma "beda style" dari Snapshot History) — ini bug yang lebih serius dari yang terlihat.
Selain itu, seandainya pun tidak blank, tabel `<table>` di Production Planning juga tidak punya
class-class struktural (`snapshot-print-table`, `snapshot-print-scroll`, dst.) yang dipakai
Snapshot History untuk mengatur ulang layout cetak (kolom nama, tinggi baris, break halaman per
grup, dll.) — jadi tetap akan berantakan / terpotong scroll-area meskipun terlihat.

### I.3 Perbandingan struktur JSX (apa yang sudah ada vs yang belum)

| Elemen | Snapshot History (`SnapshotHistoryPivot.jsx`) | Production Planning (`ProductionPlanning.jsx`) saat ini |
|---|---|---|
| Class penanda cetak di `<html>`/`<body>` | `printing-snapshot` (di-toggle saat print) | **Tidak ada** |
| Double `requestAnimationFrame` sebelum `window.print()` | Ada | Tidak ada |
| Root flex wrapper | `snapshot-print-flow` | `snapshot-print-flow` ✅ (sudah ada) |
| Wrapper scroll-area tabel | `snapshot-print-scroll` | Class polos `overflow-auto ... m-2 ... print:m-0 print:border-0` (**tidak ada** `snapshot-print-scroll`) |
| `<table>` | `snapshot-print-table` | Class polos `w-full min-w-[68rem] ...` (**tidak ada** class struktural) |
| `<col>` nama mesin | `snapshot-print-name-col` | Tidak ada |
| Baris judul cetak (`<tr>` hidden, muncul print) | `snapshot-print-title-row` + judul + subjudul + **legenda print** (`SnapshotPrintLegend`) | Ada `<tr class="hidden print:table-row">` dgn judul, tapi **tanpa class struktural** dan **tanpa legenda print** |
| Baris header grup mesin | `snapshot-group-row` (dapat `break-after: avoid-page`) | `<tr>` polos (tidak ada class, bisa ke-cut di tengah antara judul grup & baris pertamanya) |
| Baris per-mesin | `snapshot-machine-row` | `snapshot-machine-row` ✅ (sudah ada, di `MachineRow`) |
| `data-chart-track` pada track drag | Ada | Ada ✅ |
| `data-chart-cell` pada sel heatmap uap | Ada (utk reset `position` + tinggi cetak) | **Tidak ada** |
| Tombol hapus (×) / handle resize saat cetak | N/A (read-only) | Belum ada `print:hidden` → akan ikut tercetak (tidak relevan di kertas) |

### I.4 Bahaya tersembunyi kalau asal reuse class CSS snapshot

Ada satu rule CSS snapshot yang **TIDAK BOLEH** langsung dipakai ulang untuk Production
Planning:

```css
html.printing-snapshot .snapshot-print-table td[data-chart-track] > div.absolute {
  width: 100% !important;
  height: 100% !important;
}
```

Di Snapshot History, anak langsung `<td data-chart-track>` yang `absolute` cuma **satu** div
pembungkus semua segmen (`<div className="absolute inset-0 z-0 flex ...">`), jadi aman dipaksa
`100%`. Tapi di Production Planning, anak langsung `<td data-chart-track>` yang `absolute` ada
**banyak** — satu per batch (`<div data-batch-block>` dari `PlanningBatchBlock`, posisinya pakai
`left`/`width` inline persentase) plus indikator overflow `▶`/`◀`. Kalau rule di atas ikut
diberlakukan ke Production Planning, **setiap batch akan dipaksa selebar 100% track**,
menghancurkan layout Heat/Hold/Cool yang sedang di-drag-desain. **Rule ini harus TETAP hanya
untuk `printing-snapshot`, tidak digabung ke Production Planning.**

## II. Rencana Implementasi

Prinsip: **reuse struktural**, bukan duplikasi CSS. Class-class struktural (`snapshot-print-*`)
sudah generik by design (bukan cuma "punya Snapshot"), jadi rule CSS yang aman digabung tinggal
ditambah selector `html.printing-production-planning`. Yang tidak aman (§I.4) dibiarkan eksklusif
snapshot. Tidak ada perubahan backend sama sekali (murni frontend: CSS + JSX).

### II.1 `frontend/src/index.css` — tambah class penanda baru + reuse rule struktural

1. Di 4 selector rule "hide everything by default" (baris ±65-88), tambahkan
   `:not(.printing-production-planning)` di setiap `body:not(...)`.
2. Pada blok `@media print` khusus snapshot (baris ±91-222), gabungkan selector
   `html.printing-production-planning` (via koma) ke rule-rule yang **struktural & generik**:
   `.snapshot-print-flow`, `.snapshot-print-root`, `.snapshot-print-scroll`,
   `.snapshot-print-table` (+ `thead`/`tbody`/`tr`/`thead tr`), `.snapshot-group-row`,
   `th, td { position:static }`, `.snapshot-print-name-col`, `.snapshot-print-title-row`,
   `.snapshot-print-legend`, `col:first-child/last-child`, dan rule tinggi/posisi
   `td[data-chart-track], th[data-chart-cell]` (posisi relative + overflow hidden + padding 0),
   termasuk rule tinggi `.steam-heatmap-row th[data-chart-cell] { height: 5mm }` dan
   `td[data-chart-track] { height: 4mm }`.
3. **JANGAN** gabungkan rule `td[data-chart-track] > div.absolute { width/height:100% }` (lihat
   §I.4) — biarkan itu eksklusif `html.printing-snapshot`.
4. Tambah beberapa rule BARU (khusus Production Planning) di blok terpisah:
   - Sembunyikan kontrol interaktif yang tidak relevan di kertas: tombol hapus (×) dan handle
     resize (boundary/end) pada batch — cukup tambahkan `print:hidden` langsung di JSX
     (Tailwind), tidak perlu CSS terpisah.
   - Pastikan indikator overflow `▶` dan (jika sudah ada dari fitur continuation) `◀` TETAP
     tercetak (tidak diberi `print:hidden`) karena itu informasi penting untuk pembaca kertas.

### II.2 `frontend/src/pages/ProductionPlanning.jsx`

1. **`handlePrint`** — samakan pola dgn `SnapshotHistoryPivot.jsx`:
   ```javascript
   const handlePrint = () => {
     const style = document.createElement('style');
     style.id = 'planning-print-page-style';
     style.textContent = '@page { size: A4 landscape; margin: 8mm; }';
     document.head.appendChild(style);
     document.documentElement.classList.add('printing-production-planning');
     document.body.classList.add('printing-production-planning');
     const cleanup = () => {
       document.documentElement.classList.remove('printing-production-planning');
       document.body.classList.remove('printing-production-planning');
       document.getElementById('planning-print-page-style')?.remove();
     };
     window.addEventListener('afterprint', cleanup, { once: true });
     requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
   };
   ```
2. **Wrapper scroll-area** (div `overflow-auto ... m-2 sm:m-3 ...`) → tambah class
   `snapshot-print-root snapshot-print-scroll` (digabung dgn class yang sudah ada).
3. **`<table>`** → tambah class `snapshot-print-table` (gabung dgn `w-full min-w-[68rem] ...`).
4. **`<col>` pertama** (kolom nama mesin) → tambah class `snapshot-print-name-col`.
5. **Baris judul cetak** (`<tr className="hidden print:table-row">`) → tambah class
   `snapshot-print-title-row`, dan lengkapi kontennya senada Snapshot History:
   - Judul: **"Perencanaan Produksi Mesin"**.
   - Subjudul: `Shift {selectedDate} · {plan.name || 'Tanpa nama'} · Status: {plan.status} ·
     Dicetak: {timestamp}`.
   - Tambah komponen kecil baru `PlanningPrintLegend` (mirip `SnapshotPrintLegend`) yang
     render legenda fase (Heat/Hold/Cool/Running dari `PHASE_COLORS`) + legenda skala uap
     (`STEAM_HEAT_LEGEND`), dengan class `snapshot-print-legend` supaya ikut aturan
     `display:flex !important` saat cetak.
6. **Baris header grup mesin** (`<tr>` pembungkus `<th colSpan={2}>` nama grup) → tambah class
   `snapshot-group-row`.
7. **Baris "Uap" (`<th>` pembungkus `<SteamHeatmap>`)** → tambah attribute `data-chart-cell`
   dan class `steam-heatmap-row` pada `<tr>` pembungkusnya (supaya kena rule tinggi 5mm saat
   cetak, sama seperti Snapshot History).
8. **Kontrol interaktif per-batch** (`PlanningBatchBlock`) → tambah `print:hidden` ke:
   - Tombol hapus (×).
   - Handle resize boundary (garis antar fase).
   - Handle resize end (ujung Cool/Running).
   (Drag-handle ini murni UI interaktif, tidak berguna & mengotori tampilan di kertas.)
9. **Toolbar/status/mode-issue banners** — sudah punya class `no-print`, otomatis ikut
   tersembunyi lewat rule `html.printing-production-planning .no-print { display:none }` yang
   ditambahkan di §II.1 poin 2 (bagian `aside, header, .no-print`).

### II.3 Komponen baru: `PlanningPrintLegend`

Ditaruh di `ProductionPlanning.jsx` (sejenis fungsi kecil `SnapshotPrintLegend` di
`SnapshotHistoryPivot.jsx`), isi:
```jsx
function PlanningPrintLegend() {
  return (
    <div className="snapshot-print-legend hidden print:flex flex-wrap items-center gap-x-2.5 gap-y-0.5 mt-1">
      {['HEAT', 'STEADY', 'COOL', 'RUNNING'].map((key) => (
        <span key={key} className="flex items-center gap-1 text-[8px] text-gray-600">
          <span className={`inline-block w-2.5 h-1.5 ${(PHASE_COLORS[key] || {}).bg}`} />
          {PLANNING_PHASE_LABEL[key]}
        </span>
      ))}
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[8px] text-gray-600">
        <span className="text-gray-500 font-medium">Uap:</span>
        {STEAM_HEAT_LEGEND.map((item) => (
          <span key={item.label} className="flex items-center gap-0.5">
            <span
              className={`inline-block w-2.5 h-1.5 ${item.border ? 'border border-gray-300' : ''}`}
              style={{ backgroundColor: item.color }}
            />
            {item.label}
          </span>
        ))}
      </span>
    </div>
  );
}
```
(Perlu import `STEAM_HEAT_LEGEND` dari `../components/SteamHeatmap` — saat ini
`ProductionPlanning.jsx` sudah mengimpornya untuk legenda footer, tinggal reuse.)

### II.4 Ringkasan file yang berubah

| File | Perubahan |
|---|---|
| `frontend/src/index.css` | + `printing-production-planning` di 4 negasi rule default; gabung selector struktural aman ke rule snapshot yang relevan; **tidak** gabung rule `td[data-chart-track] > div.absolute` |
| `frontend/src/pages/ProductionPlanning.jsx` | `handlePrint` pola toggle class + double-RAF; tambah class struktural (`snapshot-print-scroll/root/table/name-col/title-row/group-row`, `data-chart-cell`); tambah `PlanningPrintLegend`; `print:hidden` pada kontrol interaktif batch |

**Tidak ada perubahan backend, tidak ada migrasi, tidak ada perubahan API.**

## III. Yang TIDAK diubah / di luar scope

- Style print untuk MachineRow tetap tabular sama seperti Snapshot History (nama mesin +
  track), tidak ada redesain visual baru selain menyamakan mekanisme cetak.
- Tidak menambah opsi "pilih grup mesin" khusus print (Snapshot History punya filter grup di
  toolbar biasa yang otomatis ikut ke print karena keduanya pakai state yang sama — Production
  Planning saat ini tidak punya filter grup sama sekali, jadi tidak relevan ditambahkan di sini).
- Continuation batch (fitur cross-day dari rencana sebelumnya) tetap tercetak apa adanya
  (termasuk indikator `◀`), tidak ada styling print khusus tambahan untuknya di luar yang sudah
  berlaku ke batch biasa.

## IV. Rencana Pengujian Manual (setelah implementasi)

1. Buka Production Planning, isi minimal 1 grup dengan beberapa batch (campuran AUTO overflow +
   MANUAL biasa).
2. Klik tombol Cetak (Printer icon) → buka print preview browser (jangan langsung print
   fisik/PDF dulu).
3. Pastikan preview **tidak blank** — semua grup & baris mesin tampak.
4. Pastikan ukuran kertas A4 landscape, margin 8mm (sama seperti Snapshot History).
5. Bandingkan visual berdampingan dengan hasil print Snapshot History: font judul, subjudul,
   legenda fase & uap, lebar kolom nama mesin, tinggi baris track/heatmap uap.
6. Pastikan tombol hapus (×) dan handle resize batch TIDAK muncul di hasil cetak.
7. Pastikan indikator overflow (`▶`)/continuation (`◀`) tetap muncul di hasil cetak.
8. Cetak data dengan banyak grup/mesin (>1 halaman) → pastikan judul grup tidak "yatim" di
   bagian bawah halaman (berkat `snapshot-group-row { break-after: avoid-page }`) dan baris
   mesin tidak terpotong di tengah antar halaman (`snapshot-machine-row { break-inside:
   avoid }` — sudah otomatis ikut karena class ini sudah dipakai di `MachineRow`).
9. Tutup print dialog (batal atau cetak) → pastikan class `printing-production-planning` &
   `<style>` `@page` ter-cleanup (cek DevTools: `document.documentElement.className` kembali
   normal) — refresh tidak seharusnya diperlukan.
