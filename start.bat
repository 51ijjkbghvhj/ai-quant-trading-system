@echo off
title AI Trading System
echo.
echo ============================================
echo   AI Trading System
echo   Frontend: http://localhost:8503
echo ============================================
echo.

:: Switch to the dashboard directory relative to this script
cd /d "%~dp0trading-dashboard"

:: Run using python from environment variables
python run_all.py

pause