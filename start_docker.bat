@echo off
echo ===================================================
echo Starting Plant Monitor (Docker + Nginx + Redis)
echo ===================================================
echo.

cd /d "%~dp0"

echo [1/3] Mengumpulkan file statis (jika ada perubahan)...
call venv\Scripts\activate
python manage.py collectstatic --noinput
echo.

echo [2/3] Membangun dan menjalankan kontainer Docker...
docker compose up -d --build
echo.

echo [3/3] Server berjalan!
echo Akses lokal: http://localhost:8000
echo Akses DevTunnel: (Sesuai URL DevTunnel Anda)
echo.
echo Untuk melihat log, gunakan perintah: docker compose logs -f
echo Untuk mematikan server, gunakan: docker compose down
echo.
pause
