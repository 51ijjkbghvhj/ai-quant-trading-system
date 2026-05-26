import json
from datetime import datetime

PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"
bak = PF + ".bak2." + datetime.now().strftime("%Y%m%d_%H%M%S")

with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

# 用 portfolio.json 中的 transactions 重算现金
initial = pf.get('initial_cash', 20000)
cash = initial
txs = pf.get('transactions', [])

print(f"初始现金: {initial}")
print(f"交易笔数: {len(txs)}")

for tx in txs:
    price = tx.get('price', 0)
    qty = tx.get('qty', 0)
    amount = price * qty
    if tx['type'] == 'buy':
        cash -= amount
        print(f"  BUY  {tx['symbol']} {tx['name']}: {qty}股 @ {price} = -{amount:.2f} | 现金余额: {cash:.2f}")
    elif tx['type'] == 'sell':
        cash += amount
        print(f"  SELL {tx['symbol']} {tx['name']}: {qty}股 @ {price} = +{amount:.2f} | 现金余额: {cash:.2f}")

print(f"\n计算后现金: {round(cash, 2)}")
print(f"旧现金: {pf.get('cash', 0)}")
print(f"差异: {round(cash - pf['cash'], 2)}")

# 更新现金
pf['cash'] = round(cash, 2)

# 重算 PnL 和状态
today = datetime.now().strftime("%Y-%m-%d")
pos = pf.get('positions', {})
total_mv = 0

print(f"\n持仓明细:")
for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        buy_date = b.get("buy_date", "")
        cp = b.get("current_price", b.get("cost_price", 0))
        cost = b.get("cost_price", 0)
        qty = b.get("qty", 0)
        pnl = round((cp - cost) * qty, 2)
        total_mv += cp * qty
        
        # T+1 状态
        if buy_date == today:
            b["status"] = "locked"
        else:
            b["status"] = "sellable"
        
        if b["status"] == "sellable":
            b["sellable_qty"] = qty
            b["sellable_cost"] = cost
            b["locked_qty"] = 0
            b["locked_cost"] = 0
        else:
            b["sellable_qty"] = 0
            b["sellable_cost"] = cost
            b["locked_qty"] = qty
            b["locked_cost"] = cost
        
        b["pnl"] = pnl
        
        print(f"  {sym} {b['name']}: cost={cost} cur={cp} qty={qty} pnl={pnl} status={b['status']}")

total = pf['cash'] + total_mv
pnl_total = round(total - initial, 2)

print(f"\n持仓市值: {round(total_mv, 2)}")
print(f"现金: {pf['cash']}")
print(f"总资产: {round(total, 2)}")
print(f"浮动盈亏: {pnl_total}")
print(f"仓位: {round(total_mv/total*100, 1) if total else 0}%")

# 保存
os_rename = __import__('os')
os_rename.rename(PF, bak)
with open(PF, 'w', encoding='utf-8') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print(f"\n✅ 已修复并保存。旧文件备份: {bak}")
