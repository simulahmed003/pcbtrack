@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.8+ required. Install from python.org and tick "Add to PATH". & pause & exit /b 1)
python -m pcbtrack doctor
set "S=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%S%\pcbtrack.bat" echo @echo off
>> "%S%\pcbtrack.bat" echo cd /d "%~dp0"
>> "%S%\pcbtrack.bat" echo start "" /min pythonw -m pcbtrack track
echo.
echo Installed. pcbtrack will start when you log in.
echo Starting it now...
start "" /min pythonw -m pcbtrack track
echo Open dashboard.bat to see your day.
pause
