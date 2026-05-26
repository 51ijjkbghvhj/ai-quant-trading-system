import json, os
from datetime import datetime

PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"

with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

initial = pf.get('initial_cash', 20000)
cash = initial
txs = pf.get('transactions', [])

# 重算现金
for tx in txs:
    price = tx.get('price', 0)
    qty = tx.get('qty', 0)
    amount = price * qty
    if tx['type'] == 'buy':
        cash -= amount
    elif tx['type'] == 'sell':
        cash += amount

print(f"初始现金: {initial}")
print(f"交易笔数: {len(txs)}")
print(f"计算后现金: {round(cash, 2)}")
print(f"旧现金: {pf.get('cash', 0)}")

# 更新现金
pf['cash'] = round(cash, 2)

# 重置 PnL 字段为 0 (将由 server.py 动态计算)
pos = pf.get('positions', {})
for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        b['pnl'] = 0

# 保存
bak = PF + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
os.rename(PF, bak)
with open(PF, 'w', encoding='utf-8') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print("✅ 已修复并保存。旧文件已备份。")
