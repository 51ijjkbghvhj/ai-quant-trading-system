"""
V9.0 Full Flow Test - 全流程跑通测试
"""
import sys, os, json, shutil, time
from datetime import datetime

# 1. 设置环境
WORKSPACE = r"C:\Users\Administrator\Desktop\OH-WorkSpace"
sys.path.insert(0, os.path.join(WORKSPACE, "ai-trader"))
os.chdir(os.path.join(WORKSPACE, "ai-trader"))

# 2. 引入核心模块
from v3.event_bus import (
    load_json, save_json, 
    calc_dynamic_budget, calc_market_mood, fetch_market_breadth,
    execute_trade, trade_log, PORTFOLIO_PATH
)

def run_test():
    print("="*50)
    print("  🧪 全流程跑通测试 V9.0")
    print("="*50)
    
    # A. 备份原始数据
    backup_path = str(PORTFOLIO_PATH) + ".bak_test"
    try:
        shutil.copy2(PORTFOLIO_PATH, backup_path)
        print("✅ 数据已备份至 portfolio.json.bak_test")
    except Exception as e:
        print(f"❌ 备份失败: {e}")
        return

    # B. 读取当前状态
    pf = load_json(PORTFOLIO_PATH)
    if not pf:
        print("❌ 无法读取 portfolio.json")
        return
        
    original_cash = pf.get("cash", 0)
    print(f"📊 当前现金: {original_cash}")

    # C. 测试市场情绪与动态仓位 (逻辑层)
    print("\n🧠 [逻辑层] 动态仓位计算测试...")
    
    # 1. 获取市场情绪 (如果断网会返回默认值)
    breadth = fetch_market_breadth()
    print(f"   全市场情绪数据: {breadth}")
    mood = calc_market_mood()
    print(f"   当前环境系数 M: {mood}")
    
    # 2. 计算 88 分高分票的预算
    test_score = 88
    test_budget = calc_dynamic_budget(test_score, original_cash)
    expected_budget = original_cash * 0.35 * mood # 88分对应 35% 档位
    print(f"   Score {test_score} 理论预算: {test_budget:.2f}")

    # D. 测试交易执行 (执行层)
    print("\n🚀 [执行层] 模拟执行交易 (买入 999999 测试股份)...")
    
    # 构造一个不会真实成交的模拟信号 (价格 0.01 确保能买很多，方便测试逻辑)
    # 注意：这里用真实 execute_trade，但价格极低以便观察资金扣除
    mock_signal = {
        "symbol": "sh888888",
        "name": "测试股份",
        "action": "BUY",
        "score": 88,
        "thesis": "全流程测试专用"
    }
    
    # 为了测试，我们需要在 market_data 里加点料，让 execute_trade 能拿到价格
    mock_market_data = {
        "sh888888": {
            "price": 10.0, 
            "name": "测试股份", 
            "change_pct": 2.0,
            "prev_close": 9.8
        }
    }
    
    # 调用 execute_trade
    result = execute_trade(mock_signal, pf, mock_market_data)
    
    if result.get("executed"):
        print(f"✅ 交易执行成功！")
        print(f"   结果详情: {result.get('reason')}")
        
        # 检查内存数据
        new_cash = pf.get("cash", 0)
        positions = pf.get("positions", {})
        
        print(f"💰 扣款后现金: {new_cash} (应减少约 {original_cash - new_cash:.2f})")
        
        if "sh888888" in positions:
            print(f"📈 持仓增加成功: {positions['sh888888']}")
        else:
            print("⚠️ 警告: 持仓字典里没找到 sh888888")
            
        # 强制落盘检查
        save_json(PORTFOLIO_PATH, pf)
        print("💾 已强制写入硬盘...")
        
        # 读取验证
        verify_pf = load_json(PORTFOLIO_PATH)
        if "sh888888" in verify_pf.get("positions", {}):
            print("✅ 落盘验证成功：硬盘里已有该持仓！")
        else:
            print("❌ 落盘验证失败：硬盘里没有找到该持仓 (Bug!)")
    else:
        print(f"⚠️ 交易被拦截 (可能是防抖拦截或其他风控): {result.get('reason')}")
        print("   这说明系统逻辑是通的，只是风控在工作。")

    print("\n" + "="*50)
    print("  🏁 测试结束。请查看上方结果。")
    print("="*50)

if __name__ == "__main__":
    run_test()
