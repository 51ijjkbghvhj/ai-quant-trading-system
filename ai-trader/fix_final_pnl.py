import json, os, sqlite3
from datetime import datetime

PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"
DB = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\trading_history.db"

with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

# 1. 补录缺失的买入交易
missing_buy = {
    "type": "buy", "symbol": "sh688455", "name": "科捷智能",
    "price": 23.4, "qty": 100, "time": "2026-05-25 14:40:29",
    "reason": "AI主线补涨，龙头达实智能涨停，科捷智能未涨停，换手4.4%尚可，有望轮动。"
}

# 插入到对应时间位置 (保持时序)
txs = pf["transactions"]
# 找到 14:30:02 和 14:35:23 之间的位置
idx = next(i for i, t in enumerate(txs) if "14:35:23" in t.get("time", ""))
txs.insert(idx, missing_buy)
print("✅ 已补录缺失的 科捷智能 买入记录 (-2340)")

# 2. 基于完整流水重算真实现金
initial = pf.get("initial_cash", 20000)
cash = initial
for tx in txs:
    price = tx.get("price", 0)
    qty = tx.get("qty", 0)
    if tx['type'] == 'buy': cash -= price * qty
    elif tx['type'] == 'sell': cash += price * qty

pf["cash"] = round(cash, 2)
print(f"💰 修正后真实现金: {pf['cash']} (旧现金 10039, 差额 -{round(10039 - cash, 2)})")

# 3. 确保状态与分层数据正确
today = datetime.now().strftime("%Y-%m-%d")
pos = pf.get("positions", {})
for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        qty = b.get("qty", 0)
        cost = b.get("cost_price", 0)
        cp = b.get("current_price", cost)
        b["pnl"] = round((cp - cost) * qty, 2)
        
        if b.get("buy_date", "") == today:
            b["status"], b["sellable_qty"], b["locked_qty"] = "locked", 0, qty
        else:
            b["status"], b["sellable_qty"], b["locked_qty"] = "sellable", qty, 0

# 保存
bak = PF + ".bak_final." + datetime.now().strftime("%Y%m%d_%H%M%S")
os.rename(PF, bak)
with open(PF, 'w', encoding='utf-8') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

# 4. 同步修复数据库
conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute("DELETE FROM trade_execution")
for i, tx in enumerate(pf["transactions"]):
    c.execute("INSERT INTO trade_execution (id, timestamp, type, symbol, name, price, qty, amount, pnl, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (i+1, tx.get("time",""), tx["type"], tx["symbol"], tx["name"], tx.get("price",0), tx.get("qty",0), tx.get("price",0)*tx.get("qty",0), tx.get("pnl",0), tx.get("reason","")))

c.execute("DELETE FROM positions")
for sym, entry in pf["positions"].items():
    batches = entry if isinstance(entry, list) else [entry]
    tq = sum(b.get("qty", 0) for b in batches)
    ac = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / tq if tq else 0
    c.execute("INSERT INTO positions (symbol, status, avg_cost, qty, current_pnl, conviction, thesis_json, entry_reason, created_at, updated_at) VALUES (?, 'holding', ?, ?, 0, 60, ?, ?, datetime('now'), datetime('now'))",
              (sym, ac, tq, json.dumps({"reason": batches[0].get("buy_reason","")}, ensure_ascii=False), batches[0].get("buy_reason","")))

conn.commit()
conn.close()
print("✅ 数据库已同步完整。请刷新页面验证。")
