"""
scan_connections.py — IP Scanner untuk Plant Monitor
Jalankan: py scan_connections.py
Lihat siapa saja yang sedang mengakses server (bot atau manusia)
"""

import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import subprocess
import requests
import time
import sys
from collections import Counter

# ============================================================
# Daftar tanda-tanda BOT (berdasarkan ISP/org name)
# ============================================================
BOT_ORG_KEYWORDS = [
    "cloud", "hosting", "datacenter", "data center", "server", "vps",
    "amazon", "google", "microsoft", "alibaba", "digitalocean", "linode",
    "vultr", "ovh", "hetzner", "contabo", "online sas", "scaleway",
    "cogent", "cloudflare", "tencent", "baidu", "shodan", "censys",
    "internet measurement", "research", "scanning", "security",
    "colocation", "colo", "cdn", "anycast", "backbone", "transit",
    "autonomous", "botnet",
]

# ISP Indonesia yang dikenal (kemungkinan pengguna nyata)
KNOWN_ID_ISP = [
    "telkom", "indihome", "xl axiata", "xl broadband", "indosat",
    "matrix", "biznet", "mnc", "myrepublic", "firstmedia", "iconplus",
    "linknet", "hutchison", "smartfren", "cbpns", "pt. telekomunikasi",
    "pt telekomunikasi",
]


def get_connections():
    """Ambil semua IP ESTABLISHED di port 8000 dari netstat"""
    result = subprocess.run(
        ["netstat", "-an"],
        capture_output=True, text=True
    )
    ips = []
    for line in result.stdout.splitlines():
        if ":8000" in line and "ESTABLISHED" in line:
            parts = line.split()
            if len(parts) >= 3:
                remote = parts[2]  # kolom remote address
                ip = remote.rsplit(":", 1)[0]
                if ip not in ("127.0.0.1", "0.0.0.0", "", "::1"):
                    ips.append(ip)
    return list(set(ips))


def lookup_ip(ip):
    """Lookup informasi IP via ip-api.com (gratis, tanpa API key)"""
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,isp,org,as",
            timeout=5
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def classify(info):
    """Tentukan apakah kemungkinan BOT atau MANUSIA"""
    if not info or info.get("status") != "success":
        return "❓ UNKNOWN"

    country_code = info.get("countryCode", "")
    isp = (info.get("isp", "") + " " + info.get("org", "")).lower()
    as_name = info.get("as", "").lower()

    combined = isp + " " + as_name

    # Cek apakah dari Indonesia
    is_indonesia = country_code == "ID"

    # Cek apakah ISP dikenal sebagai pengguna nyata Indonesia
    is_known_user_isp = any(k in combined for k in KNOWN_ID_ISP)

    # Cek tanda-tanda bot/cloud/datacenter
    is_bot_org = any(k in combined for k in BOT_ORG_KEYWORDS)

    if is_indonesia and is_known_user_isp and not is_bot_org:
        return "[OK]  MANUSIA (ID)"
    elif is_indonesia and is_bot_org:
        return "[!!]  BOT/Cloud (ID)"
    elif is_bot_org:
        return "[BOT] Scanner/Cloud"
    elif is_indonesia:
        return "[ID?] Indonesia - cek manual"
    else:
        return "[BOT] Asing"


def main():
    print("=" * 72)
    print("  PLANT MONITOR — IP CONNECTION SCANNER")
    print(f"  Waktu scan: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)
    print("Mengambil daftar koneksi dari netstat...")

    ips = get_connections()
    total = len(ips)

    if total == 0:
        print("\n✅ Tidak ada koneksi eksternal ESTABLISHED ke port 8000.")
        return

    print(f"Ditemukan {total} IP unik. Melakukan lookup (maks 45 IP/menit)...\n")
    print(f"{'NO':<4} {'IP':<22} {'NEGARA':<20} {'ISP/ORG':<30} {'STATUS'}")
    print("-" * 100)

    results = []
    countries = Counter()

    for i, ip in enumerate(ips, 1):
        info = lookup_ip(ip)

        country = f"{info.get('country', '?')} ({info.get('countryCode', '?')})" if info else "?"
        isp = (info.get("org") or info.get("isp") or "?")[:30]
        status = classify(info)

        countries[info.get("countryCode", "?")] += 1
        results.append((ip, country, isp, status))

        print(f"{i:<4} {ip:<22} {country:<20} {isp:<30} {status}")

        # Rate limit: ip-api.com max 45 request/menit (gratis)
        if i % 44 == 0 and i < total:
            print(f"\n[WAIT] Menunggu 60 detik (rate limit API)...\n")
            time.sleep(60)
        else:
            time.sleep(1.4)  # ~43 req/menit agar aman

    # Ringkasan
    print("\n" + "=" * 72)
    print("  RINGKASAN")
    print("=" * 72)

    bots    = sum(1 for _, _, _, s in results if "BOT" in s or "Asing" in s)
    humans  = sum(1 for _, _, _, s in results if "MANUSIA" in s)
    unknown = sum(1 for _, _, _, s in results if "UNKNOWN" in s or "cek" in s.lower())

    print(f"  Total IP unik    : {total}")
    print(f"  [OK]  Manusia ID : {humans}")
    print(f"  [BOT] Bot/Scanner: {bots}")
    print(f"  [?]   Perlu dicek: {unknown}")
    print()
    print("  Top Negara:")
    for code, count in countries.most_common(10):
        print(f"    {code:<6} : {count} koneksi")
    print("=" * 72)

    # Simpan hasil ke file
    output_file = "ip_scan_result.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Scan: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"{'IP':<22} {'NEGARA':<20} {'ISP/ORG':<35} STATUS\n")
        f.write("-" * 90 + "\n")
        for ip, country, isp, status in results:
            f.write(f"{ip:<22} {country:<20} {isp:<35} {status}\n")
        f.write(f"\nTotal: {total} | Manusia: {humans} | Bot: {bots} | Unknown: {unknown}\n")

    print(f"\nHasil disimpan ke: {output_file}")


if __name__ == "__main__":
    main()
