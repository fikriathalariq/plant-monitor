"""
analyze_bot_log.py - Tampilkan SEMUA isi bot_requests.log secara lengkap
Jalankan: py analyze_bot_log.py
Output disimpan juga ke: bot_requests_full.txt
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
from collections import Counter, defaultdict

LOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_requests.log')
OUT_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_requests_full.txt')

SEP = "=" * 90

def main():
    if not os.path.exists(LOG_FILE):
        print("File bot_requests.log belum ada.")
        print("Pastikan server sudah di-restart dan berjalan beberapa menit.")
        return

    size = os.path.getsize(LOG_FILE)
    print(f"Membaca: {LOG_FILE}  ({size:,} bytes)")

    blocked_reasons = Counter()
    blocked_paths   = Counter()
    allowed_paths   = Counter()
    ip_activity     = defaultdict(lambda: {'allowed': 0, 'blocked': 0})
    ua_counter      = Counter()
    rows            = []
    total = 0

    with open(LOG_FILE, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 7:
                continue
            ts, ip, method, status, note, path, ua = (
                parts[0], parts[1], parts[2],
                parts[3], parts[4], parts[5],
                '|'.join(parts[6:])
            )
            rows.append((ts, ip, method, status, note, path, ua))

            if 'BLOCKED' in status:
                ip_activity[ip]['blocked'] += 1
                blocked_reasons[note] += 1
                blocked_paths[path] += 1
            else:
                ip_activity[ip]['allowed'] += 1
                allowed_paths[path] += 1

            if ua and ua != '-':
                ua_counter[ua[:100]] += 1

    allowed_total = sum(v['allowed'] for v in ip_activity.values())
    blocked_total = sum(v['blocked'] for v in ip_activity.values())

    lines_out = []
    def out(s=''):
        print(s)
        lines_out.append(s)

    # ── HEADER ────────────────────────────────────────────────────────────
    out(SEP)
    out(f"  BOT REQUEST LOG — SEMUA DATA ({total:,} baris)")
    out(SEP)
    out(f"  ALLOWED : {allowed_total:,}   BLOCKED : {blocked_total:,}   IP unik : {len(ip_activity)}")
    out()

    # ── ALASAN BLOKIR (semua) ─────────────────────────────────────────────
    out(SEP)
    out("  ALASAN DIBLOKIR")
    out(SEP)
    label_map = {
        'NO_UA':    'Tanpa User-Agent',
        'BAD_UA':   'User-Agent scanner',
        'BAD_PATH': 'Path illegal',
    }
    for reason, count in blocked_reasons.most_common():
        out(f"  {label_map.get(reason, reason):<30} : {count:,}x")
    out()

    # ── SEMUA PATH DISERANG ───────────────────────────────────────────────
    out(SEP)
    out("  SEMUA PATH YANG DISERANG BOT")
    out(SEP)
    out(f"  {'COUNT':>7}  PATH")
    for path, count in blocked_paths.most_common():
        out(f"  {count:>7}  {path}")
    out()

    # ── SEMUA PATH ALLOWED ────────────────────────────────────────────────
    out(SEP)
    out("  SEMUA PATH YANG BERHASIL LOLOS (ALLOWED)")
    out(SEP)
    out(f"  {'COUNT':>7}  PATH")
    for path, count in allowed_paths.most_common():
        out(f"  {count:>7}  {path}")
    out()

    # ── SEMUA IP ──────────────────────────────────────────────────────────
    out(SEP)
    out("  SEMUA IP — AKTIVITAS LENGKAP")
    out(SEP)
    out(f"  {'IP':<22} {'ALLOWED':>8} {'BLOCKED':>8}  JENIS")
    out(f"  {'-'*22} {'-'*8} {'-'*8}  {'-'*10}")
    for ip, data in sorted(ip_activity.items(), key=lambda x: x[1]['allowed']+x[1]['blocked'], reverse=True):
        kind = '[MANUSIA?]' if data['allowed'] > 0 and data['blocked'] == 0 else \
               '[BOT]     ' if data['blocked'] > 0 and data['allowed'] == 0 else \
               '[CAMPURAN]'
        out(f"  {ip:<22} {data['allowed']:>8} {data['blocked']:>8}  {kind}")
    out()

    # ── SEMUA USER-AGENT ──────────────────────────────────────────────────
    out(SEP)
    out("  SEMUA USER-AGENT")
    out(SEP)
    for ua, count in ua_counter.most_common():
        out(f"  {count:>6}x  {ua}")
    out()

    # ── SEMUA BARIS LOG (RAW) ─────────────────────────────────────────────
    out(SEP)
    out("  SEMUA BARIS REQUEST (RAW) — diurutkan waktu")
    out(SEP)
    out(f"  {'WAKTU':<19}  {'IP':<22}  {'MTD':<6}  {'STATUS':<10}  {'NOTE':<10}  {'PATH':<40}  UA")
    out(f"  {'-'*19}  {'-'*22}  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*40}  {'-'*30}")
    for ts, ip, method, status, note, path, ua in rows:
        out(f"  {ts:<19}  {ip:<22}  {method:<6}  {status:<10}  {note:<10}  {path:<40}  {ua}")
    out()

    # Simpan ke file
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_out))
    print(f"\nDisimpan ke: {OUT_FILE}")

if __name__ == '__main__':
    main()
