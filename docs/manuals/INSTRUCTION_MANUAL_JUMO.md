# Panduan Penambahan Perangkat & Sensor (Modbus TCP)

Dokumen ini ditujukan bagi Administrator, Engineer, atau Teknisi yang ingin memasang, menambahkan, atau mengedit konfigurasi *Recorder* (baik perangkat JUMO maupun perangkat Modbus TCP lainnya) serta memetakannya ke mesin yang ada di lantai produksi.

Sistem *Plant Monitor* saat ini telah sepenuhnya mendukung konfigurasi dinamis. Anda tidak perlu lagi melakukan *hardcode* atau mengedit kode Python. Semua konfigurasi dapat dilakukan melalui **Django Admin Panel**.

---

## 1. Konsep Dasar Sistem

Sistem membaca data suhu/kecepatan menggunakan protokol komunikasi **Modbus TCP**. Ada 3 komponen utama di database yang saling berhubungan:

1. **Machine (Mesin):** Objek fisik (seperti `ZET_01`, `JD_03`, `Steam_Pr`) yang akan menerima data hasil bacaan (suhu, speed, dsb).
2. **Jumo Device (Perangkat):** Modul fisik atau *recorder* (misalnya JUMO 500CF, JUMO Logoscreen, CDR) yang bertugas membaca sinyal dari mesin dan mengirimkannya lewat kabel LAN (memiliki IP Address).
3. **Jumo Channel:** Terminal/port di dalam *Jumo Device* yang disambungkan dengan kabel ke *Machine*. Satu Jumo Device biasanya bisa memiliki beberapa channel (misal 6 Channel Analog Input).

**Alur kerjanya:** `Jumo Device` -> membaca `Jumo Channel` -> nilainya dikirimkan ke `Machine`.

---

## 2. Cara Menambahkan Perangkat (Device) Baru

Jika Anda memasang panel kontrol baru, *recorder* baru, atau mengganti IP dari *recorder* yang sudah ada:

1. Buka browser dan akses halaman **Django Admin** (contoh: `http://192.168.11.110:8000/admin/`).
2. Login menggunakan akun Administrator.
3. Pada bagian **Monitoring**, klik menu **Jumo Devices**.
4. Klik tombol **ADD JUMO DEVICE** di pojok kanan atas.
5. Isi formulir pengaturan komunikasi Modbus TCP:

   - **Name:** Nama identifikasi perangkat (contoh: `JUMO_I_502`, `RECORDER_BOILER_1`). Bebas, tapi harus unik.
   - **IP Address:** IP address dari alat fisik tersebut (contoh: `192.168.3.19`).
   - **Port:** Port TCP untuk Modbus. Biarkan default di angka `502` kecuali alat Anda menggunakan port lain.
   - **Start Addr:** Register Modbus awal yang menyimpan data Analog Input (AI).
     - Bisa diisi angka desimal (contoh: `4102`) atau Hexadesimal (contoh: `0x1006` atau `0x0035`).
     - *Pastikan membaca buku manual dari pabrikan alat untuk mengetahui address yang benar.*
   - **Device id:** Slave ID / Unit ID Modbus.
     - Biasanya JUMO 500CF / alat Modbus TCP standar menggunakan `1`.
     - Beberapa alat JUMO tipe lain atau gateway menggunakan *broadcast* yaitu `255`.
     - ⚠️ **Sangat Penting:** Jangan pernah mengisi angka `0`. Banyak alat yang akan langsung memutuskan koneksi internet (TCP Error 10054) jika diberi ID 0.
   - **Num ai:** Jumlah Analog Input / Channel yang aktif di-scan dari perangkat ini (misal `6` atau `4`).
   - **Is active:** Centang (✅) agar sistem memonitor alat ini. Jika alat sedang rusak atau di-*maintenance*, hilangkan centang agar sistem berhenti memanggil alat ini sementara waktu.

---

## 3. Cara Memetakan Sensor (Channel) ke Mesin

Setelah Anda mengisi data IP dan Port dari *Jumo Device* (langkah 2 di atas), geser ke bagian bawah halaman yang sama. Anda akan melihat bagian bernama **Jumo channels**. Di sinilah Anda menyambungkan lubang/kabel sensor fisik ke mesin di aplikasi.

1. Anda akan melihat deretan baris form. Setiap baris mewakili satu urutan pembacaan (Channel Index 0, 1, 2, dst).
2. **Channel Index:** Merupakan urutan/offset alamat dari *Start Addr*. Pastikan berurutan mulai dari `0`, `1`, `2`, hingga sejumlah `Num ai` yang Anda atur sebelumnya.
3. **Machine:** Ketikkan kode atau nama mesin yang tersambung pada lubang (channel) tersebut (contoh: `JD 1`, `ZET 4`, `Steam Pressure`). Form ini memiliki fitur *autocomplete* untuk memudahkan pencarian.
4. **Jika ada Channel (lubang) yang tidak dipakai:** Kosongkan saja pilihan `Machine`-nya, sistem akan otomatis melompat (skip) channel tersebut tanpa menghasilkan error.
5. Setelah semua terisi benar, klik **SAVE** di pojok kanan bawah.

> **Catatan Teknis:** Skrip `jumo_realtime` yang berjalan di *background server* akan mendeteksi penambahan atau perubahan ini dan me-*refresh* konfigurasinya secara **otomatis dalam waktu maksimal 30 detik**. Anda tidak perlu me-restart server!

---

## 4. Troubleshooting & Masalah Umum

Jika setelah disambungkan nilai sensor tidak keluar atau mesin berstatus **"No Signal"**, skrip `jumo_realtime` akan mencatat penyebab pastinya di log. 

Berikut adalah panduan membaca kendala yang sering terjadi:

| Pesan Error | Penyebab & Solusi |
| :--- | :--- |
| **`Connection to (...) failed: timed out`** | Sistem tidak bisa menghubungi alat tersebut. **Solusi:** Cek apakah kabel LAN tertancap dengan baik, IP Address sudah benar, dan apakah alat dapat di-ping dari server. |
| **`[WinError 10054] An existing connection was forcibly closed`** | Perangkat menolak/memutus komunikasi TCP. **Solusi:** Biasanya karena salah memasukkan `Device ID` (misalnya diisi 0). Ubah menjadi `1` atau `255`. |
| **`ExceptionResponse(dev_id=..., function_code=131, exception_code=2)`** | Modbus *Illegal Data Address*. Alat menolak karena address register yang diminta tidak ada. **Solusi:** Cek kembali nilai `Start Addr` apakah salah ketik (desimal/hex). |
| **`Register kurang/kosong. Len: 4`** | Sistem meminta 6 data (Num AI=6) tapi alat cuma punya 4 register. **Solusi:** Kurangi angka `Num ai` di Django Admin sesuai kapasitas asli *recorder*. |

Jika Anda memerlukan pengecekan ekstra cepat tanpa harus melihat layar command prompt server, akses halaman `/jumo_live` (JUMO Live Monitor) di web app untuk melihat respon dari seluruh mesin secara seketika (*real-time*).
