# Implementation Plan: Crosshair Panel + Steam Pressure Row

> Tanggal: 21 Agustus 2026  
> Target file utama: `monitoring/api_snapshots.py`, `frontend/src/pages/SnapshotHistoryPivot.jsx`, komponen baru

---

## Daftar Fitur

| # | Fitur | Kompleksitas |
|---|---|---|
| 1 | **Crosshair Tooltip Panel** — jumlah mesin per state + uap + tekanan saat hover | Medium |
| 2 | **Steam Pressure Row** — mini chart `Steam_Pr` (barg) di bawah baris uap, sticky + print | Medium |

---

## Fitur 1 — Crosshair Tooltip Panel

### 1.1 Tujuan & Perilaku

Saat cursor melintas di atas baris manapun, sebuah panel kecil muncul di dekat crosshair yang menampilkan:

- **Jam** di menit yang sedang di-hover (misal `22:01`)
- **Jumlah mesin** per state: Heating, Keeping, Cooling, Running; plus **Lain** (gabungan Off/Offline/Fault/NoSignal/Error) jika count > 0
- **Uap total** (kg/h) pada menit tersebut dari `steam_heatmap.values`
- **Tekanan uap** (barg) pada menit tersebut dari `steam_pressure.values` *(data baru dari backend)*

### 1.2 Desain Visual (UI/UX) — Minimalis

Satu baris ringkas per informasi, tanpa dekorasi berlebih. Prioritas: padat, cepat dibaca, hemat ruang.

```
┌───────────────────────────┐
│ 22:01                     │  ← jam hover, bold, 12px
│ ─────────────────────────│
│ ● 3   ● 5   ● 2   ● 1     │  ← dot warna + angka, sejajar horizontal
│ Heat Keep Cool  Run       │  ← label super kecil (8px) di bawah tiap dot
│ ─────────────────────────│
│ Uap      6.240 kg/h       │
│ Tekanan  4.2 barg         │  ← warna teks berubah sesuai status
└───────────────────────────┘
```

Ringkasan (baris demi baris):
1. **Jam** — satu baris, bold
2. **Jumlah mesin per state** — horizontal: dot kecil + angka; label state di bawah (8px). State dengan `count = 0` **disembunyikan**. Dot "Lain" hanya muncul jika count > 0.
3. **Uap & Tekanan** — dua baris teks `label` + `nilai` (flex justify-between). Tidak ada mini gauge. Indikator tekanan = warna teks saja.

**Posisi panel:**
- Default: muncul di atas cursor, rata kiri
- Jika mendekati tepi kanan (<180px): flip ke kiri cursor
- Jika mendekati tepi atas (<70px): muncul di bawah cursor
- `z-index` tinggi (z-50), `pointer-events-none`
- Tanpa animasi — langsung tampil/hilang

**Background/style (compact):**
- Latar: `bg-gray-900/95`
- Padding: `px-2.5 py-2`
- Teks utama: `text-white text-xs`
- Teks sekunder/label: `text-gray-400 text-[9px]`
- Radius: `rounded-md`
- Shadow: `shadow-lg`
- Lebar: `auto`

**Warna state:** import dari `PHASE_COLORS` (hex resmi aplikasi), jangan hardcode.

**Warna indikator tekanan (teks saja):**
| Range | Warna teks | Makna |
|---|---|---|
| < 3 barg | `text-red-400` | Kritis |
| 3 – 4.5 barg | `text-amber-400` | Rendah |
| 4.5 – 6 barg | `text-emerald-400` | Normal |
| > 6 barg | `text-purple-400` | Over-pressure |

### 1.3 Sumber Data

| Data | Sumber | Perlu Perubahan? |
|---|---|---|
| Jam hover | `hover.timeLabel` (sudah ada) | ❌ Tidak |
| Jumlah mesin per state | Hitung dari `data.groups[].machines[].segments` | ❌ Tidak (frontend-only) |
| Uap (kg/h) | `data.steam_heatmap.values[bucketIndex]` | ❌ Tidak |
| Tekanan (barg) | `data.steam_pressure.values[bucketIndex]` | ✅ **Backend baru** |

### 1.4 Algoritma Hitung State di Minute N (Frontend)

```js
const bucketIndex = Math.floor((hover.pct / 100) * SHIFT_MINUTES);

const counts = { HEAT: 0, STEADY: 0, COOL: 0, RUNNING: 0, other: 0 };
for (const group of data.groups) {
  for (const machine of group.machines) {
    const state = getStateAtBucket(machine.segments, bucketIndex);
    if (state === 'HEAT') counts.HEAT++;
    else if (state === 'STEADY') counts.STEADY++;
    else if (state === 'COOL') counts.COOL++;
    else if (state === 'RUNNING') counts.RUNNING++;
    else counts.other++;
  }
}

function getStateAtBucket(segments, bucketIndex) {
  const pct = (bucketIndex / 1440) * 100;
  for (const seg of segments) {
    if (pct >= seg.start_pct && pct < seg.start_pct + seg.width_pct) {
      return seg.state;
    }
  }
  return 'OFF';
}
```

> Hitung di `useMemo` dengan dependency `[hover?.pct, data]`.

### 1.5 Perubahan Backend (tekanan)

Kode mesin sensor tekanan yang benar di seluruh codebase: **`Steam_Pr`** (bukan `Temp_RB_Steam`). Nilai tekanan disimpan di field `temperature` pada `MachineMinuteLog`.

```python
steam_pr_machine = Machine.objects.filter(code='Steam_Pr', is_active=True).first()
pressure_buckets = {}

if steam_pr_machine:
    pr_logs = MachineMinuteLog.objects.filter(
        machine=steam_pr_machine,
        timestamp__gte=shift_start,
        timestamp__lt=shift_end,
    ).order_by('timestamp')

    for log in pr_logs:
        time_diff = (timezone.localtime(log.timestamp) - shift_start).total_seconds() / 60
        bucket_index = int(time_diff)
        if 0 <= bucket_index <= max_bucket and log.temperature is not None:
            pressure_buckets[bucket_index] = round(float(log.temperature), 2)

pressure_values = [pressure_buckets.get(i) for i in range(_data_end)]
# None = belum ada data (berbeda dari 0.0 yang valid)
```

**Response tambahan:**
```python
"steam_pressure": {
    "values": pressure_values,   # list[float | None]
    "unit": "barg",
    "scale_min": 0,
    "scale_max": 6,
    "critical_low": 3.0,
},
```

Kueri **terlepas dari filter group/machine** — tekanan adalah data global shift.

---

## Fitur 2 — Steam Pressure Mini Chart Row

### 2.1 Tujuan & Perilaku

Baris sticky di bawah baris uap menampilkan tekanan uap (`Steam_Pr`):
- Skala tetap: **0 – 6 barg**
- Garis pembatas horizontal setiap **2 barg**
- Garis kritis **3 barg** (dashed, merah tipis)
- Termasuk **print** di `thead` setiap halaman

### 2.2 Desain Visual

```
┌─────────┬───────────────────────────────────────────────────────────┐
│  Prss   │ ──────────────────────────── 6 barg ───────────────────── │
│  (barg) │ ──────────────────────────── 4 barg ───────────────────── │
│         │ · · · · · · · · · · · · · ·  3 barg (kritis) · · · · · · │
│         │ ──────────────────────────── 2 barg ───────────────────── │
│         │ ████████████████████████····  (bar per menit) ··········· │
└─────────┴───────────────────────────────────────────────────────────┘
```

**Detail visual:**
- Tinggi baris: 28px layar (`h-7`), 20px print
- Warna bar per nilai (bukan gradient posisi Y):
  - < 3 barg: `#ef4444`
  - 3–4.5 barg: `#f59e0b`
  - ≥ 4.5 barg: `#10b981`
- Background: `#fafafa`
- Grid tiap 2 barg: `rgba(0,0,0,0.08)`
- Garis 3 barg: `rgba(239,68,68,0.35)` dashed
- Future / None: abu `#e5e7eb` / kosong
- Garis sekarang (cyan): seperti baris lain

**Rendering:** `<canvas>` (pola sama dengan `SteamHeatmap.jsx`) — 1 piksel per menit, warna dari nilai aktual. Grid overlay via SVG/CSS absolute lines. Hindari SVG `<path>` + `linearGradient` (warna tidak map ke skala barg tetap; sulit handle `None`).

### 2.3 Posisi Sticky

Struktur tinggi aktual:
| Baris | Sticky top | Tinggi |
|---|---|---|
| Header MESIN + Time Axis | `top-0` | `h-8` = 32px |
| Steam Heatmap | `top-8` (32px) | `h-6` = 24px |
| Steam Pressure ← BARU | `top-14` (56px) | `h-7` = 28px |
| Sticky grup mesin | `top-[84px]` (56+28) | — |

```
STICKY_GROUP_TOP = 'top-[84px]'  // sebelumnya top-14
```

### 2.4 Print Support

Pressure row masuk `thead` agar berulang tiap halaman cetak. Label kolom kiri: `"Prss"` / `"barg"`.

---

## Ringkasan Perubahan File

| File | Perubahan |
|---|---|
| `monitoring/api_snapshots.py` | Kueri `Steam_Pr` → field `steam_pressure` di `/timeline` |
| `frontend/src/pages/SnapshotHistoryPivot.jsx` | `hoverStats`, CrosshairPanel, SteamPressureRow, sticky |
| `frontend/src/components/SteamPressureRow.jsx` | **Baru** — canvas mini chart |
| `frontend/src/components/CrosshairPanel.jsx` | **Baru** — tooltip minimalis |

---

## Urutan Implementasi

```
Step 1 — Backend steam_pressure
Step 2 — SteamPressureRow (canvas) + sticky di SnapshotHistoryPivot
Step 3 — CrosshairPanel + getStateAtBucket + hoverStats
Step 4 — Print + polish
```

---

## Risiko & Catatan

| Risiko | Mitigasi |
|---|---|
| Filter group menyembunyikan Steam_Pr | Kueri pressure **terpisah**, selalu global |
| Panel terpotong fullscreen | Boundary dari `overlayRef` / `panelRef` |
| Mouse move berat | `useMemo` + bucket index integer |
| None pressure | Tampilkan `—` di panel; kosong di chart |

---

## Contoh Response API

```json
{
  "steam_heatmap": { "...": "..." },
  "steam_pressure": {
    "values": [4.2, 4.1, 4.3, null, 4.5],
    "unit": "barg",
    "scale_min": 0,
    "scale_max": 6,
    "critical_low": 3.0
  },
  "groups": []
}
```

---

## Riwayat Perubahan Dokumen

| Tanggal | Bagian | Perubahan |
|---|---|---|
| 21 Agu 2026 | §1.2 | Tooltip minimalis: tanpa mini gauge/animasi; state horizontal |
| 21 Agu 2026 | §1.1 / §1.2 | "Lain" = agregat Off/dll, hanya tampil jika count > 0 |
| 21 Agu 2026 | §1.5 | Kode mesin = `Steam_Pr` (bukan Temp_RB_Steam); field temperature terverifikasi |
| 21 Agu 2026 | §2.2 | Rendering canvas (bukan SVG path + gradient) |
| 21 Agu 2026 | §2.3 | Sticky: Pressure `top-14`, grup `top-[84px]` |
| 21 Agu 2026 | §1.2 | Warna state dari `PHASE_COLORS` |

---

*Plan siap dieksekusi.*
