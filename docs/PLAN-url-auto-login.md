# Plan: Auto-login via URL path (port 8000)

Opsi login tambahan agar aplikasi lain bisa mengarahkan browser user yang sudah login ke Energiku tanpa mengisi form lagi.

Form login existing di `/login/` tetap ada. Keamanan URL (password di path) sengaja diabaikan karena pemakaian internal; fokus pada alur fungsional.

## Keputusan yang dikunci

- Path: `http://<host>:8000/login/{username}/{password}/`
- Form login `/login/` tidak diganti
- Setelah sukses: redirect ke dashboard Django SSR (`/`), boleh di-override dengan `?next=/path-internal`
- Umur cookie `sessionid`: **48 jam** (`SESSION_COOKIE_AGE = 172800`)
- Endpoint hanya memverifikasi kredensial terhadap tabel `auth_user` Energiku (Django User)
- Sinkronisasi database user aplikasi lain **di luar scope** — username dan password harus sudah sama di kedua sisi

## Cara kerja

Energiku memakai Django session cookie (bukan JWT). Login sukses = `authenticate()` + `login()` → cookie `sessionid`.

Timer 48 jam dihitung dari saat login (`SESSION_SAVE_EVERY_REQUEST = False`). Perubahan umur session bersifat global: form login, API React, dan auto-login URL.

```
Aplikasi lain  →  Browser GET /login/user/pass/?next=/
               →  Django authenticate
               →  sukses: Set-Cookie sessionid + 302 ke next atau dashboard
               →  gagal: 200 halaman login + pesan error spesifik
```

## Kontrak URL untuk aplikasi lain

Contoh:

```
http://192.168.x.x:8000/login/operator01/rahasia123/?next=/
```

Aturan wajib:

1. **Navigasi top-level di browser** (`window.location`, `<a href>`, HTTP 302). Bukan `curl`, `python-requests`, atau server-to-server. Middleware BotBlocker memblokir User-Agent tersebut dan request tanpa User-Agent.
2. **Jangan iframe.** Django memakai `X-Frame-Options: DENY`.
3. Username dan password **wajib di-URL-encode sekali** (`encodeURIComponent` / equivalent).
4. Trailing slash disarankan. Tanpa slash, Django akan 301 ke versi ber-slash.
5. `next` harus path internal yang diawali `/`. Bukan URL absolut ke host lain.

### Contoh JavaScript (aplikasi lain)

```javascript
const user = encodeURIComponent(loggedInUsername);
const pass = encodeURIComponent(loggedInPassword);
window.location.href =
  `http://HOST_ENERGIKU:8000/login/${user}/${pass}/?next=/`;
```

Contoh dengan halaman tujuan tertentu:

```javascript
window.location.href =
  `http://HOST_ENERGIKU:8000/login/${user}/${pass}/?next=${encodeURIComponent('/grafik/')}`;
```

### Encoding karakter spesial

Encode **sekali**. Jangan double-encode.

| Password asli | Encoded di URL |
| --- | --- |
| `rahasia123` | `rahasia123` |
| `p@ss/w?rd#1` | `p%40ss%2Fw%3Frd%231` |
| spasi | `%20` |
| `+` | `%2B` |
| `%` | `%25` |

Karakter yang merusak path jika tidak di-encode: `/ ? # % & +` dan spasi. Khusus `#` dan `?` **tidak pernah sampai ke server** jika tidak di-encode.

Kedua segmen (username dan password) wajib. `/login/foo/` tanpa password menghasilkan 404.

## Pesan error yang mungkin tampil

Jika auto-login gagal, user tetap melihat form login manual. Session lama (jika ada) tidak di-logout.

| Kondisi | Pesan |
| --- | --- |
| Username tidak ada | Username tidak ditemukan. |
| Password salah | Password salah. |
| Akun `is_active=False` | Akun dinonaktifkan. Hubungi admin. |
| Username/password kosong setelah decode | Username dan password wajib diisi. |
| Exception tak terduga (DB, session, dll.) | Login otomatis gagal. Silakan login manual. |

Perilaku lain (bukan pesan di halaman login):

| Kondisi | Perilaku |
| --- | --- |
| `next` tidak valid (`http://evil`, `//evil`, `\path`, `/login/...`) | Login tetap sukses, `next` diabaikan, redirect ke dashboard |
| `next` ke halaman tanpa permission | Login sukses; halaman tujuan yang menolak (sama seperti ketik URL manual) |
| User belum punya OperatorProfile | Login sukses; akses halaman mengikuti permission yang sudah ada |
| Sudah login sebagai A, buka URL user B | Session diganti ke B |
| Sudah login sebagai A, buka URL user A lagi | Login ulang, redirect, tidak loop |
| Double-encode (`%2540` instead of `%40`) | Password salah |
| BotBlocker / tanpa User-Agent / IP di-blacklist | 400/403; view tidak jalan |
| Session habis setelah 48 jam | User harus login lagi (form atau URL). Bukan sliding expiry |

## Prasyarat data

Auto-login **tidak membaca database aplikasi lain**.

Sebelum uji integrasi, pastikan di Admin Energiku (`/admin/` → Users):

- User sudah ada
- `username` identik (case-sensitive, byte-for-byte)
- `password` identik (di-set lewat Admin / `set_password`, bukan menempel hash mentah dari aplikasi lain)
- `is_active=True`
- Jika butuh akses operator: `OperatorProfile` + `Position.allowed_pages`

Jika password di aplikasi lain di-hash dengan algoritma berbeda, hash itu tidak bisa ditempel ke Django. Yang dikirim di URL adalah password plain, lalu Django memverifikasi terhadap hash-nya sendiri.

## Catatan session 48 jam

- Setting: `SESSION_COOKIE_AGE = 172800` di `plant_monitor/settings.py`
- Berlaku untuk semua cara login
- Session yang sudah aktif sebelum deploy tetap memakai expiry lama sampai user login ulang
