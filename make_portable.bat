@echo off
rem Keep all pcbtrack data in a "data" folder next to the program (e.g. a USB drive).
cd /d "%~dp0"
python -m pcbtrack portable
start "" /min pythonw -m pcbtrack track
echo Tracking restarted in portable mode.
pause
