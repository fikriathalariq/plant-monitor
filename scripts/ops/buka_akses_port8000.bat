@echo off
:: Batch file ini harus dijalankan dengan klik kanan -> "Run as administrator"
echo =======================================================
echo Membuka Akses Port 8000 di Windows Defender Firewall...
echo =======================================================
echo.
netsh advfirewall firewall delete rule name="Block Waitress Direct" >NUL 2>&1
netsh advfirewall firewall add rule name="Nginx Port 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >NUL 2>&1
echo [OK] Firewall rule "Block Waitress Direct" telah dihapus.
echo [OK] Port 8000 sekarang diizinkan (Allow) untuk seluruh LAN.
echo.
pause
