@echo off
title Push Plant Monitor ke GitHub
cd /d "c:\Users\HP\Documents\Plant-Monitor\plant-monitor"
echo ==========================================================
echo   PUSH PLANT MONITOR KE GITHUB (fikriathalariq/plant-monitor)
echo ==========================================================
echo.
"%LOCALAPPDATA%\Programs\Git\cmd\git.exe" push -u origin main
echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] Push berhasil! Kunjungi repositori Anda di:
    echo      https://github.com/fikriathalariq/plant-monitor
) else (
    echo [INFO] Jika gagal, pastikan Anda telah login akun GitHub di browser.
)
pause
