@echo off
title Plant Monitor - Anomaly Detection Loop
echo [Anomaly Detection Daemon] Memulai loop deteksi anomali...

cd /d "%~dp0..\.."

:loop
echo [%date% %time%] Menjalankan detect_anomalies (rentang 3 hari terakhir)...
"venv\Scripts\python.exe" manage.py detect_anomalies --days 3
echo [%date% %time%] Istirahat 60 detik...
timeout /t 60 /nobreak >nul
goto loop
