# Laporan Analisis Mendalam: Deteksi Anomali Plant Monitor

Tanggal analisis: 26 Okt 2026. Studi kasus: `:8002/history/report/4047880`.

Semua angka di bawah diukur langsung dari database PostgreSQL. Scan membaca data saja dan tidak mengubah apa pun. Satu uji coba `evaluate_identity_anomaly` dijalankan di dalam transaksi yang di-rollback. Skrip bukti ada di folder `scratch/` (`probe1.py` sampai `probe7.py`).

---

## 1. Ringkasan Eksekutif

> [!IMPORTANT]
> Dugaan Anda benar. Mayoritas anomali **memang tidak terdaftar** di halaman `/anomalies`. Halaman Process Report menghitung 8 jenis deteksi secara *live*, tetapi sistem hanya **menyimpan** 5 jenis ke tabel `DataAnomaly` (`SUHU`, `HEAT`, `KEEP`, `COOL`, `REHEATING`). Yang disimpan itu pun sering terlewat karena pemicunya tidak andal.

| Indikator | Nilai |
|---|---|
| Proses valid dan selesai (30 hari) | **1.642** |
| Yang terdaftar sebagai `DataAnomaly` | **251** (15,3%) |
| Proses tanpa identity (tidak bisa dievaluasi sama sekali) | **353** (21,5%) |
| Proses ber-identity tapi program belum ada Master Threshold | **138** |
| Re-Heating terdeteksi live (14 hari) vs terdaftar | **33 vs 14** |
| Anomali pernah di-resolve user (sepanjang waktu) | **0 dari 257** |
| Median jeda dari proses selesai sampai anomali muncul | **34,6 jam** (P90: 66 jam) |

**Tiga akar masalah:**
1. **Deteksi di report tidak disimpan.** Over-holding, late-stop, cooling lambat atau stagnan, jeda heating, dan suhu awal tinggi hanya muncul di Process Report, tidak di daftar anomali.
2. **Pemicu penyimpanan tidak andal.** Evaluasi hanya berjalan saat `DyeingIdentity` di-save. Penyapu berkala (`loop_anomalies.bat`) cuma menjalankan perintah **sekali** lalu berhenti di `pause`.
3. **Prasyarat terlalu ketat.** Anomali butuh identity, program, dan (untuk SUHU/HEAT/KEEP/COOL) master threshold. Batch tanpa itu tidak pernah dievaluasi.

---

## 2. Studi Kasus: Batch 4047880 (JD_16 #741, Program P. 013)

### 2.1 Fakta proses

| Parameter | Aktual | Ideal program |
|---|---|---|
| Heating (real) | 260 mnt | 110 mnt |
| Holding | 52 mnt | 60 mnt |
| Cooling | 42 mnt | 20 mnt |
| Total efektif | 354 mnt | 190 mnt (efisiensi sekitar 54%, grade C) |
| Peak temp | 131,5°C | 130°C |
| Tekanan uap rata-rata | 3,79 bar | ambang 3,8 bar |
| Pasca-70°C sampai OFF | 32 mnt | batas 45 mnt |
| Idle sebelum heating | 14 mnt | batas 20 mnt |

Peristiwa utama: pukul **23:26** suhu turun dari puncak ke **87,2°C** (belum menyentuh 70°C) selama 17 menit, lalu dipanaskan lagi ke **131,7°C**. Ada 2 siklus heating, dengan **+202 menit** siklus tambahan.

### 2.2 Dua kartu yang muncul di report

| Kartu | Sumber | Dihitung | Disimpan di `DataAnomaly` |
|---|---|---|---|
| `MULTIPLE_HEATING_CYCLES` (CRITICAL) | [api_report.py L2060-2100](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/monitoring/api_report.py#L2060-L2100) | Live, tiap report dibuka | Ya (sebagai flag `REHEATING`) |
| `WRONG_LINK` (HIGH, flags `HEAT, REHEATING`) | [api_report.py L2242-2254](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/monitoring/api_report.py#L2242-L2254) | Dari DB | Ya |

Temuan dari kasus ini:
- **Kejadian yang sama muncul dua kali.** Kartu live dan kartu DB menggambarkan peristiwa yang sama.
- **Label `WRONG_LINK` salah.** Semua 257 anomali di DB bertipe `WRONG_LINK`, padahal kasus ini jelas re-heating, bukan salah link. Rekomendasi di kartu DB ("Verifikasi kesesuaian input nama Program...") menyesatkan untuk kasus ini.
- **Teks "Sistem Deteksi Z-Score / Statistik" tidak akurat.** Yang dipakai adalah batas persentil (IQR) dari `AnomalyThresholdMaster`, bukan Z-Score.
- **Diagnosis heating kemungkinan keliru.** Report menyebut "TERHAMBAT SUPLAI UAP" karena 3,79 bar < 3,8 bar (selisih 0,01 bar). Durasi heating 260 mnt sudah mencakup siklus ke-2, jadi kelambatan itu lebih tepat dikaitkan ke re-heating daripada ke uap.
- **Dua metrik heating berbeda.** Detektor memakai `heating_duration` (220), report memakai `real_heating_duration` (260). Ini sebabnya `heat_diff` di anomali (110) berbeda dari angka di report (150).
- **Anomali ini baru terdaftar 16 jam setelah proses selesai** (dibuat 23 Okt 12:42 UTC, proses selesai 22 Okt 20:58 UTC). Penyebabnya diduga pemicu bergantung pada operator menyimpan identity.

---

## 3. Temuan Terukur dari Database

### 3.1 Cakupan data

| Metrik | Nilai |
|---|---|
| `DyeingProcess` total / valid | 21.335 / 21.041 |
| `DyeingIdentity` terhubung ke proses / + program | 6.415 / 6.351 |
| `DataAnomaly` total | 257 (semua `WRONG_LINK`, semua unresolved) |
| Sebaran severity | LOW 143, MEDIUM 70, CRITICAL 30, HIGH 14 |
| Sebaran flag | HEAT 112, KEEP 105, SUHU 104, COOL 72, REHEATING 14, SUHU_HARD 5 |
| `AnomalyRuleConfig` aktif | 1 (hanya `HARD_TEMP_LIMIT`) |
| `AnomalyThresholdMaster` | 320 (238 di antaranya berbasis kurang dari 10 sampel) |
| Proposal kalibrasi (`AnomalyThresholdProposal`) | 0 |
| Anomali unresolved berumur lebih dari 7 hari | 72 |

### 3.2 Deteksi live yang tidak tersimpan (30 hari, 1.642 proses)

| Deteksi (kondisi di report) | Memenuhi syarat | Terdaftar di DB | Catatan |
|---|---|---|---|
| `OVER_HOLDING` (hold > ideal + 8 mnt) | 264 (16%) | 66 | CRITICAL (> 25 mnt): 144 |
| `LATE_STOP_AFTER_COOLING` (> 45 mnt) | 491 (30%) | 74 | CRITICAL (> 60 mnt): 312 |
| `SLOW_COOLING_ANOMALY` | **931 (57%)** | 195 | Terlalu banyak, perlu kalibrasi ulang |
| `START_TEMP_HIGH` (> 60°C) | 34 | **0** | Tidak pernah terdaftar |
| `PRE_HEAT_IDLE` (> 20 mnt) | 740 (45%) | n/a | Berlabel INFO, terlalu umum |
| Hold kurang dari 50% ideal | 23 | 4 | Belum ada detektornya di report |
| Peak temp kurang dari ideal − 10°C | 23 | n/a | Belum ada detektornya |
| Tidak pernah mencapai < 70°C | 12 | n/a | Belum ada detektornya |
| Durasi efektif > 600 mnt | 24 | n/a | Belum ada detektornya |
| Re-Heating (live, 14 hari) | 33 | 14 | 19 tidak terdaftar |

Kolom "Terdaftar di DB" berarti batch itu punya *record* anomali apa pun. Belum tentu flag-nya sama dengan deteksi di kolom pertama. `MID_HEATING_PAUSE` dan stagnasi cooling berbasis log tidak dipindai (tidak diukur).

### 3.3 Re-Heating terlewat (14 hari)

Dari 19 batch yang tidak terdaftar:
- 16 batch **punya identity dan program**, tetapi tidak punya record anomali.
- 2 batch tanpa identity, keduanya mesin `Temp_RB_Steam` (lihat bagian 4.3).
- 1 batch punya identity tanpa program.

Uji rollback pada 4 batch dari kelompok pertama (JR_08 #701, JD_01 #2003, JR_11 #652, JD_12 #822): `evaluate_identity_anomaly` sekarang **menghasilkan `inserted` dengan severity HIGH** dan flag `REHEATING`. Artinya logika deteksinya benar. Yang gagal adalah **pemicunya**, bukan detektornya.

---

## 4. Akar Masalah (Teknis)

### 4.1 Pemicu penyimpanan tidak andal

| # | Masalah | Lokasi |
|---|---|---|
| T1 | Evaluasi real-time hanya lewat `post_save` `DyeingIdentity`, dan semua exception ditelan `except Exception: pass`. Jika terjadi error, tidak ada jejaknya. | [signals.py L160-165](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/monitoring/signals.py#L160-L165) |
| T2 | Tidak ada trigger saat `DyeingProcess` **selesai**. Jika identity disimpan sebelum proses selesai atau sebelum metrik final terisi, hasilnya `none` dan tidak pernah dievaluasi ulang. | signals.py |
| T3 | `loop_anomalies.bat` menjalankan `detect_anomalies` **sekali** lalu `pause`, padahal [START_SEMUA.bat](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/START_SEMUA.bat) mengklaim "berulang setiap 60 detik". Penyapu berkala praktis tidak berjalan. | [loop_anomalies.bat](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/loop_anomalies.bat) |
| T4 | `detect_anomalies --days 1` hanya menyapu jendela 1 hari. Batch yang terlewat lebih dari 1 hari tidak pernah diperbaiki. | [detect_anomalies.py L145-167](file:///c:/Users/HP/Documents/Plant-Monitor/plant-monitor/monitoring/management/commands/detect_anomalies.py#L145-L167) |
| T5 | Tidak ada auto-resolve di jalur V2. `calculate_anomalies.py` (V1) punya, tetapi tidak dipakai. Anomali yang sudah normal tetap `unresolved`. | calculate_anomalies.py |
| T6 | Anomali baru muncul rata-rata 34,6 jam setelah proses selesai, sehingga tidak bisa dipakai untuk koreksi harian. | Bagian 1 |

### 4.2 Prasyarat evaluasi terlalu ketat

| # | Masalah | Dampak |
|---|---|---|
| P1 | Anomali selalu terikat ke `identity_record` (`evaluate_identity_anomaly` mulai dari identity). Batch tanpa identity tidak bisa dievaluasi. | 353 batch (21,5%) bebas dari deteksi. Pada 7 hari terakhir 91 dari 398 batch tidak ter-link. |
| P2 | Tanpa `AnomalyThresholdMaster`, flag SUHU/HEAT/KEEP/COOL tidak pernah dihasilkan. | 138 batch tidak mendapat cek deviasi sama sekali. |
| P3 | Master berbasis sampel sangat sedikit (238 dari 320 punya < 10 sampel). Lebar band heating median 60 menit dan maksimum 492 menit, jadi hampir apa pun lolos. | Under-detection. |
| P4 | Program tanpa nilai ideal (nilai `0` atau `null`) membuat diff bernilai `None` sehingga dilewati. | Cek dilewati diam-diam. |

### 4.3 Kualitas deteksi

| # | Masalah | Bukti |
|---|---|---|
| Q1 | **Mesin utilitas ikut dihitung sebagai batch.** `Temp_RB_Steam` dan `Temp_R_Bakar` bukan mesin dyeing. Re-Heating terdeteksi sampai **274 siklus / 6.428 menit** pada Temp_RB_Steam #53. | Data dari scan |
| Q2 | Dua definisi durasi heating (`heating_duration` vs `real_heating_duration`) berbeda lebih dari 10 menit pada **327 dari 1.634** batch (20%). | Data dari scan |
| Q3 | `anomaly_type` selalu `WRONG_LINK` meski penyebabnya re-heating, suhu, atau durasi. | 257 dari 257 |
| Q4 | `SUHU_HARD` memakai `display_label` yang sama dengan `SUHU` ("Suhu"), sehingga tidak bisa dibedakan di UI. | `AnomalyRuleConfig` id 1 |
| Q5 | Batas severity hanya menghitung jumlah flag, tidak memperhitungkan besar kerugian. Re-Heating selalu HIGH meski kerugiannya kecil atau sangat besar. | detect_anomalies.py L59 |
| Q6 | Ambang tetap di kode (8 mnt, 45 mnt, 15 mnt, 1,4×) tidak bisa dikonfigurasi. `AnomalyRuleConfig` hanya mendukung satu `rule_type` (`THRESHOLD_DIFF`). | api_report.py L2103-2240 |
| Q7 | Dua jalur penghitungan (`api_report.py` dan `detect_anomalies.py`) dengan logika berbeda. Hasilnya bisa tidak konsisten (lihat 2.2). | Studi kasus |
| Q8 | Duplikasi kartu: kejadian yang sama muncul sebagai kartu live dan kartu DB. | Studi kasus |

---

## 5. Katalog Deteksi yang Diusulkan

Kolom "Kondisi" mengikuti ambang di report saat ini. Kolom "Rekomendasi ambang" adalah usulan yang perlu divalidasi dengan pemilik proses.

### 5.1 Deteksi yang sudah ada di report, perlu dipersistenkan

| Kode flag | Kategori | Kondisi saat ini | Frekuensi 30 hari | Rekomendasi |
|---|---|---|---|---|
| `REHEATING` | Interupsi proses | ≥ 2 siklus naik, valley masih > 70°C | 33 (14 hari) | Pertahankan. Kecualikan mesin `Temp_*`. Severity berdasar `reheat_extra_mins`. |
| `OVER_HOLD` | Operasional | hold − ideal > 8 mnt | 264 | WARNING > 8, CRITICAL > 25 (pertahankan). |
| `LATE_STOP` | Operasional | < 70°C sampai OFF > 45 mnt | 491 | Terlalu sering (30%). Usul WARNING > 60, CRITICAL > 90. Validasi dulu. |
| `COOL_STAGNATION` | Operasional | stagnan ≥ 15 mnt di ≥ 70°C | belum diukur | Pertahankan, butuh log. |
| `SLOW_COOL` | Mesin / HE | cool > ideal + 15 mnt dan > 1,4× ideal | **931 (57%)** | **Kalibrasi ulang.** Bandingkan dengan histori mesin-program, bukan ideal resep saja. |
| `MID_HEAT_PAUSE` | Kurva | span − heating > 10 mnt | belum diukur | Bedakan dari dosing bertahap resep. |
| `START_TEMP_HIGH` | Prosedur | suhu awal > 60°C | 34 (0 terdaftar) | Pertahankan sebagai WARNING. |

### 5.2 Deteksi baru yang disarankan

| Kode flag | Kondisi | Alasan | Frekuensi 30 hari |
|---|---|---|---|
| `SHORT_HOLD` | hold < 50% ideal | Risiko kualitas warna (under-processing). Bahaya kualitas, bukan hanya efisiensi. | 23 |
| `UNDERSHOOT_TEMP` | peak < suhu program − 10°C | Proses tidak mencapai suhu target. | 23 |
| `NO_COOL_TO_70` | `reached_70c_time` kosong | Siklus tidak selesai normal. | 12 |
| `DURATION_OUTLIER` | durasi efektif > 600 mnt (atau > P99 mesin-program) | Batch ekstrem. | 24 |
| `UNLINKED_BATCH` | batch valid tanpa identity > N jam setelah selesai | Menutup lubang P1. Sasaran: operator melengkapi identity. | 353 |
| `NO_MASTER` | identity + program ada tapi master belum ada | Menutup lubang P2 dan memicu kalibrasi. | 138 |
| `LOW_STEAM_DURING_HEAT` | tekanan uap < ambang selama sebagian besar heating | Memisahkan penyebab suplai dari penyebab mesin. | belum diukur |

### 5.3 Perbaikan model data

- Pisahkan `anomaly_type` (kategori) dari `flags` (daftar kode). Kategori usulan: `PROCESS_DEVIATION`, `INTERRUPTION`, `OPERATIONAL`, `EQUIPMENT`, `LINKAGE`, `DATA_QUALITY`.
- Izinkan `identity_record` bernilai null supaya batch tanpa identity bisa terdaftar (kategori `LINKAGE`).
- Satu sumber kebenaran untuk detektor. Jadikan modul bersama yang dipakai `api_report.py` dan `detect_anomalies.py`. Report cukup **membaca** hasil tersimpan plus penjelasan.
- Simpan `rule_version` dan `evidence` (jam, suhu, durasi) di `details` supaya hasil bisa direproduksi.

---

## 6. Rekomendasi dan Roadmap

### Fase 1 (cepat, dampak besar)
1. Perbaiki `loop_anomalies.bat` menjadi loop sungguhan, atau pindahkan ke Windows Task Scheduler (misal tiap 15 menit, `--days 3`).
2. Ganti `except: pass` di signal dengan `logger.exception(...)`.
3. Tambah trigger saat `DyeingProcess` berubah ke `is_complete=True`.
4. Kecualikan mesin utilitas `Temp_*` dari deteksi.
5. Jalankan backfill `detect_anomalies --days 30` untuk menutup 16 batch Re-Heating yang terlewat.

### Fase 2 (persistensi deteksi report)
6. Buat modul detektor bersama dan simpan `OVER_HOLD`, `LATE_STOP`, `COOL_STAGNATION`, `MID_HEAT_PAUSE`, `START_TEMP_HIGH` ke `DataAnomaly`.
7. Pisahkan `anomaly_type` dari `flags`. Hentikan label `WRONG_LINK` untuk kasus non-link.
8. Hapus duplikasi kartu di Process Report (satu kejadian = satu kartu).
9. Samakan metrik heating (`real_heating_duration`) di semua jalur.

### Fase 3 (kalibrasi dan cakupan)
10. Kalibrasi ulang `SLOW_COOL` dan `LATE_STOP` dengan data histori mesin-program.
11. Tambah deteksi baru (5.2) dan jadikan ambang bisa dikonfigurasi lewat `AnomalyRuleConfig`.
12. Pertimbangkan master dengan sampel kecil: pakai fallback ke level grup mesin atau program saja bila sampel < 10.
13. Aktifkan alur proposal kalibrasi mingguan (`calibrate_anomalies`). Saat ini 0 proposal.

### Fase 4 (alur kerja)
14. Auto-resolve anomali yang sudah tidak terdeteksi pada evaluasi ulang.
15. Notifikasi untuk CRITICAL baru. Peninjauan anomali berumur > 7 hari (72 saat ini).
16. Perbaiki bug UI `/anomalies` yang sudah tercatat di [implementation_plan.md](file:///C:/Users/HP/.gemini/antigravity/brain/9adb78d4-e36a-4f1f-81ee-efce64c4e933/implementation_plan.md).

---

## 7. Batasan Analisis

- Scan 30 hari memakai ambang yang sama dengan kode report. Frekuensi di tabel 3.2 adalah jumlah yang memenuhi kondisi, bukan jumlah anomali yang benar-benar bermasalah. Validasi ke tim produksi tetap diperlukan.
- `COOL_STAGNATION` dan `MID_HEAT_PAUSE` berbasis log menit tidak dipindai massal, jadi frekuensinya belum diketahui.
- Penyebab pasti 16 batch terlewat belum bisa dipastikan antara (a) exception yang tertelan, (b) evaluasi dijalankan sebelum metrik final, atau (c) jalur link yang tidak memicu signal. Untuk memastikannya, diperlukan logging (Fase 1 langkah 2).
- Bagian "Diagnosis heating kemungkinan keliru" di 2.2 adalah analisis dari angka. Konfirmasi ke tim mesin bila perlu.
