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

# 🆕 路径配置：代码与数据分离
from pathlib import Path
WORKSPACE = str(Path(__file__).resolve().parent.parent)
USER_DATA_DIR = os.path.join(WORKSPACE, "user_data")
os.makedirs(USER_DATA_DIR, exist_ok=True)

sys.path.insert(0, WORKSPACE)
sys.path.insert(0, os.path.join(WORKSPACE, "ai-trader"))
os.chdir(WORKSPACE)  # 保持在项目根目录

# 自动迁移旧数据
import shutil
_FILES_TO_MOVE = ['portfolio.json', 'ai_config.json', 'mimo_debug.log']
for f_name in _FILES_TO_MOVE:
    _old_path = os.path.join(WORKSPACE, "ai-trader", f_name)
    _new_path = os.path.join(USER_DATA_DIR, f_name)
    if not os.path.exists(_new_path) and os.path.exists(_old_path):
        print(f"[System] 🔄 检测到旧版数据，正在迁移 {f_name} 到 /user_data ...")
        shutil.copy2(_old_path, _new_path)

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
