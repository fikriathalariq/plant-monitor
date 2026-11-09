@echo off
title Plant Monitor — Starting Up...
color 0A

echo.
echo  ==========================================
echo   Plant Monitor - Full Startup
echo  ==========================================
echo.

cd /d "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"

REM ── 1. Cek PostgreSQL ──────────────────────────────────────────────────────
echo [1/5] Memeriksa PostgreSQL...
sc query "postgresql-x64-17" | find "RUNNING" >nul
if %errorlevel% NEQ 0 (
    echo        PostgreSQL belum jalan, mencoba menyalakan...
    net start postgresql-x64-17
) else (
    echo        OK - PostgreSQL sudah berjalan.
)

REM ── 2. Mulai Nginx ─────────────────────────────────────────────────────────
echo.
echo [2/5] Menyalakan Nginx (Gateway Web)...
tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I "nginx.exe" >NUL
if %errorlevel% == 0 (
    echo        Nginx sudah berjalan. Reload konfigurasi...
    cd /d "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2"
    nginx.exe -s reload
    cd /d "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
) else (
    cd /d "C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2"
    start "" nginx.exe
    cd /d "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
    echo        OK - Nginx dinyalakan.
)

REM ── 3. Mulai Waitress (Slot Blue 8081) ─────────────────────────────────────
echo.
echo [3/5] Menyalakan Waitress (Slot Blue 8081)...
powershell -Command "Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue" | find "8081" >nul
if %errorlevel% == 0 (
    echo        OK - Waitress Slot Blue (8081) sudah aktif.
) else (
    start "Plant Monitor - Web Server (Blue)" /MIN "C:\Users\HP\Documents\Plant-Monitor\plant-monitor\venv\Scripts\python.exe" run_server.py --port=8081 --slot=blue
    echo        OK - Waitress Slot Blue dinyalakan (minimized).
)

REM ── 4. Mulai Background Workers (Sensor & Telegram) via Singleton Guard ────
echo.
echo [4/5] Memeriksa & Menyalakan Background Workers (Sensor & Telegram)...
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\HP\Documents\Plant-Monitor\plant-monitor\scripts\start_background_workers.ps1"

REM ── 5. Status Akses ────────────────────────────────────────────────────────
echo.
echo [5/5] Frontend React dilayani langsung oleh Nginx (High Performance Static Serving)...
echo        OK - Frontend siap di port 8000, 8002, dan 8003.

echo.
echo  ==========================================
echo   Semua komponen sudah berjalan!
echo  ==========================================
echo.
echo   Akses Utama (React) : http://192.168.11.110:8000 (atau buka :8002)
echo   Django Admin        : http://192.168.11.110:8000/admin
echo   Engineer Workspace: http://localhost:8003/engineer
echo   Arsip Web HTML Lama : http://192.168.11.110:8004
echo.
echo  Tekan tombol apapun untuk menutup jendela ini.
echo  (Semua proses tetap berjalan di background)
pause >nul
