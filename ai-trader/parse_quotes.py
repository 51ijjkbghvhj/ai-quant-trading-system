# -*- coding: utf-8 -*-
import urllib.request
import json

url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sz000591,sh600157,sz300058,sz000938,sz300017,sz002230,sh600536,sh600703,sz300274,sh600438,sz002600,sz000725,sh600010,sh600028,sh601988,sh601288,sh601398,sz000560,sh600588"

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=10)
raw = resp.read().decode("gbk")

stocks = {}
for line in raw.strip().split(";"):
    line = line.strip()
    if not line:
        continue
    # parse v_xxx="data"
    eq_pos = line.find("=")
    if eq_pos == -1:
        continue
    var_part = line[:eq_pos].strip()  # v_sh000001
    data_part = line[eq_pos+2:-1]  # remove =" and trailing "
    
    symbol = var_part.replace("v_", "")
    fields = data_part.split("~")
    
    if len(fields) < 40:
        continue
    
    # Tencent quote format:
    # [0]=market [1]=name [2]=code [3]=current_price [4]=prev_close [5]=open
    # [30]=date [31]=change_amt [32]=change_pct
    # [33]=high [34]=low [35]=price/vol/amount [36]=vol(shares)
    # [37]=turnover_rate [38]=PE
    name = fields[1]
    code = fields[2]
    current = float(fields[3]) if fields[3] else 0
    prev_close = float(fields[4]) if fields[4] else 0
    open_price = float(fields[5]) if fields[5] else 0
    change_pct = float(fields[32]) if fields[32] else 0
    change_amt = float(fields[31]) if fields[31] else 0
    high = float(fields[33]) if fields[33] else 0
    low = float(fields[34]) if fields[34] else 0
    turnover = float(fields[37]) if fields[37] else 0
    volume_str = fields[36] if len(fields) > 36 else "0"
    
    stocks[symbol] = {
        "name": name,
        "code": code,
        "price": current,
        "prev_close": prev_close,
        "open": open_price,
        "change_pct": change_pct,
        "change_amt": change_amt,
        "high": high,
        "low": low,
        "turnover": turnover
    }
    
    print(f"{symbol}: {name} ({code}) | 现价:{current} | 昨收:{prev_close} | 开盘:{open_price} | 涨跌:{change_pct}% | 换手:{turnover}%")

# 🆕 动态指向 user_data 缓存
from pathlib import Path
USER_DATA = Path(__file__).resolve().parent.parent / "user_data"
USER_DATA.mkdir(exist_ok=True)
with open(USER_DATA / "quotes_cache.json", "w", encoding="utf-8") as f:
    json.dump(stocks, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(stocks)} stocks to user_data/quotes_cache.json")
