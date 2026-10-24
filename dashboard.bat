@echo off
rem Open the pcbtrack dashboard in your browser (http://127.0.0.1:8765).
cd /d "%~dp0"
start "" pythonw -m pcbtrack serve
