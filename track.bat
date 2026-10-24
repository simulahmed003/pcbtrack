@echo off
cd /d "%~dp0"
start "" /min pythonw -m pcbtrack track
echo pcbtrack is tracking in the background.
