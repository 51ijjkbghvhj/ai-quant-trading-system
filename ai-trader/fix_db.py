import sqlite3, json

DB = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\trading_history.db"
PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"

# 1. 修复 trade_execution 表中 qty=0 的问题
conn = sqlite3.connect(DB)
c = conn.cursor()

# 从 portfolio.json 读取正确交易记录
with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

txs = pf.get('transactions', [])
print(f"从 portfolio.json 读取 {len(txs)} 条交易记录")

# 清空旧表并重建
c.execute("DELETE FROM trade_execution")

for i, tx in enumerate(txs):
    qty = tx.get('qty', 0)
    price = tx.get('price', 0)
    amount = price * qty
    pnl = tx.get('pnl', 0)
    c.execute("""INSERT INTO trade_execution 
        (id, timestamp, type, symbol, name, price, qty, amount, pnl, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        i + 1,
        tx.get('time', ''),
        tx.get('type', ''),
        tx.get('symbol', ''),
        tx.get('name', ''),
        price,
        qty,
        amount,
        pnl,
        tx.get('reason', '')
    ))
    if qty > 0:
        print(f"  [{tx.get('time')}] {tx.get('type')} {tx.get('symbol')} {tx.get('name')} qty={qty} price={price}")

conn.commit()

# 2. 修复 positions 表
c.execute("DELETE FROM positions")
pos = pf.get('positions', {})
for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    total_qty = sum(b.get('qty', 0) for b in batches)
    avg_cost = sum(b.get('cost_price', 0) * b.get('qty', 0) for b in batches) / total_qty if total_qty > 0 else 0
    name = batches[0].get('name', sym)
    reason = batches[0].get('buy_reason', '')
    c.execute("""INSERT OR REPLACE INTO positions 
        (symbol, status, avg_cost, qty, current_pnl, conviction, thesis_json, entry_reason, created_at, updated_at) 
        VALUES (?, ?, ?, ?, 0, 60, ?, ?, datetime('now'), datetime('now'))""",
        (sym, 'holding', avg_cost, total_qty, json.dumps({"reason": reason}, ensure_ascii=False), reason))
    print(f"  positions: {sym} {name} qty={total_qty} cost={avg_cost:.2f}")

conn.commit()
conn.close()

# 3. 修复 ai_analysis 表缺少的列
conn2 = sqlite3.connect(DB)
c2 = conn2.cursor()
try:
    c2.execute("ALTER TABLE ai_analysis ADD COLUMN market_stage TEXT")
except:
    pass
try:
    c2.execute("ALTER TABLE ai_analysis ADD COLUMN pnl REAL DEFAULT 0")
except:
    pass
conn2.commit()
conn2.close()

print("\n✅ 数据库已修复")
