# Analisis dan Saran UI/UX Filter Anomali

## Perubahan yang Dilakukan
1. **Penghapusan Filter Eksternal (Client-Side):**
   - Filter `Mesin` dan `Tipe Analisis` yang sebelumnya berada di header halaman `AnomalyDetection` telah dihilangkan. Hal ini membuat tampilan header atas jauh lebih bersih dan fokus pada *Action Buttons* (Refresh, Export, Print) serta Filter *Backend* (Status & Tanggal) yang memang harus mengambil data ulang dari server.
2. **Implementasi Excel-Style Column Header:**
   - Semua header kolom pada tabel TanStack kini menggunakan komponen `DataTableColumnHeader`.
   - Ketika header di-klik, pengguna akan melihat *dropdown* yang berisi opsi pengurutan (Sort A-Z, Z-A, Clear Sort) dan juga daftar nilai unik dari kolom tersebut (Filter).
   - Filter sudah mengadaptasi gaya Excel, dilengkapi *search box* dan *checkbox* (*Select All*, atau pilih secara spesifik) untuk kemudahan filter pada data kategorikal yang banyak.
3. **Penyelarasan Export Excel:**
   - Fitur Ekspor Excel kini akan mengekspor baris-baris data yang secara spesifik sedang *tampil* (terfilter) oleh tabel, sehingga apa yang di-download benar-benar sesuai dengan apa yang dilihat di layar (WYSIWYG - *What You See Is What You Get*).

## Masukan dan Saran Lanjutan (Next Steps)
Berikut adalah beberapa rekomendasi UI/UX untuk menyempurnakan interaksi pada tabel:

1. **Indikator Filter Aktif di Luar Tabel:**
   Meskipun filter di level kolom (Excel-style) sangat fleksibel, terkadang pengguna kesulitan mengingat kolom apa saja yang sedang aktif difilter, terutama jika tabel memiliki banyak kolom. 
   - *Saran:* Tambahkan deretan "Chips" / "Tags" kecil di atas tabel (di bawah toolbar) yang menampilkan filter aktif (Contoh: `Mesin: Mesin A, Mesin B (x)`, `Tipe: Suhu (x)`). Tombol silang `(x)` pada chip dapat langsung menghapus filter dari kolom bersangkutan.

2. **Debounce pada Kolom Pencarian Global vs Kolom:**
   Meskipun pencarian melalui *dropdown* header sangat praktis untuk mencari nilai unik, seringkali user hanya mengingat satu kata kunci acak (misal sebagian nomor PO) tanpa tahu kolom asalnya.
   - *Saran:* Mempertahankan / menambahkan kembali *Global Search Bar* (pencarian teks ke semua kolom sekaligus) di pojok tabel dapat membantu pencarian lintas-kolom dengan lebih cepat.

3. **Optimasi pada Data Berjumlah Sangat Besar (Pagination vs Client-side Filter):**
   TanStack Table saat ini melakukan filter nilai unik *(Unique Values)* dengan membaca semua baris yang ter-load. Karena ini adalah data anomaly yang mungkin jumlah barisnya cukup banyak (misalnya >500 baris setelah fetch awal).
   - *Saran:* Apabila total data nantinya menyentuh ribuan baris, maka *Unique Values* sebaiknya juga dihitung dan disuplai langsung dari Backend (melalui *Faceted/Aggregated API*), dan filter tabel juga diarahkan secara *Server-Side Filtering* agar performa UI React tidak menurun / patah-patah saat merender ratusan nilai unik di dalam *dropdown list*.

4. **Keseragaman Format Tanggal:**
   Pada kolom *Waktu Start*, list filternya akan mengumpulkan *string* tanggal spesifik per detiknya. Dalam Excel, tanggal biasanya di-grouping berdasarkan Bulan/Tahun.
   - *Saran:* Jika filter tanggal di dalam tabel sering digunakan, buat kolom virtual di tabel yang hanya berisi "Bulan" atau "Tanggal (tanpa jam)" agar dropdown filter tanggal tidak terlalu panjang dan lebih mudah dicentang.

Keseluruhan perbaikan UI ini membuat pengguna jauh lebih familiar karena mengadopsi standar *software* spreadsheet pada umumnya, meningkatkan kenyamanan saat menganalisis data mesin.
