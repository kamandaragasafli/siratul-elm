@echo off
cd /d "%~dp0"
echo.
echo [1/2] Kohne serverleri dayandirir...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
echo [2/2] Backend baslayir: 0.0.0.0:8000
echo Telefon testi: http://192.168.0.178:8000/api/health/
echo Firewall bloklayirsa allow_firewall.bat-i ADMIN kimi isledin.
echo.
py manage.py runserver 0.0.0.0:8000
