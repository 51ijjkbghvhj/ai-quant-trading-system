import json, os, sqlite3
from datetime import datetime

PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"
DB = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\trading_history.db"

with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

# 1. 模拟补单：执行 09:36:47 AI 发出但被 T+1 拦截的 4 笔卖出
missed_sells = [
    {"sym": "sz002047", "name": "宝鹰股份", "price": 4.86},
    {"sym": "sz000630", "name": "铜陵有色", "price": 6.67},
    {"sym": "sz300715", "name": "凯伦股份", "price": 21.55},
    {"sym": "sh688455", "name": "科捷智能", "price": 22.94},
]

print("🔄 正在执行被遗漏的卖出...")
sell_time = "2026-05-26 09:36:47"
pos = pf.get("positions", {})
cash = pf.get("cash", 3284.0)

for ms in missed_sells:
    sym = ms["sym"]
    if sym not in pos:
        print(f"  ⚠️ {sym} 不在持仓中，跳过")
        continue
    
    entry = pos[sym]
    batches = entry if isinstance(entry, list) else [entry]
    total_qty = sum(b.get("qty", 0) for b in batches)
    if total_qty <= 0:
        print(f"  ⚠️ {sym} 数量为 0，跳过")
        continue
        
    avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty
    pnl = round((ms["price"] - avg_cost) * total_qty, 2)
    
    # 更新现金
    cash += ms["price"] * total_qty
    
    # 记录交易
    pf["transactions"].append({
        "type": "sell", "symbol": sym, "name": ms["name"],
        "price": ms["price"], "qty": total_qty, "pnl": pnl,
        "time": sell_time, "reason": "补单执行: AI 逻辑破坏触发卖出"
    })
    
    # 删除持仓
    del pos[sym]
    
    print(f"  ✅ 卖出 {sym} {ms['name']}: {total_qty}股 @ {ms['price']} | 盈亏: {pnl} | 现金: {cash:.2f}")

pf["cash"] = round(cash, 2)
pf["positions"] = pos

# 2. 确保今日持仓状态正确
today = datetime.now().strftime("%Y-%m-%d")
for sym, entry in pf["positions"].items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        bd = b.get("buy_date", "")
        qty = b.get("qty", 0)
        cost = b.get("cost_price", 0)
        cp = b.get("current_price", cost)
        b["pnl"] = round((cp - cost) * qty, 2)
        
        if bd == today:
            b["status"] = "locked"
            b["sellable_qty"], b["sellable_cost"] = 0, cost
            b["locked_qty"], b["locked_cost"] = qty, cost
        else:
            b["status"] = "sellable"
            b["sellable_qty"], b["sellable_cost"] = qty, cost
            b["locked_qty"], b["locked_cost"] = 0, 0

# 保存 portfolio.json
bak = PF + ".bak3." + datetime.now().strftime("%Y%m%d_%H%M%S")
os.rename(PF, bak)
with open(PF, 'w', encoding='utf-8') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print(f"\n💾 账户状态已保存。现金: {pf['cash']}, 持仓: {len(pf['positions'])} 只")

# 3. 同步修复数据库 trade_execution 表
conn = sqlite3.connect(DB)
c = conn.cursor()

# 清空并重建 trade_execution
c.execute("DELETE FROM trade_execution")
for i, tx in enumerate(pf["transactions"]):
    qty = tx.get("qty", 0)
    price = tx.get("price", 0)
    amount = price * qty
    pnl = tx.get("pnl", 0)
    c.execute("INSERT INTO trade_execution (id, timestamp, type, symbol, name, price, qty, amount, pnl, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (i+1, tx.get("time",""), tx["type"], tx["symbol"], tx["name"], price, qty, amount, pnl, tx.get("reason","")))

# 同步 positions 表
c.execute("DELETE FROM positions")
for sym, entry in pf["positions"].items():
    batches = entry if isinstance(entry, list) else [entry]
    tq = sum(b.get("qty", 0) for b in batches)
    ac = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / tq if tq else 0
    nm = batches[0].get("name", sym)
    rs = batches[0].get("buy_reason", "")
    c.execute("INSERT INTO positions (symbol, status, avg_cost, qty, current_pnl, conviction, thesis_json, entry_reason, created_at, updated_at) VALUES (?, 'holding', ?, ?, 0, 60, ?, ?, datetime('now'), datetime('now'))",
              (sym, ac, tq, json.dumps({"reason": rs}, ensure_ascii=False), rs))

conn.commit()
conn.close()
print("✅ 数据库 trade_execution 和 positions 表已同步修复。")
