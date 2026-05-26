import urllib.request, json
url = "http://localhost:8503/api/all"
with urllib.request.urlopen(url) as r:
    d = json.loads(r.read().decode("utf-8"))

pf = d.get("pf", {})
print(f"✅ 现金: {pf.get('cash')}")
print(f"✅ 总资产: {pf.get('total')}")
print(f"✅ 浮动盈亏: {pf.get('pnl')}")
print(f"✅ 持仓数量: {len(pf.get('pos', {}))} 只")
for sym, v in pf.get("pos", {}).items():
    print(f"   {sym} {v.get('name')}: status={v.get('status')} qty={v.get('qty')} pnl={v.get('pnl')}")
