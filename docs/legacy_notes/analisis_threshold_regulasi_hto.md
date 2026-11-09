# Analisis Korelasi Speed R. Bakar vs Oil Temp & Penentuan Threshold Regulasi HTO

Dokumen ini berisi hasil analisis data empiris dari database PostgreSQL (`MachineMinuteLog`) selama **30 hari terakhir** (rentang pertengahan Agustus hingga pertengahan September 2026) untuk memetakan perilaku kerja Thermal Oil Heater (HTO) dan menentukan nilai batas (*threshold*) yang paling akurat untuk mendeteksi kejadian regulasi.

---

## 1. Karakteristik Operasional HTO (Data 30 Hari)

Berdasarkan ekstraksi data log per menit pada sensor `Oil_Temp` (Temperatur Oli HTO) dan `Speed_R_Bakar` (Inverter Feeder Bahan Bakar HTO):

### A. Kondisi Saat Boiler Beroperasi Aktif (`Oil_Temp > 100°C`)
* **Total Data:** 17.517 menit (~292 jam kerja aktif)
* **Speed R. Bakar Normal:** Berada di rentang **13,0 Hz s/d 16,5 Hz** (rata-rata: **14,46 Hz**, median: **14,14 Hz**).
* **Suhu Oli Operasional Normal (`Oil_Temp`):**
  * Kuartil Bawah (Q1 / 25%): **238,11 °C**
  * Rata-rata: **237,29 °C**
  * Median (Q2 / 50%): **240,54 °C**
  * Kuartil Atas (Q3 / 75%): **242,68 °C**
  * Suhu Maksimum: **249,65 °C**

---

## 2. Pemetaan Pola Drop Speed (`Speed_R_Bakar <= 0.5 Hz`)

Dari 30 hari data, ditemukan **359 kali blok waktu** di mana speed feeder HTO drop ke $\le 0.5$ Hz (mendekati 0 Hz). Dari 359 blok tersebut, data terbagi menjadi **2 kategori yang sangat kontras**:

### Kategori A: Shutdown / Maintenance / Hari Libur Pabrik (27 Kejadian)
* **Durasi:** Berlangsung lama (**10 menit hingga 40 jam** berturut-turut).
* **Suhu Oli:** Drop drastis di bawah suhu kerja normal (Peak suhu hanya berkisar antara **67 °C s/d 188 °C**, dengan rata-rata suhu ~85 °C).
* **Kesimpulan:** Ini adalah kondisi mesin mati/istirahat, **bukan regulasi**.

### Kategori B: Kejadian Regulasi Operasional Murni (332 Kejadian)
* **Pola Kejadian:** Feeder sedang menyala stabil di ~14 Hz, lalu tiba-tiba **cut-off ke 0 Hz selama beberapa menit**, kemudian menyala kembali ke ~14 Hz.
* **Durasi Regulasi:** Sangat konsisten dan singkat, berkisar antara **1 s/d 6 menit** (rata-rata **2,89 menit**, median **3 menit**).
* **Korelasi Suhu Oli Saat Regulasi Terjadi:**
  * **Suhu Minimum saat Regulasi Terpicu:** **242,18 °C**
  * **25% Kejadian:** $\ge 244,87 \text{ }^\circ\text{C}$
  * **Median (50% Kejadian):** $\ge 245,94 \text{ }^\circ\text{C}$
  * **75% Kejadian:** $\ge 247,35 \text{ }^\circ\text{C}$
  * **Suhu Puncak Tertinggi:** **254,49 °C**
  * **Rata-rata Suhu Puncak:** **246,15 °C**

> **Mekanisme Lapangan Terbukti:**
> Ketika suhu sirkulasi oli mencapai **$\ge 242\text{--}246\text{ }^\circ\text{C}$**, controller burner HTO otomatis memutus feeder (`Speed_R_Bakar` $\rightarrow$ 0 Hz) untuk mencegah *overheating* oli termal. Dalam waktu 2–4 menit sirkulasi tanpa pembakaran, suhu oli turun sekitar 3–5 °C (ke level ~239–241 °C). Begitu suhu turun ke level tersebut, feeder otomatis menyala kembali.

---

## 3. Evaluasi Sensitivitas Pemilihan Threshold (`boiler_regulation_hto_oil_temp_min`)

Dilakukan uji simulasi terhadap berbagai opsi batas suhu puncak (*peak temperature*) dengan aturan:
*Speed drop $\le 0.5\text{ Hz}$ dengan suhu oli di window kejadian $\ge \text{Threshold}$*:

| Opsi Threshold | Regulasi Terdeteksi (Durasi $\le 15$ mnt) | False Positive (Shutdown Ikut Terhitung) | False Negative (Regulasi Nyata yang Terlewat) | Analisis |
| :---: | :---: | :---: | :---: | :--- |
| **200,0 °C** | 332 event | 0 | 0 | Terlalu longgar / jauh di bawah setpoint kontrol HTO pabrik |
| **235,0 °C** | 332 event | 0 | 0 | Kurang ideal karena beririsan dengan batas Alert Kritis HTO Low (235 °C) |
| **240,0 °C** | **332 event (100%)** | **0 (0%)** | **0 (0%)** | ⭐ **Sangat Aman & Presisi** (Toleran terhadap variasi beban) |
| **242,0 °C** | **332 event (100%)** | **0 (0%)** | **0 (0%)** | ⭐ **Paling Akurat** (Tepat di titik minimum terpicunya regulasi) |
| **244,0 °C** | 286 event | 0 | 46 event (13,8%) | Terlalu ketat; 46 kejadian regulasi nyata tidak terdeteksi |
| **245,0 °C** | 240 event | 0 | 92 event (27,7%) | Terlalu ketat; hampir sepertiga kejadian regulasi terlewat |

---

## 4. Kesimpulan & Rekomendasi Pemasangan Threshold

1. **Nilai Threshold Terbaik:**
   * Rekomendasi utama: **`242.0 °C`** (atau **`240.0 °C`** untuk batas toleransi lebih longgar).
   * Nilai ini menjamin **100% kejadian regulasi terdeteksi (332 kejadian)** tanpa satu pun *false positive* dari mesin shutdown/mati, dan tanpa ada *false negative*.

2. **Definisi Aturan Deteksi HTO yang Diusulkan:**
   * **`Speed_R_Bakar <= 0.5 Hz`**
   * **`Oil_Temp >= 242.0 °C`** (diperiksa dalam rentang $\pm 2$ menit sebelum atau selama speed 0 Hz)
   * **`Gap Tolerance: 1 menit`** (mengabaikan lonjakan sesaat $\le 1$ menit agar kejadian yang bersambung tidak terpecah)
   * **`Durasi Maksimal Regulasi: 15 menit`** (kejadian 0 Hz di atas 15 menit diklasifikasikan sebagai *Shutdown/Stop Produksi*, bukan regulasi intermiten).
