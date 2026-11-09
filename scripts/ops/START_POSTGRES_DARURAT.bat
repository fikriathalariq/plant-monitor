@echo off
title PostgreSQL Darurat (Tanpa Admin)
echo Menyalakan PostgreSQL tanpa hak Administrator...
"C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\17\data"
echo Database sudah menyala di background! Jendela ini akan tertutup.
timeout /t 3 >nul
