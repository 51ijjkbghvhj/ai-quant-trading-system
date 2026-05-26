"""Event-Driven AI Trading System v3.0 Entry Point"""
import sys
import os

# ★ 强制关闭Python输出缓冲，确保日志实时显示
os.environ['PYTHONUNBUFFERED'] = '1'

# Windows控制台UTF-8编码支持 + 行缓冲
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

WORKSPACE = r"C:\Users\Administrator\Desktop\OH-WorkSpace"
sys.path.insert(0, WORKSPACE)
sys.path.insert(0, os.path.join(WORKSPACE, "ai-trader"))
os.chdir(os.path.join(WORKSPACE, "ai-trader"))

from v3.event_bus import run_cycle, main_loop, run_manual_analysis, set_mode

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "once":
            set_mode("AUTO")
            run_cycle()
        elif arg == "manual":
            stock = sys.argv[2] if len(sys.argv) > 2 else None
            set_mode("MANUAL")
            run_manual_analysis(stock)
        elif arg == "auto":
            set_mode("AUTO")
            main_loop(poll_interval=10)
        else:
            print(f"Usage: python v3_main.py [once|manual|auto] [stock_symbol]")
    else:
        set_mode("AUTO")
        main_loop(poll_interval=10)
