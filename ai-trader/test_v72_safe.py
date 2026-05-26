# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile
import shutil

# 1. 强制 UTF-8 输出，防止 Windows 控制台乱码
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

# 2. 设置工作路径
# 假设脚本放在 ai-trader 目录下，则 WORKSPACE 是其父目录
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
# 如果放在别处，请修改下面的路径为实际路径
# WORKSPACE = r"C:\Users\Administrator\Desktop\OH-WorkSpace"

print("=== V7.2 独立安全测试 (沙盒模式) ===\n")

# 3. 创建临时隔离环境
TEMP_DIR = tempfile.mkdtemp(prefix="v72_test_")
TEMP_DB = os.path.join(TEMP_DIR, "trading_history.db")
print(f"📂 临时数据库: {TEMP_DB}")

try:
    # 4. 劫持数据库路径 (确保绝对不碰真实数据)
    sys.path.insert(0, WORKSPACE)
    import v2.db
    import v3.experience_layer
    
    # 关键点：修改模块内的全局变量，指向临时库
    v2.db.DB_PATH = TEMP_DB
    v3.experience_layer.DB_PATH = TEMP_DB
    
    # 5. 初始化临时库
    v2.db.init_db()
    print("[OK] 临时数据库已初始化\n")

    # 6. 注入经验层数据 (模拟历史交易)
    from v3.experience_layer import record_thesis_outcome, update_thesis_stats, get_ai_context
    print("⏳ 注入模拟历史数据...")
    record_thesis_outcome("高潮期龙头接力", "EUPHORIA", 100.0, "win", "成功", 2.0)
    record_thesis_outcome("高潮期龙头接力", "EUPHORIA", -80.0, "loss", "炸板", 1.0)
    record_thesis_outcome("高潮期龙头接力", "EUPHORIA", 50.0, "win", "成功", 1.5)
    update_thesis_stats("高潮期龙头接力")

    # 7. 构建市场结构
    from v3.market_structure import build_market_structure, format_for_ai
    mock_market = {
        "sz300001": {"name": "AI龙一", "price": 50, "change_pct": 20.0, "turnover_rate": 15.0, "volume": 500000},
        "sz000002": {"name": "地产弱鸡", "price": 5, "change_pct": -9.9, "turnover_rate": 22.0, "volume": 1000000}
    }
    structure = build_market_structure(mock_market)
    market_prompt = format_for_ai(structure)
    print("[OK] 市场结构已生成\n")

    # 8. 新闻打标
    from v3.news_pipeline import tag_news, format_news_for_ai
    mock_news = [
        {"title": "央行降准释放流动性", "digest": ""}, 
        {"title": "网传某科技龙头业绩大增", "digest": ""}
    ]
    tagged = tag_news(mock_news)
    news_prompt = format_news_for_ai(tagged)
    print("[OK] 新闻已打标\n")

    # 9. 获取经验上下文
    exp_ctx = get_ai_context()
    exp_prompt = "【经验与反思参考】\n"
    for s in exp_ctx['thesis_stats']:
        exp_prompt += f"- {s['type']}: 胜率{s['win_rate']} | 盈亏比:{s['profit_factor']} | 样本:{s['sample_size']}\n"
    for m in exp_ctx['mistakes']:
        exp_prompt += f"⚠️ {m['reason']}\n"

    # 10. 打印最终 AI Prompt (验证升级效果)
    print("=" * 60)
    print("🤖 【AI 最终看到的完整 Prompt】")
    print("=" * 60)
    print(market_prompt)
    print("-" * 60)
    print(news_prompt)
    print("-" * 60)
    print(exp_prompt)
    print("=" * 60 + "\n")

    # 11. 测试风控引擎 (干跑)
    print("🛡️ 测试风控引擎决策...")
    from v2.risk_engine import check_signal
    from v2.models import Signal, MarketData
    from v3.position_lifecycle import PositionManager

    sig = Signal(timestamp="2024-01-01", symbol="sz300001", name="AI龙一",
                 action="BUY", score=85, confidence=0.9, position_ratio=0.15,
                 reason="板块龙头突破", holding_days_expectation=3, price=50.0, qty=100, is_leader=True)
    md = MarketData(timestamp="2024-01-01", symbol="sz300001", name="AI龙一",
                    price=50.0, prev_close=41.6, open=45, high=50, low=45,
                    volume=500000, amount=25000000, change_pct=20.0, turnover_rate=15.0,
                    sector="AI", sector_strength=90, market_state="hot", ma5=48, ma10=40)
    
    pm = PositionManager()
    result = check_signal(sig, md, {}, 10000, 10000, 0, market_state="hot", position_manager=pm)
    
    print(f"✅ 风控裁决: {'通过' if result.approved else '拦截'}")
    print(f"📝 原因: {result.reason}\n")

    print("🎉 测试完成！V7.2 逻辑运行正常。")

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

finally:
    # 12. 自动清理沙盒 (用完即焚)
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        print(f"🗑️ 已自动清理临时文件")
    print("💾 你的真实系统数据未受任何影响。")
