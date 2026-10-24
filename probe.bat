@echo off
rem Record what Altium's windows expose (for diagnosing detection). Switch documents while it runs.
cd /d "%~dp0"
python -m pcbtrack probe
pause
