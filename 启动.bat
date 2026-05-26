@echo off
chcp 65001 >nul
echo AI Trading System - 启动程序
echo 正在检查依赖...
pip install -q -r requirements.txt
echo 正在启动系统...
cd trading-dashboard
python run_all.py
pause
