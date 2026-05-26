import json, os
from datetime import datetime

PF = r"C:\Users\Administrator\Desktop\OH-WorkSpace\ai-trader\portfolio.json"
bak = PF + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")

with open(PF, 'r', encoding='utf-8') as f:
    pf = json.load(f)

os.rename(PF, bak)

today = datetime.now().strftime("%Y-%m-%d")
pos = pf.get("positions", {})

for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        buy_date = b.get("buy_date", "")
        cp = b.get("current_price", 0) or b.get("cost_price", 0)
        cost = b.get("cost_price", 0)
        qty = b.get("qty", 0)
        
        # 1. T+1 状态机
        if buy_date == today:
            b["status"] = "locked"
        else:
            b["status"] = "sellable"
        
        # 2. 分层数量
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
        
        # 3. PnL 重置为 0 (由 server.py 动态计算)
        b["pnl"] = 0

with open(PF, 'w', encoding='utf-8') as f:
    json.dump(pf, f, ensure_ascii=False, indent=2)

print(f"✅ 已修复: cash={pf['cash']}, positions={len(pos)}")
for sym, entry in pos.items():
    batches = entry if isinstance(entry, list) else [entry]
    for b in batches:
        print(f"  {sym} {b['name']}: status={b['status']}, qty={b['qty']}, cost={b['cost_price']}")
