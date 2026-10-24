@echo off
rem Write today's report (md / csv / json) into the reports folder.
cd /d "%~dp0"
python -m pcbtrack report
pause
