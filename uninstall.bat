@echo off
rem Stop pcbtrack and remove it from Windows login. Your data is kept.
cd /d "%~dp0"
python -m pcbtrack stop --all
python -m pcbtrack autostart off
echo.
echo pcbtrack stopped and removed from login.
echo Your data is still in %LOCALAPPDATA%\pcbtrack - delete that folder to erase it.
pause
