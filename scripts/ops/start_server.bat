@echo off
echo Starting Plant Monitor Server...
cd /d "%~dp0..\.."
call venv\Scripts\activate
waitress-serve --host=0.0.0.0 --port=8000 plant_monitor.wsgi:application