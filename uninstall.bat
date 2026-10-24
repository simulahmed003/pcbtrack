@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\pcbtrack.bat" 2>nul
taskkill /F /IM pythonw.exe 2>nul
echo Startup entry removed. Your data stays in %LOCALAPPDATA%\pcbtrack
pause
