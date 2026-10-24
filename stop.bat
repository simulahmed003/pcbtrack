@echo off
cd /d "%~dp0"
python -m pcbtrack stop --all
echo Run track.bat (tracking) or dashboard.bat (dashboard) to start again.
pause
