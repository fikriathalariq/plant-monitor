@echo off
title Plant Monitor — Stopping All...
color 0C

echo.
echo  ==========================================
echo   Plant Monitor - Mematikan Semua Proses
echo  ==========================================
echo.

cd /d "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"

echo [1/5] Menghentikan Nginx...
"C:\Users\HP\Downloads\nginx-1.28.2\nginx-1.28.2\nginx.exe" -s stop 2>nul
echo        OK.

echo.
echo [2/5] Menghentikan Waitress, JUMO Realtime, Log History, Anomali...
taskkill /F /IM python.exe 2>nul
echo        OK - Semua proses Python dihentikan.

echo.
echo [3/5] Menghentikan Frontend Vite (port 8002)...
taskkill /F /FI "WINDOWTITLE eq Plant Monitor - Frontend*" 2>nul
echo        OK.

echo.
echo [4/5] Menghentikan Engineer Workspace (port 8003)...
taskkill /F /FI "WINDOWTITLE eq Plant Monitor - Engineer Workspace*" 2>nul
echo        OK.

echo.
echo [5/5] Menghentikan sisa proses Node.js (Vite/npm)...
taskkill /F /IM node.exe 2>nul
echo        OK.

echo.
echo  ==========================================
echo   Semua proses Plant Monitor dihentikan.
echo  ==========================================
echo.
echo   Yang dimatikan:
echo     - Nginx
echo     - Waitress / Django (port 8000 gateway & 8004 arsip)
echo     - JUMO Realtime + Log Minute History
echo     - Kalkulasi Anomali (loop)
echo     - Frontend staging (port 8002)
echo     - Engineer Workspace (port 8003)
echo.
echo   PostgreSQL TIDAK dimatikan (database tetap jalan).
echo.
echo  Tekan tombol apapun untuk menutup.
pause >nul
