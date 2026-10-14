@echo off
cd /d "%~dp0"
py -3 share_app.py
if errorlevel 1 pause
