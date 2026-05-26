import http.server, socketserver, json, urllib.parse, urllib.request, threading, time, re, shutil
import sys, os, traceback, sqlite3
from datetime import datetime
from pathlib import Path

# 1. Constants
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "ai-trader"))

MKT = BASE / "trading-dashboard" / "market_data.json"
PF = BASE / "ai-trader" / "portfolio.json"
LOG = BASE / "ai-trader" / "ai_trade.log"
STATIC = BASE / "trading-dashboard" / "static"
MODE_FILE = BASE / "ai-trader" / "system_mode.json"
AI_CONFIG = BASE / "ai-trader" / "ai_config.json"
PORT = 8503

# ==========================================================
# 系统启动横幅与模块自检
# ==========================================================
def print_system_banner():
    import json
    import os
    import sys
    
    print("=" * 50)
    print("  AI 交易系统 v9.0 启动")
    print("=" * 50)
    print("[系统] 正在初始化核心模块...")
    
    # 模块列表检查
    modules_to_check = [
        "v2.db",
        "v2.ai_model", 
        "v2.risk_engine",
        "v3.market_structure",
        "v3.news_pipeline",
        "v3.experience_layer",
        "v3.feature_store",
        "v3.fundamental_risk_layer"
    ]
    
    sys.path.insert(0, str(BASE / "ai-trader"))
    
    all_ok = True
    for mod_name in modules_to_check:
        try:
            __import__(mod_name) 
            print(f"[模块] {mod_name} ... 正常")
        except Exception as e:
            # 仅打印警告，不中断启动
            print(f"[模块] {mod_name} ... 警告 ({e})")

    # 检查 AI 配置
    try:
        config_path = str(BASE / "ai-trader" / "ai_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                ai_conf = json.load(f)
            model_name = ai_conf.get("model", "Unknown")
            print(f"[AI] 模型配置已加载: {model_name}")
        else:
            print("[AI] 警告: 未找到 ai_config.json")
    except Exception as e:
        print(f"[AI] 配置加载失败: {e}")

    # 启动财务背景层
    try:
        from v3.fundamental_risk_layer import start_layer
        pf_path = str(BASE / "ai-trader" / "portfolio.json")
        start_layer(pf_path)
    except Exception as e:
        print(f"[基本面层] 启动失败: {e}")

    print("=" * 50)
    print("  系统就绪。开始监控市场...")
    print("=" * 50)
    print()



# 2. Helper Functions
def load(p):
    for _ in range(3):
        try:
            if p.exists():
                with open(p, encoding="utf-8") as f: return json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            time.sleep(0.1)
    return {}

def save_json(p, d):
    tmp = str(p) + ".tmp"
    bak = str(p) + ".bak"
    try:
        if os.path.exists(p): shutil.copy2(p, bak)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(p))
    except: pass

def get_stats():
    try:
        db_path = str(BASE / "ai-trader" / "trading_history.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ai_analysis")
        analyses = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM trade_execution")
        trades = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(pnl),0) FROM trade_execution")
        pnl = c.fetchone()[0]
        conn.close()
        return {"analyses": analyses, "trades": trades, "pnl": round(pnl, 2)}
    except: return {"analyses": 0, "trades": 0, "pnl": 0}

def fetch_real_price_from_sina(sym):
    """备用源 2：新浪财经 (数据极准)"""
    import re, urllib.request
    try:
        url = f"https://hq.sinajs.cn/list={sym}"
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=3)
        raw = resp.read().decode("gbk", errors="replace")
        m = re.search(r'="([^"]*)"', raw)
        if m:
            f = m.group(1).split(",")
            if len(f) > 3:
                return {"price": float(f[3]), "change_pct": float(f[32]) if len(f) > 32 else 0}
    except: pass
    return {}

def fetch_real_price_from_eastmoney(sym):
    """备用源 3：东方财富 (JSON 格式)"""
    import json, urllib.request
    try:
        secid = f"1.{sym[2:]}" if sym.startswith("sh") else f"0.{sym[2:]}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f170"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"})
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read().decode("utf-8")).get("data", {})
        price = data.get("f43", 0) / 100
        if price > 0:
            prev = data.get("f46", 1)
            change = ((price - prev) / prev) * 100 if prev else 0
            return {"price": price, "change_pct": change}
    except: pass
    return {}

def fetch_real_price_from_tencent(symbols):
    """主源 1：腾讯行情 (速度快，支持批量)"""
    import re, urllib.request
    results = {}
    formatted = []
    for sym in symbols:
        if sym.startswith(('sh', 'sz')): formatted.append(sym)
        elif sym.startswith('6'): formatted.append('sh' + sym)
        elif sym.startswith(('0', '3')): formatted.append('sz' + sym)
    if not formatted: return results
    
    url = "https://qt.gtimg.cn/q=" + ",".join(formatted)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=4)
        raw = resp.read().decode("gbk", errors="replace")
        for line in raw.split(";"):
            m = re.search(r'v_(\w+)="([^"]*)"', line.strip())
            if not m: continue
            sym = m.group(1)
            f = m.group(2).split("~")
            if len(f) < 40: continue
            results[sym] = {
                "name": f[1] if len(f) > 1 else '',
                "price": float(f[3]) if f[3] else 0,
                "change_pct": float(f[32]) if f[32] else 0,
            }
    except: pass
    return results

def get_real_quotes_smart(symbols):
    """智能多源路由：优先腾讯，缺谁补谁，绝不造假"""
    symbols = list(symbols)
    if not symbols: return {}
    
    # 1. 尝试主源批量获取
    results = fetch_real_price_from_tencent(symbols)
    success_symbols = set(results.keys())
    
    # 2. 对失败的股票，逐个启用备用源
    failed_symbols = [s for s in symbols if s not in success_symbols]
    for sym in failed_symbols:
        # 尝试新浪
        res = fetch_real_price_from_sina(sym)
        if res.get("price", 0) > 0:
            results[sym] = res
            continue
        # 尝试东财
        res = fetch_real_price_from_eastmoney(sym)
        if res.get("price", 0) > 0:
            results[sym] = res
    
    return results

def fetch_quotes_subset(symbols):
    """获取指定股票的实时行情（腾讯API）"""
    import re, urllib.request
    results = {}
    formatted = []
    for sym in symbols:
        if sym.startswith(('sh', 'sz')): formatted.append(sym)
        elif sym.startswith('6'): formatted.append('sh' + sym)
        elif sym.startswith(('0', '3')): formatted.append('sz' + sym)
    if not formatted: return results
    url = "https://qt.gtimg.cn/q=" + ",".join(formatted)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("gbk", errors="replace")
        for line in raw.split(";"):
            m = re.search(r'v_(\w+)="([^"]*)"', line.strip())
            if not m: continue
            sym = m.group(1)
            f = m.group(2).split("~")
            if len(f) < 40: continue
            results[sym] = {
                "price": float(f[3]) if f[3] else 0,
                "change_pct": float(f[32]) if f[32] else 0,
                "turnover_rate": float(f[38]) if f[38] else 0,
            }
    except: pass
    return results

# 3. Data Fetching (Dynamic Import)
def migrate_portfolio_data():
    """启动时执行：T+1 状态机同步 & PnL 重算"""
    try:
        pf = load(PF)
        if not pf: return
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        pos = pf.get("positions", {})
        unlocked = 0
        
        for sym, entry in pos.items():
            batches = entry if isinstance(entry, list) else [entry]
            for b in batches:
                buy_date = b.get('buy_date', '')
                cp = b.get('current_price', 0) or b.get('cost_price', 0)
                cost = b.get('cost_price', 0)
                qty = b.get('qty', 0)
                
                # 1. T+1 状态机：今天买的锁定，昨天及之前的全部解冻
                if buy_date == today_str:
                    b['status'] = 'locked'
                else:
                    if b.get('status') == 'locked':
                        b['status'] = 'sellable'
                        unlocked += 1
                
                # 2. 强制重算 PnL 与分层数量（修复前端显示为 0）
                b['pnl'] = round((cp - cost) * qty, 2)
                if b['status'] == 'sellable':
                    b['sellable_qty'] = qty
                    b['sellable_cost'] = cost
                    b['locked_qty'] = 0
                    b['locked_cost'] = 0
                elif b['status'] == 'locked':
                    b['sellable_qty'] = 0
                    b['sellable_cost'] = cost
                    b['locked_qty'] = qty
                    b['locked_cost'] = cost
        
        save_json(PF, pf)
        print(f"[系统] 数据状态同步完成: T+1 解冻 {unlocked} 只持仓, PnL 已重算")
    except Exception as e:
        print(f"[WARN] 数据同步失败: {e}")

def fetch_initial_data():
    print("[初始化] 正在获取初始行情数据...")
    try:
        from v3.event_bus import fetch_quotes, fetch_indices, fetch_news, update_market_json, get_full_market_pool
        pf = load(PF)
        quotes = fetch_quotes()
        indices = fetch_indices()
        news = fetch_news()
        
        # 获取全市场活跃股池用于前端监控池
        full_pool_codes = get_full_market_pool()
        
        print(f"[初始化] 获取行情: {len(quotes) if quotes else 0} 只股票, {len(indices) if indices else 0} 指数, {len(news) if news else 0} 新闻")
        update_market_json(quotes or {}, pf, [], indices or {}, news or {}, monitor_pool_codes=full_pool_codes)
    except Exception as e:
        print(f"[初始化] 错误: {e}")
        traceback.print_exc()

# 4. API Data Aggregator
def api():
    now = datetime.now()
    try:
        h, m = now.hour, now.minute
        wd = now.weekday()
        if wd >= 5: phase = "周末休市"
        elif h < 9: phase = "盘前"
        elif h == 9 and m < 30: phase = "集合竞价"
        elif h == 11 and m >= 30: phase = "午间休市"
        elif h >= 15: phase = "已收盘"
        else: phase = "交易中"

        mkt = load(MKT)
        pf = load(PF)
        
        # ★ 数据防御：修复脏数据导致的崩溃
        if not isinstance(mkt.get('stocks'), dict):
            mkt['stocks'] = {}  # 强制重置为空字典
        ai_config = load(AI_CONFIG)
        pf["ai_model"] = ai_config.get("model", "未配置")
        pf["ai_api_url"] = ai_config.get("api_url", "")

        # 获取研究 AI 模型名称
        try:
            with open(BASE / "ai-trader" / "ai_config_research.json", 'r', encoding='utf-8') as f:
                r_config = json.load(f)
            pf["research_model"] = r_config.get("model", "未配置")
        except:
            pf["research_model"] = "未配置"

        # ★ 关键：交易时间内实时获取持仓和关注池的行情
        pos = pf.get("positions", {})
        watchlist = pf.get("watchlist", [])
        
        # ★ 全时段获取持仓和关注池的真实实时行情（腾讯API收盘后也返回最新数据）
        target_symbols = set(list(pos.keys()) + [w.get("symbol", "") for w in watchlist if w.get("symbol")])
        target_symbols.discard("")
        if target_symbols:
            try:
                quotes = get_real_quotes_smart(target_symbols)
                for sym in pos:
                    entry = pos[sym]
                    batches = entry if isinstance(entry, list) else [entry]
                    if sym in quotes and quotes[sym].get("price", 0) > 0:
                        price = quotes[sym]["price"]
                        change_pct = quotes[sym].get("change_pct", 0)
                        for b in batches:
                            b["current_price"] = price
                            b["change_pct"] = change_pct
                
                # ★ 修复关注池 +0.0%：回写行情到 watchlist
                for w in watchlist:
                    sym = w.get("symbol", "")
                    if sym in quotes and quotes[sym].get("price", 0) > 0:
                        w["price"] = quotes[sym]["price"]
                        w["change_pct"] = quotes[sym].get("change_pct", 0)
            except Exception as e:
                pass

        # ★ 关键防御：清洗 pos 数据，确保前端拿到的每个持仓字段都是数字
        # ★ 新增：隔夜结算逻辑 (T+1 解锁) - 仅在内存中动态计算，不写文件
        today_str = datetime.now().strftime("%Y-%m-%d")
        for sym in list(pos.keys()):
            entry = pos[sym]
            batches = entry if isinstance(entry, list) else [entry]
            
            # 结算：把昨天的 locked 变成 sellable (动态计算)
            for b in batches:
                b_date = b.get('buy_date', '')
                if b.get('status') == 'locked' and b_date and b_date < today_str:
                    b['status'] = 'sellable'
            
            # 2. 数据清洗与计算
            for b in batches:
                b['qty'] = b.get('qty', 0)
                b['cost_price'] = b.get('cost_price', 0)
                if b.get('current_price') is None: b['current_price'] = 0
                b['pnl'] = (b.get('current_price', 0) - b['cost_price']) * b['qty']
                b.setdefault('name', sym)
                b.setdefault('buy_date', '')
                b.setdefault('status', 'sellable') # 兼容旧数据
                b.setdefault('change_pct', 0)

        # ★ 重构 pos_display：不再合并，而是分层展示 (可卖 vs 冻结)
        pos_display = {}
        try:
            for sym, entry in pos.items():
                # 兼容旧数据：如果是字典而不是列表，转为列表
                if isinstance(entry, dict):
                    entry = [entry]
                if not isinstance(entry, list):
                    continue
                    
                batches = entry
                if not batches: continue
                
                # 分离可卖和冻结
                sellable_batches = [b for b in batches if b.get('status') != 'locked']
                locked_batches = [b for b in batches if b.get('status') == 'locked']
                
                # 计算可卖部分
                s_qty = sum(b.get('qty', 0) for b in sellable_batches)
                s_cost = sum(b.get('cost_price', 0) * b.get('qty', 0) for b in sellable_batches)
                s_avg = s_cost / s_qty if s_qty > 0 else 0
                s_pnl = sum(b.get('pnl', 0) for b in sellable_batches)
                
                # 计算冻结部分
                l_qty = sum(b.get('qty', 0) for b in locked_batches)
                l_cost = sum(b.get('cost_price', 0) * b.get('qty', 0) for b in locked_batches)
                l_avg = l_cost / l_qty if l_qty > 0 else 0
                l_pnl = sum(b.get('pnl', 0) for b in locked_batches)
                
                # 组装前端显示对象
                p = batches[0].copy()
                p['qty'] = s_qty + l_qty # 总持仓
                p['sellable_qty'] = s_qty
                p['sellable_cost'] = round(s_avg, 3)
                p['sellable_pnl'] = s_pnl
                p['locked_qty'] = l_qty
                p['locked_cost'] = round(l_avg, 3)
                p['locked_pnl'] = l_pnl
                p['pnl'] = s_pnl + l_pnl # 总盈亏
                p['change_pct'] = batches[0].get('change_pct', 0)
                
                pos_display[sym] = p
        except Exception as e:
            print(f"[ERROR] pos_display construct failed: {e}")
            traceback.print_exc()
            # 降级：直接使用原始数据
            for sym, entry in pos.items():
                if isinstance(entry, dict):
                    pos_display[sym] = entry
                elif isinstance(entry, list) and entry:
                    # 简单合并
                    total_qty = sum(b.get('qty', 0) for b in entry)
                    p = entry[0].copy()
                    p['qty'] = total_qty
                    pos_display[sym] = p
        
        # ★ 兜底保护:如果分层构造失败，直接返回原始数据，防止前端空白
        if not pos_display and pos:
            print("[WARN] pos_display 构造为空，使用原始 pos 兜底")
            pos_display = pos
            
        # ★ 关键修复:确保返回给前端的数据不为空
        # 即使 pos_display 构造失败，也要把原始持仓数据发给前端
        if not pos_display:
            pos_display = pf.get("positions", {})
            
        # 更新 pf 字典中的 positions (虽然 return 里是新建字典，但保持数据一致性)
        pf["positions"] = pos_display
        
        # ★ 实时计算全市场情绪 (Sentiment)
        indices = mkt.get("market", {}).get("indices", {})
        lu_pool = mkt.get("limit_up_pool", [])
        
        score = 50
        up_count = 0
        down_count = 0
        idx_list = list(indices.values()) if isinstance(indices, dict) else []
        
        # 只有在交易时段（包括盘中、竞价）才基于数据计算情绪
        # 休市/周末时，保持中性或显示休市，避免使用过时数据误导
        if "交易中" in phase or "竞价" in phase or "午间" in phase:
            # ★ 升级：基于监控池的涨跌家数计算市场广度（更真实）
            monitor_pool = mkt.get("monitor_pool", [])
            up_stocks = [s for s in monitor_pool if isinstance(s, dict) and s.get('change_pct', 0) > 0]
            down_stocks = [s for s in monitor_pool if isinstance(s, dict) and s.get('change_pct', 0) < 0]
            up_count = len(up_stocks)
            down_count = len(down_stocks)
            total = up_count + down_count
            up_ratio = round(up_count / total * 100, 1) if total > 0 else 50.0
            
            # 情绪分数计算 (基准 50)
            score = 50
            # 1. 涨跌比贡献 (权重 40%)
            if total > 0:
                score += (up_ratio - 50) * 0.4
            
            # 2. 涨停家数贡献 (游资情绪风向标)
            lu_pool_data = mkt.get("limit_up_pool", [])
            lu_count = len(lu_pool_data) if lu_pool_data else 0
            if lu_count >= 50: score += 15
            elif lu_count >= 20: score += 8
            elif lu_count >= 10: score += 4
            elif lu_count < 3: score -= 15
            
            # 限制范围 0-100
            score = max(0, min(100, int(score)))
            
            # 定义情绪阶段
            if score >= 80: sent_phase = "情绪高潮"
            elif score >= 60: sent_phase = "情绪修复"
            elif score >= 40: sent_phase = "震荡分化"
            elif score >= 20: sent_phase = "情绪低迷"
            else: sent_phase = "情绪冰点"
            
            # 计算涨跌比
            total_count = up_count + down_count
            up_ratio = round(up_count / total_count * 100, 1) if total_count > 0 else 50.0
        else:
            # 休市/收盘/周末状态
            score = 50
            sent_phase = phase # 直接显示系统状态，如 "已收盘" 或 "周末休市"
            up_count = 0
            down_count = 0
            up_ratio = 0
        
        real_time_sentiment = {
            "emotion_score": score,
            "emotion_phase": sent_phase,
            "up_count": up_count,
            "down_count": down_count,
            "up_ratio": up_ratio
        }
        
        # ★ 关键修复：计算财务变量（之前缺失导致 NameError，前端全为 0）
        init = pf.get("initial_cash", 0)
        cash = pf.get("cash", 0)
        # 计算持仓市值
        mv = 0.0
        for sym, entry in pos_display.items():
            qty = entry.get("qty", 0) or 0
            cp = entry.get("current_price", 0) or 0
            mv += qty * cp
        total = cash + mv
        
        # ★ 监控池数据清洗：剔除无效代码字符串和价格为 0 的半成品，并限制显示数量防止前端卡顿
        raw_monitor_pool = mkt.get("monitor_pool", [])
        clean_monitor_pool = [
            s for s in raw_monitor_pool 
            if isinstance(s, dict) and s.get('price', 0) > 0
        ]
        # 限制只返回前 200 只
        clean_monitor_pool = clean_monitor_pool[:200]
        
        return {
            "ts": now.isoformat(),
            "sys": {"time": now.strftime("%H:%M:%S"), "phase": phase},
            "idx": mkt.get("market", {}).get("indices", {}),
            "stocks": mkt.get("stocks", {}),
            "news": mkt.get("news", []),
            "sectors": mkt.get("hot_sectors", []),
            "sent": real_time_sentiment,
            "lu": clean_monitor_pool,
            "monitor": clean_monitor_pool,
            "gainers": mkt.get("top_gainers", []),
            "turnover": mkt.get("top_turnover", []),
            "pos": pos_display,
            "pf": {
                "init": init, "cash": round(cash,2), "pos": pos_display,
                "total": round(total,2), "mv": round(mv,2),
                "pnl": round(total-init,2),
                "pnl_pct": round((total-init)/init*100,2) if init else 0,
                "pos_pct": round(mv/total*100,2) if total else 0,
                "tx": pf.get("transactions",[]),
                "risk_logs": pf.get("risk_logs",[]),
                "ai_status": pf.get("ai_status","未连接"),
                "ai_model": pf.get("ai_model", "未配置"),
                "ai_api_url": pf.get("ai_api_url", ""),
                "research_model": pf.get("research_model", "未配置"),
                "ai_model_status": pf.get("ai_model_status",""),
                "ai_log": pf.get("ai_log",[]),
                "watch": pf.get("watchlist",[]),
            }
        }
    except Exception as e:
        return {"ts": now.isoformat(), "error": str(e)}

# 5. Request Handler
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        
        if p in ("/","/index.html"): 
            self._file(STATIC/"index.html")
        elif p=="/api/all": 
            self._json(api())
        elif p=="/api/log": 
            try:
                if LOG.exists():
                    with open(LOG, "r", encoding="utf-8") as f: lines = f.readlines()
                    self._json({"lines": lines[-100:]})
                else: self._json({"lines": []})
            except: self._json({"lines": []})
        elif p=="/api/history":
            try:
                limit = int(qs.get("limit", [50])[0])
                table = qs.get("table", [None])[0]
                
                # 修复：获取时间范围参数
                start_date = qs.get("start", [None])[0]
                end_date = qs.get("end", [None])[0]
                
                # 修复空字符串导致查询为 0 的 Bug
                if not start_date: start_date = None
                if not end_date: end_date = None
                
                rows = []
                db_path = str(BASE / "ai-trader" / "trading_history.db")
                try:
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    t = table if table in ('ai_analysis', 'risk_control', 'trade_execution') else 'ai_analysis'
                    
                    # 构建带时间过滤的 SQL
                    sql = f"SELECT * FROM {t} WHERE 1=1"
                    params = []
                    
                    if start_date:
                        sql += " AND timestamp >= ?"
                        params.append(start_date)
                    if end_date:
                        sql += " AND timestamp <= ?"
                        params.append(end_date + " 23:59:59")
                        
                    sql += " ORDER BY id DESC LIMIT ?"
                    params.append(limit)
                    
                    c.execute(sql, params)
                    rows = [dict(r) for r in c.fetchall()]
                    for r in rows:
                        if 'signals_json' in r and r['signals_json']:
                            try: r['signals'] = json.loads(r['signals_json'])
                            except: pass
                    conn.close()
                except Exception as db_e:
                    rows = [{"error": str(db_e)}]
                self._json({"rows": rows, "stats": {"total": len(rows)}})
            except Exception as e:
                self._json({"error": str(e)})
        elif p=="/api/ai/models":
            try:
                url = qs.get("url", [None])[0]
                key = qs.get("key", [None])[0]
                if url and key:
                    from v2.ai_model import list_models
                    ok, models = list_models(url, key)
                    self._json({"status":"ok","models":models})
                else:
                    self._json({"status":"error","error":"Missing url or key"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})

        elif p=="/api/ai/config":
            config = load(AI_CONFIG)
            if config.get("api_key"):
                key = config["api_key"]
                config["api_key_masked"] = key[:8] + "***" + key[-4:] if len(key) > 12 else "***"
            self._json(config)
        elif p=="/api/ai/research_config":
            rc_path = BASE / "ai-trader" / "ai_config_research.json"
            if rc_path.exists():
                with open(rc_path, 'r', encoding='utf-8') as f:
                    rc = json.load(f)
                if rc.get("api_key"):
                    rc["api_key_masked"] = rc["api_key"][:8] + "***" + rc["api_key"][-4:]
                self._json(rc)
            else:
                self._json({"api_url": "", "api_key": "", "model": ""})
        elif p=="/api/analysis/status":
            try:
                from v3.event_bus import get_status
                self._json(get_status())
            except: self._json({"running": False})

        elif p=="/api/sessions":
            pf = load(PF)
            self._json({"sessions": pf.get("sessions", [])})
        elif p == "/api/kline":
            try:
                import sys
                # 确保能导入 v3
                sys.path.insert(0, str(BASE / "ai-trader"))
                from v3.kline_fetcher import get_raw_klines
                qs_params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                symbol = qs_params.get('symbol', [''])[0]
                data = get_raw_klines(symbol)
                self._json({"status": "ok", "data": data})
            except Exception as e:
                self._json({"status": "error", "message": str(e)})
        else: 
            self.send_error(404)
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if p=="/api/analysis/start":
            try:
                from v3.event_bus import start_analysis
                self._json(start_analysis())
            except Exception as e:
                self._json({"status":"error","error":str(e)})
        elif p=="/api/analysis/stop":
            try:
                from v3.event_bus import stop_analysis
                self._json(stop_analysis())
            except Exception as e:
                self._json({"status":"error","error":str(e)})
        elif p=="/api/ai/models":
            try:
                url = qs.get("url", [None])[0]
                key = qs.get("key", [None])[0]
                if url and key:
                    from v2.ai_model import list_models
                    ok, models = list_models(url, key)
                    self._json({"status":"ok","models":models})
                else:
                    self._json({"status":"error","error":"Missing url or key"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})

        elif p=="/api/ai/config":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
                save_json(AI_CONFIG, post_data)
                from v2.ai_model import reload_config
                reload_config()
                self._json({"status":"ok","message":"AI配置已保存"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})
        elif p=="/api/ai/research_config":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
                rc_path = BASE / "ai-trader" / "ai_config_research.json"
                save_json(rc_path, post_data)
                self._json({"status":"ok","message":"研究AI配置已保存"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})
        elif p=="/api/ai/test":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                post_data = json.loads(raw)
                from v2.ai_model import test_connection
                ok, result = test_connection(post_data.get('api_url'), post_data.get('api_key'))
                resp = {"status":"ok","connected":ok,"result":result}
                if "available_models" in result:
                    resp["models"] = result["available_models"]
                self._json(resp)
            except Exception as e:
                self._json({"status":"error","error":str(e)})
        elif p=="/api/analysis/status":
            try:
                from v3.event_bus import get_status
                self._json(get_status())
            except: self._json({"running": False})
        
        elif p=="/api/portfolio/adjust":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                post_data = json.loads(raw)
                
                pf = load(PF)
                if pf is None:
                    self._json({"status":"error","error":"无法读取账户数据"})
                else:
                    # 更新现金
                    new_cash = post_data.get('cash')
                    new_initial = post_data.get('initial_cash')
                    
                    if new_cash is not None:
                        pf['cash'] = float(new_cash)
                    if new_initial is not None:
                        pf['initial_cash'] = float(new_initial)
                    
                    save_json(PF, pf)
                    self._json({"status":"ok","message":"账户资金已更新"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})

        elif p=="/api/watchlist/validate":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                post_data = json.loads(raw)
                keyword = post_data.get('keyword', '').strip()
                
                if not keyword:
                    self._json({"status":"error","error":"请输入代码"})
                    return

                # 只处理 6 位数字代码
                sym = keyword.lower()
                if len(sym) == 6 and sym.isdigit():
                    if sym.startswith('6'): sym = 'sh' + sym
                    elif sym.startswith(('0', '3')): sym = 'sz' + sym
                elif len(sym) == 8 and sym.startswith(('sh', 'sz')):
                    pass # 已经是完整格式
                else:
                    self._json({"status":"error","error":"请输入有效的 6 位 A 股代码 (如 000725)"})
                    return

                # 实时验证代码是否存在
                try:
                    quotes = get_real_quotes_smart([sym])
                    if sym in quotes and quotes[sym].get('price', 0) > 0:
                        self._json({"status":"ok", "symbol": sym, "name": quotes[sym].get('name', '')})
                    else:
                        self._json({"status":"error","error":"代码不存在或已退市"})
                except Exception as e:
                    self._json({"status":"error","error":"验证失败: " + str(e)})
            except Exception as e:
                self._json({"status":"error","error":str(e)})

        elif p=="/api/watchlist/add":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                post_data = json.loads(raw)
                sym = post_data.get('symbol', '').strip().lower()
                
                if not sym.startswith(('sh', 'sz')):
                    self._json({"status":"error","error":"代码格式错误，需以 sh 或 sz 开头"})
                    return
                    
                # ★ 从行情接口获取真实股票名称
                stock_name = ''
                try:
                    quotes = get_real_quotes_smart([sym])
                    if sym in quotes and quotes[sym].get('name'):
                        stock_name = quotes[sym]['name']
                except:
                    pass
                
                # 如果获取不到名称，用代码后6位作为临时名称
                if not stock_name:
                    stock_name = sym[-6:]
                    
                pf = load(PF)
                wl = pf.setdefault("watchlist", [])
                # 去重
                if not any(w.get("symbol") == sym for w in wl):
                    wl.append({"symbol": sym, "name": stock_name, "reason": "用户手动添加", "added_time": datetime.now().strftime("%H:%M:%S")})
                    save_json(PF, pf)
                self._json({"status":"ok"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})

        elif p=="/api/watchlist/remove":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                post_data = json.loads(raw)
                sym = post_data.get('symbol', '')
                
                pf = load(PF)
                pf["watchlist"] = [w for w in pf.get("watchlist", []) if w.get("symbol") != sym]
                save_json(PF, pf)
                self._json({"status":"ok"})
            except Exception as e:
                self._json({"status":"error","error":str(e)})
                
        else: self.send_error(404)

    def _file(self, f):
        if not f.exists(): self.send_error(404); return
        c = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type","text/html;charset=utf-8")
        self.send_header("Cache-Control","no-cache, no-store, must-revalidate")
        self.send_header("Content-Length",str(len(c)))
        self.end_headers()
        self.wfile.write(c)

    def _json(self, d):
        try:
            b = json.dumps(d,ensure_ascii=False,default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json;charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length",str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError): pass
    
    def log_message(self, format, *args): return # Suppress default logs


if __name__ == '__main__':
    print(f"  AI Trading System")
    print(f"  Frontend: http://localhost:{PORT}")
    print()
    
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("",PORT), H) as s:
        try: s.serve_forever()
        except KeyboardInterrupt: print("\nStopped")
