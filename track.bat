@echo off
rem Start tracking in the background (no window). Only one copy can run.
cd /d "%~dp0"
start "" /min pythonw -m pcbtrack track
echo pcbtrack is tracking in the background.
