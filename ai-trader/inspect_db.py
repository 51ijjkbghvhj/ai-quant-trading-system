import sqlite3, json

DB = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\trading_history.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. 列出所有表
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r['name'] for r in c.fetchall()]
print("=" * 60)
print("数据库表结构")
print("=" * 60)
for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    cols = [r['name'] for r in c.fetchall()]
    c.execute(f"SELECT COUNT(*) as cnt FROM {t}")
    cnt = c.fetchone()['cnt']
    print(f"\n[{t}] ({cnt} rows)")
    print(f"  字段: {', '.join(cols)}")

# 2. 查看交易执行记录 (trade_execution)
print("\n" + "=" * 60)
print("交易执行记录 (trade_execution)")
print("=" * 60)
c.execute("SELECT * FROM trade_execution ORDER BY id DESC LIMIT 30")
rows = c.fetchall()
for r in rows:
    d = dict(r)
    print(f"  [{d.get('timestamp','?')}] {d.get('action','?')} {d.get('symbol','?')} qty={d.get('quantity',0)} price={d.get('price',0)} pnl={d.get('pnl',0)}")

# 3. 查看 AI 分析记录 (ai_analysis) - 动态查列
print("\n" + "=" * 60)
print("AI 分析记录 (最近10条)")
print("=" * 60)
c.execute("PRAGMA table_info(ai_analysis)")
ai_cols = [r['name'] for r in c.fetchall()]
c.execute(f"SELECT {', '.join(ai_cols)} FROM ai_analysis ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    d = dict(r)
    sig = d.get('signals_json','')[:80] if d.get('signals_json') else ''
    print(f"  [{d.get('timestamp','?')}] status={d.get('status','?')} executed={d.get('executed','?')} signals={sig}")

# 4. 查看当前持仓 (positions)
print("\n" + "=" * 60)
print("当前持仓 (positions)")
print("=" * 60)
c.execute("SELECT * FROM positions")
for r in c.fetchall():
    d = dict(r)
    print(f"  {d['symbol']} | status={d['status']} | qty={d['qty']} | cost={d['avg_cost']} | pnl={d['current_pnl']} | thesis={d.get('entry_reason','')[:50]}")

# 5. 查看风控记录
print("\n" + "=" * 60)
print("风控拦截记录 (最近15条)")
print("=" * 60)
c.execute("SELECT * FROM risk_control ORDER BY id DESC LIMIT 15")
for r in c.fetchall():
    d = dict(r)
    print(f"  [{d.get('timestamp','?')}] {d.get('action','?')} {d.get('symbol','?')} -> {d.get('result','?')} | {d.get('reason','')[:80]}")

# 6. 交易执行按买卖统计
print("\n" + "=" * 60)
print("交易汇总")
print("=" * 60)
c.execute("SELECT type, COUNT(*) as cnt, SUM(amount) as total_amount, SUM(pnl) as total_pnl FROM trade_execution GROUP BY type")
for r in c.fetchall():
    d = dict(r)
    print(f"  {d['type']}: {d['cnt']}笔, 总金额={d['total_amount']}, 总盈亏={d['total_pnl']}")

# 7. 从交易记录推算现金
c.execute("SELECT type, price, qty FROM trade_execution ORDER BY id")
all_tx = c.fetchall()
initial = 20000
cash = initial
for tx in all_tx:
    amt = tx['price'] * tx['qty']
    if tx['type'] in ('buy', 'BUY'):
        cash -= amt
    elif tx['type'] in ('sell', 'SELL'):
        cash += amt
print(f"\n  初始现金: {initial}")
print(f"  推算现金: {round(cash, 2)}")

conn.close()
