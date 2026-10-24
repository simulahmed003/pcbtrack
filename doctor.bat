@echo off
rem Check the setup and list anything missing.
cd /d "%~dp0"
python -m pcbtrack doctor
pause
