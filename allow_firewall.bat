@echo off
:: Sağ klik -> Run as administrator
netsh advfirewall firewall delete rule name="Sirac Django 8000" >nul 2>&1
netsh advfirewall firewall add rule name="Sirac Django 8000" dir=in action=allow protocol=TCP localport=8000
if %errorlevel%==0 (
  echo OK — port 8000 telefon ucun acildi.
) else (
  echo Xeta — bu fayli "Run as administrator" ile acin.
)
pause
