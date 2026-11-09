@echo off
REM ============================================
REM Quick Fix for Development Issues
REM ============================================

echo Fixing Plant Monitor Development Issues...
echo.

cd /d "%~dp0..\.."

REM Activate virtual environment
call venv\Scripts\activate

echo [1/4] Installing WhiteNoise (if not installed)...
pip install whitenoise --quiet

echo.
echo [2/4] Clearing corrupted sessions...
python manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete(); print('✓ Sessions cleared')"

echo.
echo [3/4] Clearing cache...
python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('✓ Cache cleared')"

echo.
echo [4/4] Collecting static files (for network access)...
python manage.py collectstatic --noinput

echo.
echo ========================================
echo ✓ All fixes applied!
echo ========================================
echo.
echo Now restart your development server:
echo   python manage.py runserver
echo.
pause
