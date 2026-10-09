@echo off
cd /d "%~dp0"
python randomizer.py gui
if errorlevel 1 pause
