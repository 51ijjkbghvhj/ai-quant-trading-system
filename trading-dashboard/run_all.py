"""AI Trading System - 启动入口"""
import sys, os, socketserver

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "ai-trader"))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import server

if __name__ == "__main__":
    print("\n[System] 正在初始化 AI 交易系统...")
    print()

    # 1. 执行系统健康检查 & 打印 Banner
    try:
        from v3.event_bus import print_system_banner
        print_system_banner()
    except Exception as e:
        print(f"[WARN] Banner 打印失败：{e}")

    # 1.5. 启动时强制同步 T+1 状态 (修复之前“只锁不解”的 Bug)
    print("[System] 正在同步账户状态 (T+1 自动解锁)...")
    server.migrate_portfolio_data()

    # 2. 获取初始前端数据
    print("[System] 加载前端初始数据...")
    server.fetch_initial_data()

    # 3. 启动 Web 服务器
    print("[System] 前端 Web 服务器已就绪。")
    print("    > 访问地址：http://localhost:8503")
    print("    > 按 Ctrl+C 停止运行\n")
    
    try:
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        with socketserver.ThreadingTCPServer(("", 8503), server.H) as s:
            s.serve_forever()
    except OSError as e:
        if "10048" in str(e) or "address" in str(e).lower():
            print("\n[ERROR] 启动失败：端口 8503 被占用！")
            print("原因：你可能已经打开了一个系统窗口，或者旧进程未完全退出。")
            print("解决：请关闭所有黑窗口，等待 1 分钟后重试。")
        else:
            print(f"\n[ERROR] 启动失败: {e}")
    except KeyboardInterrupt:
        print("\n[System] 已停止。")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
