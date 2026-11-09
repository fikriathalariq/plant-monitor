@echo off
cd /d "C:\Users\HP\Documents\Plant-Monitor\plant-monitor"
start "Server" /MIN "C:\Users\HP\Documents\Plant-Monitor\plant-monitor\venv\Scripts\python.exe" run_server.py
start "JUMO" /MIN "C:\Users\HP\Documents\Plant-Monitor\plant-monitor\venv\Scripts\python.exe" manage.py jumo_realtime
start "LogHistory" /MIN "C:\Users\HP\Documents\Plant-Monitor\plant-monitor\venv\Scripts\python.exe" manage.py log_minute_history
