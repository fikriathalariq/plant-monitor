# Laporan Koreksi & Audit: `debug_optimizer.py` vs. Permintaan Steam Levelling

**Dokumen yang diaudit:**
- `debug_optimizer.py` (implementasi simulasi)
- `REPORT_OPTIMASI_STEAM_LEVELLING.md` (laporan hasil dry-run)
- Referensi baseline: `walkthrough.md` (baseline IQR heat/hold/cool per mesin)

**Tujuan dokumen ini:** memverifikasi apakah logika kode benar-benar merepresentasikan instruksi yang diberikan, dan menandai bagian mana yang berisiko membuat hasil simulasi menyesatkan.

---

## 1. Ringkasan Temuan

| # | Temuan | Tingkat Risiko | Kategori |
|---|---|---|---|
| 1 | **Efek domino tak terbatas** pada aturan "gap < 2 jam" bisa menarik batch maju belasan jam, melebihi asumsi fisik "material sudah standby" | 🔴 **Tinggi** | Kesalahan konseptual (spesifikasi + implementasi) |
| 2 | Filter tersembunyi `operation_mode == 'AUTO'` tidak pernah diberitahukan ke Anda maupun disebut di laporan | 🟡 Sedang | Transparansi/dokumentasi |
| 3 | *Escape valve* pencarian slot uap (`break` setelah 12 jam) bisa diam-diam melanggar target 6.000 kg/h tanpa dicatat | 🔴 Tinggi | Validitas hasil |
| 4 | Ketergantungan pada *regex* + *join* manual (`Batch #(\d+)`) untuk mengambil `max_temp` berisiko gagal senyap (default ke 0 → dianggap ≤110°C) | 🟡 Sedang | Kualitas data |
| 5 | Metrik "rata-rata pergeseran -0,12 jam" berpotensi menyesatkan karena dirata-rata dari sebaran yang sangat skew | 🟢 Rendah | Penyajian laporan |
| 6 | Minimum gap 1 jam ikut diterapkan pada kasus gap > 2 jam (arrival), padahal instruksi Anda hanya menyebutkannya untuk kasus < 2 jam | 🟢 Rendah | Interpretasi aturan |

Detail masing-masing di bawah.

---

## 2. Temuan #1 (Kritis): Efek Domino Tidak Realistis pada Aturan "Gap < 2 Jam"

### Apa yang terjadi
Kode menghitung "gap nyata" (`real_gap`) selalu relatif terhadap **batch sebelumnya di mesin yang sama**, menggunakan waktu **real/aktual historis**:

```python
real_gap = r['original_start_abs'] - prev['orig_end_abs']
```

Jika `real_gap < 2 jam`, batch dianggap "continuous flow" (kain sudah standby di mesin) dan boleh ditarik maju. Titik jangkarnya (`E_start`) dihitung dari **jadwal baru (sudah dioptimasi)** batch sebelumnya, bukan dari jadwal real-nya:

```python
E_start = prev['new_end_abs'] + allowed_min_gap   # bukan prev['orig_end_abs']
```

### Mengapa ini bermasalah
Laporan Anda sendiri melaporkan **JD_11 Batch #648 maju 14,7 jam**, karena Batch #647 sebelumnya (yang aslinya molor sampai ±18 jam akibat antrian uap) dipersingkat drastis oleh baseline ideal. Secara matematis kode ini benar mengeksekusi aturan yang Anda tuliskan — tapi mari uji validitas fisiknya:

- Aturan "gap < 2 jam = kain sudah standby" **hanya valid diinterpretasikan pada garis waktu real**. Artinya: kain Batch #648 tiba/siap ±1–2 jam **setelah waktu real selesai Batch #647** (yang terjadi sangat terlambat).
- Begitu Batch #647 dipersingkat 14 jam dalam simulasi, jangkar baru untuk #648 ikut mundur... **maju** 14 jam lebih awal — padahal **tidak ada bukti bahwa kain Batch #648 sudah tiba 14 jam lebih awal dari waktu real-nya**. Kesiapan kain #648 kita hanya tahu terjadi ±1-2 jam setelah waktu real #647 selesai (yang notabene sudah sangat terlambat).
- Dengan kata lain: rantai kompresi (efek domino) **mewariskan asumsi "kain sudah siap" dari batch sebelumnya secara berantai**, padahal asumsi itu awalnya hanya dijamin valid secara lokal (1 pasang batch, berdasarkan data real), bukan untuk seluruh rantai yang sudah bergeser jauh dari waktu real.

### Akar masalah: permintaan Anda atau eksekusi model?
Ini **bukan salah ketik kode**, tapi **celah pada spesifikasi aturan** yang tidak Anda sadari dampaknya saat merumuskan instruksi. Instruksi "gap < 2 jam boleh maju/mundur ±1 jam" masuk akal untuk **satu pasang batch**, tapi tidak eksplisit menyebutkan **batas maksimum kumulatif** ketika efek ini berantai ke banyak batch berturut-turut pada mesin yang sama. Kode mengikuti instruksi secara harfiah, tapi karena instruksi tidak memberi batas, hasilnya menjadi ekstrem dan secara fisik meragukan (kain tidak mungkin "datang" 14,7 jam lebih cepat hanya karena mesin jadi lebih efisien).

### Rekomendasi Perbaikan
Pilih salah satu (atau kombinasi):

1. **Cap pergeseran maju per-batch relatif terhadap real time**, misalnya: pergeseran maju tidak boleh melebihi *slack* yang benar-benar tersedia dari selisih durasi historis vs baseline batch itu sendiri, bukan warisan akumulasi dari batch-batch sebelumnya.
2. **Reset jangkar "kesiapan kain" ke waktu real** setiap kali gap terhadap batch sebelumnya (di real time) ≥ suatu ambang, alih-alih selalu memakai `prev['new_end_abs']`. Idealnya, tambahkan kolom "waktu kain tiba" yang eksplisit dari data lantai pabrik, bukan diinferensi dari gap.
3. Minimal: **beri batas atas eksplisit** (misalnya maksimum maju = gap real batch itu ke batch sebelumnya + 1 jam saja, tidak boleh mewarisi surplus dari batch-batch lebih awal dalam rantai).
4. Apa pun opsi yang dipilih, **laporkan secara terpisah** batch-batch dengan pergeseran maju > 4-6 jam sebagai "butuh verifikasi manual", karena ini adalah sinyal bahwa asumsi model mulai diragukan validitasnya.

---

## 3. Temuan #2: Filter `operation_mode == 'AUTO'` Tidak Diberitahukan

```python
if mode == 'AUTO' and r['max_temp'] > 110 and mc in baseline_data:
```

Kode menambahkan syarat bahwa optimasi baseline **hanya berlaku untuk mesin bermode `AUTO`**. Ini secara teknis **beralasan** (mesin `MANUAL` hanya punya satu blok `RUNNING`, bukan struktur HEAT/STEADY/COOL — jadi baseline heat/hold/cool tidak relevan diterapkan pada mesin manual). Namun:

- Anda **tidak pernah diberi tahu** kriteria ini ada.
- Laporan `REPORT_OPTIMASI_STEAM_LEVELLING.md` mengklaim "436 dari 609 batch (71,5%) dioptimasi, sisanya mempertahankan durasi historis" — **tanpa merinci berapa dari sisa 28,5% itu karena suhu ≤110°C vs. karena mesin berstatus MANUAL**. Ini menyembunyikan sebagian penyebab di balik satu angka gabungan.
- Juga tidak dijelaskan berapa mesin yang `max_temp > 110°C` tapi **kodenya tidak ada di `baseline_data`** (30 mesin saja yang punya baseline dari `walkthrough.md`) — batch pada mesin di luar daftar itu otomatis tidak dioptimasi meski suhunya tinggi.

### Rekomendasi
Tambahkan breakdown di laporan: dari batch yang **tidak** dioptimasi, pisahkan menjadi kategori "suhu ≤110°C (sesuai instruksi, tidak diubah)" vs "suhu >110°C tapi mesin MANUAL/tidak ada baseline (limitasi data)". Kategori kedua adalah gap data yang seharusnya diinformasikan ke Anda, bukan didiamkan.

---

## 4. Temuan #3: *Escape Valve* 12 Jam Bisa Melanggar Target 6.000 kg/h Secara Senyap

```python
while O_start + new_steam_dur < TOTAL_MINUTES:
    window = global_steam[O_start : O_start + new_steam_dur]
    if max(window) + usage <= TARGET_STEAM:
        break
    O_start += 1
    if O_start - E_start > 720:   # 12 jam
        break
```

Jika dalam 12 jam pencarian tidak ditemukan slot yang memenuhi target ≤6.000 kg/h, loop **tetap `break` dan batch dipaksa ditempatkan** di `O_start` terakhir — **walaupun itu melanggar target 6.000 kg/h**. Tidak ada log, warning, atau penghitungan berapa kali ini terjadi.

Ini artinya klaim laporan "**Beban Puncak Uap: 5.985,8 kg/h**" hanya benar **jika tidak ada satu pun batch yang mengenai jalur ini**. Belum ada bukti/verifikasi eksplisit di kode maupun laporan bahwa hal ini tidak pernah terjadi selama 609 batch × 11 hari.

### Rekomendasi
Tambahkan pencatatan (`log`/`print`) setiap kali `O_start - E_start > 720` tercapai, sertakan jumlah kejadian dan batch mana yang terdampak di laporan. Idealnya, verifikasi ulang dengan `max(global_steam)` per-mesin dan per-hari (bukan cuma satu angka global) untuk memastikan tidak ada periode tersembunyi yang melebihi 6.000 kg/h.

---

## 5. Temuan #4: Risiko Silent-Fail pada Pengambilan `max_temp`

```python
m = re.search(r'Batch #(\d+)', b.label)
if m:
    proc = DyeingProcess.objects.filter(machine=b.machine, batch_number=m.group(1)).first()
    if proc and proc.max_temp:
        max_temp = proc.max_temp
```

Jika `b.label` tidak mengikuti format `"Batch #N"` persis, atau `DyeingProcess` yang cocok tidak ditemukan, atau `max_temp` bernilai `None`/`0`, maka `max_temp` tetap `0` — batch tersebut **otomatis dianggap ≤110°C** dan tidak dioptimasi, **tanpa peringatan apa pun**. Ini bisa membuat batch yang sebenarnya bersuhu tinggi justru tidak ikut dikompresi, sehingga hasil "436 batch teroptimasi" berpotensi under-count, bukan karena aturan bisnis, tapi karena kegagalan pencocokan data.

### Rekomendasi
Tambahkan penghitung `unmatched_label_count` dan `missing_dyeing_process_count`, laporkan keduanya. Jika jumlahnya signifikan (>1-2%), perlu investigasi format label sebelum laporan dianggap valid.

---

## 6. Temuan #5: Metrik "Rata-rata Pergeseran -0,12 Jam" Berpotensi Menyesatkan

Laporan menulis rata-rata pergeseran **-0,12 jam (maju 7 menit)**, dihitung dari rata-rata aritmetika seluruh 609 `diff`. Namun laporan yang sama menyebut **177 batch mundur** vs **154 batch maju** — secara jumlah batch, lebih banyak yang **mundur**. Rata-rata bisa tetap negatif (net maju) karena sebagian kecil pergeseran maju berukuran sangat besar (14,7 jam, 11,8 jam, dst. — lihat Temuan #1), yang menarik rata-rata ke arah negatif walau mayoritas batch justru sedikit mundur.

Menyajikan hanya rata-rata tanpa median/distribusi berisiko memberi kesan keseluruhan jadwal "membaik" secara agregat, padahal itu didominasi oleh beberapa outlier ekstrem yang justru problematis (lihat Temuan #1).

### Rekomendasi
Sertakan median pergeseran, serta pisahkan rata-rata "maju" dan rata-rata "mundur" secara terpisah alih-alih digabung menjadi satu angka net.

---

## 7. Temuan #6 (Minor): Minimum Gap 1 Jam Ikut Berlaku di Kasus "Arrival" (>2 Jam)

Instruksi Anda menyebutkan aturan "jarak minimal 1 jam antara cooling dan heating" **secara spesifik untuk kasus gap < 2 jam**. Namun di kode, `allowed_min_gap` (yang menghasilkan minimum 1 jam / atau gap real jika <1 jam) turut dipakai sebagai komponen `max(...)` pada cabang gap > 2 jam:

```python
if real_gap > 120:
    E_start = max(r['original_start_abs'], prev['new_end_abs'] + allowed_min_gap)
```

Karena `real_gap > 120` menit, nilai `allowed_min_gap` otomatis terisi 60 menit — jadi ini menambahkan syarat "minimal 1 jam setelah cooling batch sebelumnya" bahkan di kasus arrival, yang tidak pernah Anda minta secara eksplisit untuk kasus tersebut. Dalam praktiknya dampaknya kecil (karena `max()` akan memilih `original_start_abs` di hampir semua kasus riil), tapi ini adalah contoh **asumsi tambahan yang tidak transparan** — cocok dengan tema Temuan #2.

### Rekomendasi
Jika ini memang dimaksudkan sebagai "waktu changeover fisik minimum mesin" (masuk akal secara teknik), sebutkan secara eksplisit sebagai asumsi terpisah di laporan, bukan menyatu diam-diam dalam variabel yang sama dengan aturan gap<2 jam.

---

## 8. Hal yang Sudah Benar (Tervalidasi)

Agar audit ini seimbang, berikut bagian yang **sesuai** dengan instruksi Anda dan tidak ditemukan cacat:

- **Baseline heat/hold/cool** per mesin di `baseline_data` **cocok 1:1** dengan tabel `walkthrough.md` (dicek silang untuk beberapa mesin: `JD_01`, `JD_11`, dll.) — tidak ada salah transkripsi angka.
- Ambang **">110°C" memicu baseline, "≤110°C" pertahankan data lama** diimplementasikan dengan benar (`r['max_temp'] > 110`), termasuk tidak mengubah durasi untuk kasus ≤110°C.
- Perhitungan `real_gap` menggunakan **waktu real/aktual** (`orig_end_abs`, `original_start_abs`), bukan waktu yang sudah dioptimasi — ini sesuai instruksi bahwa keputusan "apakah kain sudah standby atau belum" harus berbasis data historis, bukan hasil simulasi.
- Aturan **"gap > 2 jam → tidak boleh dimajukan dari data real, hanya boleh mundur"** diimplementasikan dengan benar melalui `E_start = max(original_start_abs, ...)`.
- Aturan **"gap < 2 jam, minimal 1 jam kecuali gap real sudah <1 jam maka pakai itu"** diimplementasikan dengan tepat: `allowed_min_gap = min(60, max(0, real_gap))`.
- Simulasi *steam levelling* memakai array menit-per-menit global (`global_steam`) sehingga perhitungan beban puncak per menit (bukan per jam kasar) — ini granularitas yang baik dan sesuai target "maksimum 6.000 kg/h".

---

## 9. Rekomendasi Tindak Lanjut (Prioritas)

1. **(Wajib sebelum laporan dipakai untuk keputusan produksi)** Perbaiki Temuan #1 — beri batas atas pada efek domino pergeseran maju, dan audit ulang batch-batch dengan pergeseran maju terbesar (Top 5 di laporan asli) untuk verifikasi kelayakan fisiknya (apakah kain benar-benar sudah tersedia di titik waktu baru tersebut).
2. Perbaiki Temuan #3 — tambahkan logging pelanggaran target 6.000 kg/h supaya klaim "5.985,8 kg/h tercapai" bisa diverifikasi, bukan diasumsikan.
3. Tambahkan transparansi untuk Temuan #2 dan #4 (breakdown alasan batch tidak dioptimasi + jumlah data yang gagal dicocokkan).
4. Perbaiki penyajian statistik di Temuan #5 (tambah median, pisah rata-rata maju/mundur).
5. Setelah 1-4 selesai, jalankan ulang simulasi dan bandingkan hasil baru dengan hasil lama sebagai bagian dari laporan revisi.

---

*Dokumen ini adalah hasil audit independen terhadap kode dan laporan yang sudah ada, dibuat untuk mendokumentasikan temuan sebelum hasil dry-run digunakan sebagai dasar keputusan penjadwalan produksi.*
