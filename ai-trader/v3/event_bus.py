import re
import threading
import ssl
"""
Event Bus - 事件驱动交易核心
"""
import sys
import urllib.request, os, json, time, re, urllib.request, threading, shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 导入市场结构模块
from v3.market_structure import build_market_structure, extract_key_events, format_for_ai

# 🆕 路径配置：代码与数据分离 (v9.0.7)
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 指向 OH-WorkSpace 根目录
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

# 统一指向 user_data
PORTFOLIO_PATH = USER_DATA_DIR / "portfolio.json"
TRADE_LOG = USER_DATA_DIR / "ai_trade.log"

# 自动迁移旧数据：如果 user_data 里没有，但旧位置有，则搬运过去
_old_portfolio = BASE_DIR / "portfolio.json"
if not PORTFOLIO_PATH.exists() and _old_portfolio.exists():
    print(f"[System] 🔄 检测到旧版数据，正在迁移 portfolio.json 到 /user_data ...")
    import shutil
    shutil.copy2(_old_portfolio, PORTFOLIO_PATH)

_old_log = BASE_DIR / "ai_trade.log"
if not TRADE_LOG.exists() and _old_log.exists():
    shutil.copy2(_old_log, TRADE_LOG)

# 前端数据路径保持不变
MARKET_JSON = BASE_DIR / "trading-dashboard" / "market_data.json"

# 全局状态
_running = False
_thread = None

# 冷却名单内存变量(避免频繁写文件)
_cooldown_list = {}  # {sym: {name, reason, until}}

# =========================================================
# 🚀 系统启动状态检查 & 日志美化模块
# =========================================================

def print_system_banner():
    """打印系统启动时的健康检查报告"""
    # 延迟导入
    from v3.experience_layer import get_conn as get_exp_conn
    from v2.db import get_conn as get_db_conn

    print("=" * 60)
    print("  [System] AI Trading System v9.0.6 - Status Report")
    print("=" * 60)

    status_db = "ERROR"
    status_mem = "ERROR"
    status_tencent = "FAIL"
    status_sina = "FAIL"
    status_ai = "CFG_ERROR"

    portfolio = load_json(PORTFOLIO_PATH)
    cash = portfolio.get('cash', 0) if portfolio else 0

    # 1. 数据库检查
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        conn.close()
        table_count = len(tables)
        status_db = f"OK ({table_count} Tables)"

        # 检查记忆库数据量
        exp_conn = get_exp_conn()
        ec = exp_conn.cursor()
        ec.execute("SELECT count(*) FROM thesis_outcomes")
        trade_count = ec.fetchone()[0]
        ec.execute("SELECT count(*) FROM daily_reflection")
        ref_count = ec.fetchone()[0]
        exp_conn.close()
        status_mem = f"OK ({trade_count} Trades, {ref_count} Reflections)"
    except Exception as e:
        status_db = f"Error: {e}"

    # 2. 腾讯行情 API 检查
    try:
        import requests
        res = requests.get("https://qt.gtimg.cn/q=sh600519", timeout=5)
        if "~" in res.text and len(res.text) > 50:
            status_tencent = f"OK (Connected)"
        else:
            status_tencent = f"WARN (Delay/Block)"
    except Exception as e:
        status_tencent = f"Error: {e}"

    # 3. 全市场列表 API (新浪) 检查
    try:
        res = requests.get("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=1", timeout=5)
        if "symbol" in res.text or len(res.text) > 10:
            status_sina = f"OK (Connected)"
    except Exception as e:
        status_sina = f"WARN (Timeout/Fallback)"

    # 4. AI 接口检查 (只读配置)
    try:
        with open(RESEARCH_CONFIG_PATH, 'r', encoding='utf-8') as f:
            ai_cfg = json.load(f)
        model_name = ai_cfg.get('model', 'Unknown')
        status_ai = f"Ready (Model: {model_name})"
    except Exception as e:
        status_ai = f"Error: {e}"

    # 打印表格
    print(f"  [Acc]  账户资金:    Y {cash:,.2f}  |  持仓: {len(portfolio.get('positions', {}))} 只")
    print("-" * 60)
    print(f"  [DB]   核心数据库: {status_db}")
    print(f"  [DB]   经验记忆库: {status_mem}")
    print(f"  [API]  腾讯行情:   {status_tencent}")
    print(f"  [API]  新浪列表:   {status_sina}")
    print(f"  [AI]   研究引擎:   {status_ai}")
    print("=" * 60)
    print("\n[System] 核心模块加载完毕,等待启动指令...")
    print()

# 辅助函数
def trade_log(msg, force_console=False):
    """统一日志输出函数
    
    参数:
        msg: 日志消息
        force_console: 是否强制输出到控制台(默认False,但AI相关日志会自动强制)
    """
    ts = datetime.now().strftime("%H:%M:%S")
    out_msg = f"[{ts}] {msg}"
    
    # 始终写入日志文件（带强制刷新）
    try:
        with open(TRADE_LOG, 'a', encoding='utf-8') as f:
            f.write(out_msg + '\n')
            f.flush()  # 强制写入磁盘
    except: pass
    
    # ★ 智能判断是否需要输出到控制台
    force_show = force_console
    
    # AI分析相关日志强制显示
    ai_keywords = [
        '[AI]', '[AI思考]', '[AI调试]', '[AI分析]',
        '持仓分析:', '原始候选信号:', '交易分析完成:',
        '动作=', '逻辑=', '评分=', '信号:', '候选:',
        '交易 AI', '研究 AI'
    ]
    
    if any(k in msg for k in ai_keywords):
        force_show = True
    
    # 其他关键日志也显示
    other_keywords = [
        '[交易]', '[风控]', '[关注]', '[周期]', '[系统]',
        '[记忆交接]', '[经验层]', '[线程]', '[错误]',
        '[买入]', '[卖出]', '[涨停]', '[跌停]'
    ]
    
    if any(k in msg for k in other_keywords):
        force_show = True
    
    # 始终输出INFO日志
    if '[INFO]' in msg:
        force_show = True
    
    # ★ 控制台输出（强制刷新缓冲区）
    if force_show:
        try:
            print(out_msg, flush=True)
            # Windows控制台强制刷新
            sys.stdout.flush()
            if hasattr(sys.stdout, 'buffer'):
                sys.stdout.buffer.flush()
        except:
            pass

def load_json(path):
    for _ in range(3):  # 重试 3 次防文件读写冲突
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, PermissionError):
            time.sleep(0.1)
    return None

def save_json(path, data):
    if not data: return
    tmp_path = str(path) + ".tmp"
    bak = str(path) + ".bak"
    try:
        if os.path.exists(path): shutil.copy2(path, bak)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))  # 原子替换,防半截读取
    except Exception as e:
        trade_log(f"[ERROR] 保存 JSON 失败 ({path}): {e}")

# 全市场股票池缓存 (纯动态配置，无保底池)
_FULL_MARKET_POOL = None
_POOL_UPDATE_TIME = 0

def get_full_market_pool():
    """获取全市场活跃股票池 (优先实时网络+失败时缓存兜底)"""
    global _FULL_MARKET_POOL, _POOL_UPDATE_TIME
    now = time.time()

    # 1. 内存缓存 (30 分钟内直接返回)
    if _FULL_MARKET_POOL and (now - _POOL_UPDATE_TIME) < 1800:
        pool = _FULL_MARKET_POOL
    else:
        pool = set()
        
        # 2. ★ 优先尝试实时网络获取 (用户要求实时数据)
        try:
            codes = fetch_all_stock_codes()  # 这里如果失败会抛出异常
            if codes and len(codes) > 50:
                pool.update(codes)
                _FULL_MARKET_POOL = pool
                _POOL_UPDATE_TIME = now
                # 成功后保存到本地 (方便下次启动失败时兜底)
                try:
                    cache_file = BASE / "data" / "stock_pool_cache.txt"
                    cache_file.parent.mkdir(exist_ok=True)
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(sorted(pool)))
                except: pass
                print(f"[INFO] ✅ 实时股票池获取成功: {len(pool)} 只")
                return pool
        except Exception as e:
            print(f"[ERROR] 网络获取失败: {e}")
            # 3. 网络失败 -> 尝试读取本地缓存 (昨日数据)
            cache_file = BASE / "data" / "stock_pool_cache.txt"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_codes = [line.strip() for line in f if line.strip()]
                    if len(cached_codes) > 50:
                        pool.update(cached_codes)
                        print(f"[WARN] ⚠️ 网络失败，使用昨日缓存池: {len(cached_codes)} 只")
                        _FULL_MARKET_POOL = pool
                        return pool
                except: pass
            
            # 4. 所有手段都失败 -> 系统报错停止
            print("[CRITICAL] ❌ 无法获取股票池，系统无法运行！请检查网络或代理设置。")
            raise Exception("Stock pool fetch failed")

    # ★ 关键:加入持仓和关注池,确保实时行情
    try:
        pf = load_json(PORTFOLIO_PATH)
        for sym in pf.get("positions", {}).keys():
            if sym: pool.add(sym)
        for w in pf.get("watchlist", []):
            sym = w.get("symbol", "")
            if sym: pool.add(sym)
    except:
        pass

    return pool

def _calc_limit_prices(prev_close: float, symbol: str) -> tuple:
    """根据昨收价和股票代码计算涨跌停价(交易所规则)"""
    if prev_close <= 0:
        return 0, 0
    sym_upper = symbol.upper()
    if sym_upper.startswith(('SH68', 'SZ30')):
        rate = 0.20  # 科创板/创业板
    elif sym_upper.startswith(('SH8', 'SH4', 'SZ8')):
        rate = 0.30  # 北交所
    else:
        rate = 0.10  # 主板
    return round(prev_close * (1 + rate), 2), round(prev_close * (1 - rate), 2)


def fetch_single_quote(symbol):
    """获取单只股票实时价格(智能多源回退,含涨跌停价)"""
    if not symbol: return {}
    # 格式化前缀
    sym = symbol
    if not symbol.startswith(('sh', 'sz')):
        if symbol.startswith('6'): sym = 'sh' + symbol
        elif symbol.startswith(('0', '3')): sym = 'sz' + symbol

    # 1. 尝试腾讯
    try:
        url = f"https://qt.gtimg.cn/q={sym}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("gbk", errors="replace")

        m = re.search(r'v_(\w+)="([^"]*)"', raw.strip())
        if m:
            f = m.group(2).split("~")
            if len(f) >= 40:
                price = float(f[3])
                if price > 0:
                    return {
                        "symbol": m.group(1),
                        "name": f[1],
                        "price": price,
                        "change_pct": float(f[32]),
                        "turnover_rate": float(f[38]),
                        "limit_up_price": float(f[47]) if len(f) > 47 and f[47] else _calc_limit_prices(float(f[4]) if f[4] else 0, sym)[0],
                        "limit_down_price": float(f[48]) if len(f) > 48 and f[48] else _calc_limit_prices(float(f[4]) if f[4] else 0, sym)[1]
                    }
    except: pass

    # 2. 备用:新浪
    try:
        url = f"https://hq.sinajs.cn/list={sym}"
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("gbk", errors="replace")
        m = re.search(r'="([^"]*)"', raw)
        if m:
            f = m.group(1).split(",")
            if len(f) > 3:
                price = float(f[3])
                if price > 0:
                    change_pct = float(f[32]) if len(f) > 32 else 0
                    prev_close = float(f[2]) if len(f) > 2 else 0
                    limit_up, limit_down = _calc_limit_prices(prev_close, sym)
                    return {"symbol": sym, "name": f[0], "price": price, "change_pct": change_pct, "turnover_rate": 0,
                            "limit_up_price": limit_up, "limit_down_price": limit_down}
    except: pass

    # 3. 备用:东方财富
    try:
        secid = f"1.{sym[2:]}" if sym.startswith("sh") else f"0.{sym[2:]}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f170"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8")).get("data", {})
        price = data.get("f43", 0) / 100
        if price > 0:
            prev = data.get("f46", 1)
            change = ((price - prev) / prev) * 100 if prev else 0
            prev = data.get("f60", 0) / 100 if data.get("f60") else (price / (1 + change / 100) if change else price)
            limit_up, limit_down = _calc_limit_prices(prev, sym)
            return {"symbol": sym, "name": data.get("f58", sym), "price": price, "change_pct": change, "turnover_rate": 0,
                    "limit_up_price": limit_up, "limit_down_price": limit_down}
    except: pass

    return {}

def fetch_quotes():
    """获取A股全市场真实实时行情(腾讯API批量)"""
    results = {}

    full_pool = get_full_market_pool()
    symbols = list(full_pool)
    batch_size = 100  # 腾讯API单次最多支持约100个

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        formatted = []
        for sym in batch:
            if sym.startswith(('sh', 'sz')):
                formatted.append(sym)
            elif sym.startswith('6'):
                formatted.append('sh' + sym)
            elif sym.startswith(('0', '3')):
                formatted.append('sz' + sym)

        if not formatted:
            continue

        url = "https://qt.gtimg.cn/q=" + ",".join(formatted)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read().decode("gbk", errors="replace")
        except: continue

        for line in raw.split(";"):
            m = re.search(r'v_(\w+)="([^"]*)"', line.strip())
            if not m: continue
            sym = m.group(1)
            f = m.group(2).split("~")
            if len(f) < 40: continue
            try:
                price = float(f[3]) if f[3] else 0
                if price <= 0: continue
                results[sym] = {
                    "symbol": sym, "name": f[1],
                    "price": price,
                    "prev_close": float(f[4]) if f[4] else 0,
                    "open": float(f[5]) if f[5] else 0,
                    "high": float(f[33]) if f[33] else 0,
                    "low": float(f[34]) if f[34] else 0,
                    "volume": int(f[6]) if f[6] else 0,
                    "amount": float(f[37]) if f[37] else 0,
                    "change_pct": float(f[32]) if f[32] else 0,
                    "turnover_rate": float(f[38]) if f[38] else 0,
                    "limit_up_price": float(f[47]) if len(f) > 47 and f[47] else _calc_limit_prices(float(f[4]) if f[4] else 0, sym)[0],
                    "limit_down_price": float(f[48]) if len(f) > 48 and f[48] else _calc_limit_prices(float(f[4]) if f[4] else 0, sym)[1],
                }
            except: continue

    print(f"[INFO] 获取行情: {len(results)} 只股票 (全市场 A 股)")
    return results

def fetch_all_stock_codes():
    """获取A股最活跃的前百股票 (超时15秒+重试)"""
    codes = set()
    import requests
    requests.packages.urllib3.disable_warnings()
    
    # ★ 关键修复：增加超时时间，防止启动失败
    TIMEOUT = 15  # 从 5 秒增加到 15 秒
    MAX_RETRY = 2 # 失败后重试 2 次
    
    for retry in range(MAX_RETRY):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            print(f"[INFO] 尝试获取股票池 (第 {retry+1} 次, 超时 {TIMEOUT} 秒)...")

            # 涨幅榜前 2 页 (80x2=160只)
            for page in range(1, 3):
                url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=80&sort=changepercent&asc=0&node=hs_a"
                resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            data = resp.json()
            for s in data:
                sym = s.get("code", "")
                if sym: codes.add(sym)

            # 换手率榜前 1 页 (80只)
            url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=80&sort=turnoverratio&asc=0&node=hs_a"
            resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            data = resp.json()
            for s in data:
                sym = s.get("code", "")
                if sym: codes.add(sym)

            # 成交额榜前 1 页
            url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=80&sort=amount&asc=0&node=hs_a"
            resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
            data = resp.json()
            for s in data:
                sym = s.get("code", "")
                if sym: codes.add(sym)

            # 加入持仓和关注池
            try:
                with open(PORTFOLIO_PATH, encoding='utf-8') as f:
                    pf = json.load(f)
                    for sym in pf.get("positions", {}).keys():
                        if sym: codes.add(sym)
                    for w in pf.get("watchlist", []):
                        sym = w.get("symbol", "")
                        if sym: codes.add(sym)
            except: pass

            print(f"[INFO] 活跃股票池: {len(codes)} 只 (网络获取成功)")
            return codes  # 成功则直接返回
            
        except Exception as e:
            print(f"[WARN] 第 {retry+1} 次获取失败: {e}")
            if retry == MAX_RETRY - 1:
                print("[ERROR] 所有重试均失败，请检查网络连接！")
                raise  # 抛出异常，不再偷偷用默认池
            time.sleep(2)  # 等待 2 秒后重试

def fetch_indices():
    """获取指数"""
    indices = {}
    try:
        url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000016,sh000905"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
        for line in raw.split(";"):
            m = re.search(r'v_(\w+)="([^"]*)"', line.strip())
            if not m: continue
            f = m.group(2).split("~")
            if len(f) > 30:
                indices[m.group(1)] = {
                    "name": f[1], "price": float(f[3]),
                    "change": float(f[31]), "change_pct": float(f[32])
                }
    except: pass
    return indices

def fetch_news():
    """获取新闻"""
    news = []
    try:
        url = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_101_ajaxResult_50_1_.html"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("utf-8", errors="replace")
        match = re.search(r'var ajaxResult=(.+)', raw)
        if match:
            data = json.loads(match.group(1))
            if "LivesList" in data:
                for item in data["LivesList"][:30]:
                    news.append({
                        "title": item.get("title", "") or "",
                        "content": item.get("digest", "") or "",
                        "time": item.get("time", "")[:16].replace("T", " "),
                        "impact": "neutral", "source": "东方财富"
                    })
    except: pass
    try:
        from v3.news_pipeline import tag_news
        return tag_news(news)
    except:
        return news

def update_market_json(current_data, pf, events, indices, news, monitor_pool_codes=None):
    """更新市场数据供前端展示"""
    import os
    MARKET_JSON = str(BASE_DIR / "trading-dashboard" / "market_data.json")
    valid_stocks = {s: d for s, d in current_data.items() if d.get("price", 0) > 0}

    sector_map = defaultdict(lambda: {"stocks": [], "total_change": 0, "up": 0})
    for s, d in valid_stocks.items():
        name = d.get("name", "")
        sector = "其他"
        cn_map = {"金融": ["银行", "保险", "证券"], "白酒": ["茅台", "五粮液", "酒"], "半导体": ["半导体", "芯片"], "新能源": ["锂电", "光伏", "储能"], "医药": ["医药", "生物"], "AI": ["人工智能", "算法", "算力"]}
        for sec, kws in cn_map.items():
            if any(k in name for k in kws): sector = sec; break
        sector_map[sector]["stocks"].append({"symbol": s, "name": name, "change_pct": d.get("change_pct", 0)})
        sector_map[sector]["total_change"] += d.get("change_pct", 0)
        if d.get("change_pct", 0) > 0: sector_map[sector]["up"] += 1

    hot_sectors = []
    for name, stats in sector_map.items():
        if len(stats["stocks"]) >= 2:
            hot_sectors.append({
                "name": name, "change_pct": round(stats["total_change"] / len(stats["stocks"]), 2),
                "stock_count": len(stats["stocks"]), "up_ratio": round(stats["up"] / len(stats["stocks"]) * 100, 1),
                "stocks": stats["stocks"]
            })
    hot_sectors.sort(key=lambda x: x["change_pct"], reverse=True)

    total = len(valid_stocks)
    up = sum(1 for d in valid_stocks.values() if d.get("change_pct", 0) > 0)
    up_ratio = up / total * 100 if total else 0
    phase = "高潮" if up_ratio > 70 else ("冰点" if up_ratio < 30 else "震荡")
    score = int(up_ratio)

    mkt = {
        "market": {"indices": indices, "stocks": valid_stocks},
        "hot_sectors": hot_sectors, "news": news,
        "sentiment": {"emotion_score": score, "emotion_phase": phase, "up_count": up, "down_count": total-up, "up_ratio": round(up_ratio, 1)},
        "timestamp": datetime.now().isoformat()
    }
    # 计算涨停/涨幅/换手率榜
    valid_stocks_list = list(valid_stocks.values())
    mkt['limit_up_pool'] = sorted([s for s in valid_stocks_list if s.get('change_pct', 0) >= 9.9], key=lambda x: x.get('change_pct', 0), reverse=True)
    mkt['top_gainers'] = sorted(valid_stocks_list, key=lambda x: x.get('change_pct', 0), reverse=True)[:50]
    mkt['top_turnover'] = sorted(valid_stocks_list, key=lambda x: x.get('turnover_rate', 0), reverse=True)[:50]

    # ★ 构建前端监控池数据
    # 合并有行情的股票和全市场活跃股代码
    monitor_pool = []
    seen_symbols = set()
    
    # 1. 优先加入有详细行情的股票
    for s in valid_stocks_list:
        sym = s.get('symbol', '')
        if sym and sym not in seen_symbols:
            monitor_pool.append(s)
            seen_symbols.add(sym)
    
    # 2. 补充全市场活跃池中缺失的股票（无行情或行情未获取到）
    if monitor_pool_codes:
        for code in monitor_pool_codes:
            if code not in seen_symbols:
                # 构造基础信息
                monitor_pool.append({
                    "symbol": code,
                    "name": "--",
                    "price": 0,
                    "change_pct": 0,
                    "open": 0, "high": 0, "low": 0, "amount": 0
                })
                seen_symbols.add(code)
    
    mkt['monitor_pool'] = monitor_pool

    print(f"[INFO] 市场数据已更新: {len(valid_stocks)} 只股票, 监控池 {len(monitor_pool)} 只")
    save_json(MARKET_JSON, mkt)

def start_analysis():
    global _running
    
    # ★ 防止重复启动：检查是否已在运行
    if _running:
        trade_log("[系统] 分析已在运行中,请勿重复启动。")
        return {"status": "already_running"}
    
    _running = True
    trade_log("[系统] 正在启动双线程分析架构...")

    # Update status in portfolio
    pf = load_json(PORTFOLIO_PATH)
    if pf is None:
        trade_log("[严重] 无法读取 portfolio.json,已保护性中止。")
        return {"status": "failed"}
    pf["ai_status"] = "分析中"
    pf["ai_start_time"] = __import__('datetime').datetime.now().isoformat()
    save_json(PORTFOLIO_PATH, pf)

    import threading
    # 启动双线程架构:交易线程 (高优先级) + 研究线程 (低优先级/后台)
    # 1. 交易线程
    t_trading = threading.Thread(target=trading_loop, kwargs={"base_interval": 90}, daemon=True)
    # 2. 研究线程 (生物钟调度,无需间隔参数)
    t_research = threading.Thread(target=research_loop, daemon=True)

    t_trading.start()
    t_research.start()

    trade_log("[系统] 双线程分析循环已启动 (交易 + 研究)。")
    return {"status": "started"}

def main_loop(poll_interval=10):
    """兼容 v3_main.py 的入口点"""
    start_analysis()
    try:
        import time
        while _running:
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        stop_analysis()

def stop_analysis():
    global _running
    if not _running:
        return {"status": "not_running"}
    _running = False

    pf = load_json(PORTFOLIO_PATH)
    if not pf:
        trade_log("[保护] 文件读取失败,拒绝覆盖,已保留原数据。")
        return {"status": "failed"}
    pf["ai_status"] = "已停止"
    save_json(PORTFOLIO_PATH, pf)
    trade_log("[系统] 分析循环已停止。")
    return {"status": "stopped"}

def get_status():
    return {"running": _running}

# ══════════════════════════════════════════════════════════
# AI 分析层 - 双模型架构
# ══════════════════════════════════════════════════════════

# 🆕 指向 user_data 目录下的研究配置（如果没有独立配置，则 fallback 到主配置）
RESEARCH_CONFIG_PATH = str(USER_DATA_DIR / "ai_config_research.json")
if not os.path.exists(RESEARCH_CONFIG_PATH):
    RESEARCH_CONFIG_PATH = str(USER_DATA_DIR / "ai_config.json")

def call_trading_ai(market_structure: dict, portfolio: dict, key_events: list = None) -> dict:
    """
    🟢 Model A: 交易 AI (高频实时、精简 Prompt、快速响应)
    """
    try:
        from v2.ai_model import call_mimo

        # ★ 核心架构修复:在输入层构建"可交易候选池",过滤掉买不起的标的
        cash = portfolio.get("cash", 0)
        positions = portfolio.get("positions", {})

        market_value = 0
        for sym, entry in positions.items():
            batches = entry if isinstance(entry, list) else [entry]
            for b in batches:
                price = b.get("current_price", 0)
                if price <= 0: price = b.get("cost_price", 0)
                market_value += b.get("qty", 0) * price

        total = cash + market_value
        
        # ★ 优化:动态价格上限与风控上限对齐
        # 原 15% 上限导致 20-30 元主力密集区股票被误杀
        # 改为 25%，覆盖趋势票，同时不超过风控的 25% 绝对上限
        display_budget = total * 0.25  
        max_price = display_budget / 100.0 if display_budget > 0 else 0

        # 1. 核心数据提取 (去除冗余)
        limit_stats = market_structure.get('limit_stats', {})
        sent = market_structure.get('sentiment', {})
        market_stage = market_structure.get('market_stage', '未知')

        # === 🆕 动态视野架构: 根据情绪周期调整 AI 视野 ===
        # L1:全量扫描 (由 fetch_quotes 决定)
        # L2:扩展候选池 (根据 Stage 动态调整)
        # L3:AI决策 (Prompt 输入)
        if '高潮' in market_stage:
            max_dragons = 20
            max_sectors = 10
            stocks_per_sector = 8
        elif market_stage in ['升温', '震荡偏多']:
            max_dragons = 15
            max_sectors = 6
            stocks_per_sector = 5
        else:
            # 震荡/退潮/恐慌/低迷
            max_dragons = 10
            max_sectors = 3
            stocks_per_sector = 3

        # ★ 注入当前交易阶段,让 AI 知道现在是集合竞价还是连续竞价
        phase_name, can_trade = get_trading_phase()
        user_prompt = f"【交易阶段】{phase_name} {'(正式交易时段)' if can_trade else '(集合竞价/非交易,仅观察分析)'}\n"
        user_prompt += f"市场阶段:{market_structure.get('market_stage', '?')} | 涨停{limit_stats.get('limit_up_count', 0)}只 跌停{limit_stats.get('limit_down_count', 0)}只\n"
        user_prompt += f"上涨比:{sent.get('up_ratio', 0)}% 均涨幅:{sent.get('avg_change', 0)}%\n"

        # === 架构升级:认知与执行分离 (Cognition-Execution Separation) ===

        user_prompt += "\n【第一层:全市场全景与观测锚点 (今日实时)】\n"
        user_prompt += "(注:带👁️标的超出预算,仅作主线强度参考,不可推荐)\n"

        dragons = market_structure.get('dragons', [])
        if dragons:
            dragon_list = []
            # ★ 动态龙头数量
            for d in dragons[:max_dragons]:
                p = d.get('price', 0)
                name = d['name']
                chg = f"{d['change_pct']:+.1f}%"
                turnover = d.get('turnover_rate', 0)
                # 增加领涨标签和详细数据
                tag = " 👁️仅观测 (超预算)" if p > max_price else ""
                dragon_list.append(f"{name}(领涨,今{chg},换手{turnover:.1f}%): 现价{p:.2f}元{tag}")
            user_prompt += "龙头:" + ", ".join(dragon_list) + "\n"

        user_prompt += "\n【第二层:可交易候选池 (仅买得起)】\n"

        sectors = market_structure.get('sectors', [])
        if sectors:
            # ★ 动态板块数量
            for s in sectors[:max_sectors]:  
                # 过滤逻辑:只保留买得起的强势股
                affordable_stocks = [t for t in s.get('top_stocks', []) if t.get('price', 0) <= max_price]
                if affordable_stocks:
                    # ★ 明确板块领涨股，并带上时间维度数据
                    leader_name = s.get('leader', {}).get('name', '未知')
                    stocks_info_list = []
                    for t in affordable_stocks[:stocks_per_sector]:
                        chg = t.get('change_pct', 0)
                        turnover = t.get('turnover_rate', 0)
                        stocks_info_list.append(f"{t.get('name', '')}(今{chg:+.1f}%,换手{turnover:.1f}%)")
                    
                    stocks_info = "，".join(stocks_info_list)
                    user_prompt += f"- {s['name']} (领涨:{leader_name}): {stocks_info}\n"

        # 2. 持仓与 T+1 (分层展示: 可卖 vs 冻结)
        positions = portfolio.get("positions", {})
        today = datetime.now().strftime('%Y-%m-%d')
        if positions:
            user_prompt += "【当前持仓】\n"
            for sym, pos_entry in positions.items():
                batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
                if not batches: continue
                
                name = batches[0].get("name", sym)
                current_price = batches[0].get("current_price", 0)
                
                # 分离可卖和冻结批次
                sellable_batches = [b for b in batches if b.get("status") != "locked"]
                locked_batches = [b for b in batches if b.get("status") == "locked"]
                
                # 计算可卖部分
                s_qty = sum(b.get("qty", 0) for b in sellable_batches)
                s_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in sellable_batches)
                s_avg_cost = s_cost / s_qty if s_qty > 0 else 0
                
                # 计算冻结部分
                l_qty = sum(b.get("qty", 0) for b in locked_batches)
                l_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in locked_batches)
                l_avg_cost = l_cost / l_qty if l_qty > 0 else 0
                
                # 构建提示词
                line_parts = [f"  {sym}({name}): 现价{current_price:.2f}"]
                
                if s_qty > 0:
                    s_pnl_pct = (current_price - s_avg_cost) / s_avg_cost * 100 if s_avg_cost > 0 else 0
                    line_parts.append(f"可卖{s_qty}股(成本{s_avg_cost:.2f}, 盈亏{s_pnl_pct:+.1f}%)")
                
                if l_qty > 0:
                    l_pnl_pct = (current_price - l_avg_cost) / l_avg_cost * 100 if l_avg_cost > 0 else 0
                    line_parts.append(f"冻结{l_qty}股(成本{l_avg_cost:.2f}, 盈亏{l_pnl_pct:+.1f}%) 🔒")
                
                user_prompt += ", ".join(line_parts) + "\n"
        else:
            user_prompt += "【当前持仓】空仓\n"

        # 2.5 读取风控冷却名单(从内存变量读取,避免频繁写文件)
        global _cooldown_list
        now_ts = __import__('time').time()
        active_cooldown = {}
        if _cooldown_list:
            user_prompt += "【冷却名单】以下股票刚被风控拒绝,15 分钟内请勿推荐:\n"
            for sym, info in _cooldown_list.items():
                if info.get("until", 0) > now_ts:
                    active_cooldown[sym] = info
                    user_prompt += f"  - {sym} ({info.get('name', '')}): {info.get('reason', '')}\n"
                # 自动清理过期项
            _cooldown_list = active_cooldown

        # 2.6 ⭐️ 动态资金感知 (软性约束 + 中军优先)
        cash = portfolio.get("cash", 0)
        positions = portfolio.get("positions", {})

        # ★ 实时动态计算持仓市值(基于刚刚刷新的最新现价)
        market_value = 0
        for sym, entry in positions.items():
            batches = entry if isinstance(entry, list) else [entry]
            for b in batches:
                # 优先用现价,若缺失则用成本价兜底,确保动态计算准确
                price = b.get("current_price", 0)
                if price <= 0: price = b.get("cost_price", 0)
                market_value += b.get("qty", 0) * price

        total = cash + market_value
        pos_pct = (market_value / total * 100) if total > 0 else 0

        # 仓位状态描述
        if pos_pct < 20: state_desc = "极轻仓"
        elif pos_pct < 40: state_desc = "轻仓"
        elif pos_pct < 60: state_desc = "半仓"
        elif pos_pct < 80: state_desc = "重仓"
        else: state_desc = "满仓"

        user_prompt += f"\n【资金约束】当前仓位 {pos_pct:.1f}%({state_desc}),可用现金 {cash:.2f} 元,单票预算上限:{display_budget:.2f}元 (即股价需 <= {max_price:.2f}元)。\n"
        
        # ★ 动态策略提示 (根据市场阶段变化)
        stage = market_structure.get('market_stage', '震荡')
        if '高潮' in stage:
            strategy_hint = "当前为高潮期:资金极度亢奋,优先做核心龙头,若龙头买不到则选最强的补涨股 (评分 70-80),严禁买跟风杂毛。"
        elif '升温' in stage or '偏多' in stage:
            strategy_hint = "当前为升温期:主线逐渐清晰,寻找与龙头同属性的趋势股 (评分 80+),敢于上车。"
        elif '退潮' in stage or '恐慌' in stage:
            strategy_hint = "当前为退潮/恐慌期:风险极大,防守为主,宁可空仓也不接飞刀,除非有绝对抗跌的独立逻辑 (评分需>85)。"
        else:
            strategy_hint = "当前为震荡期:低吸为主,避免追高,关注有业绩支撑或政策利好的低位启动股。"

        user_prompt += "\n【今日策略指令】\n"
        user_prompt += f"{strategy_hint}\n"
        user_prompt += "\n请严格遵循以下决策逻辑:\n"
        user_prompt += "1. **认知主线**:参考【第一层】的龙头锚点 (领涨股 + 换手率),判断当前市场资金主攻什么方向。\n"
        if can_trade:
            user_prompt += "2. **执行交易**:**必须且只能**从【第二层:可交易候选池】中挑选标的。严禁推荐带👁️的股票。\n"
            user_prompt += "3. **评分标准**:90+=绝对核心 (重仓), 80-89=主线趋势 (标准), 70-79=补涨试错 (小仓), <70=放弃。\n"
            user_prompt += "4. **宁缺毋滥与兜底机制**:\n"
            user_prompt += "   - 第一优先级：与【第一层】主线一致的核心龙头。\n"
            user_prompt += "   - 第二优先级 (兜底)：若第二层无绝对龙头,**必须选出 1 只形态最强、量价健康的非核心标的**作为小仓试错 (评分控制在 60-75)。\n"
            user_prompt += "   - 除非【第二层】为空或全部涨停,否则**严禁返回空数组 []**。\n"
        else:
            user_prompt += "2. **集合竞价任务**:当前不是正式交易时段。请做以下观察:\n"
            user_prompt += "   - 持仓股和龙头股的开盘强弱(高开=资金认可,低开=资金抛弃)\n"
            user_prompt += "   - 哪些板块集体高开?是否有主线切换迹象?\n"
            user_prompt += "   - 返回 HOLD 信号即可,请在 thesis 中描述观察到的情绪状态。\n"

        # 2.7 ⭐️ 接入经验层:读取复盘日记和历史交易结果
        try:
            from v3.experience_layer import get_ai_context
            ctx = get_ai_context()

            # 读取最近的复盘日记
            reflections = ctx.get('reflection', [])
            if reflections:
                user_prompt += "\n【近期复盘日记】\n"
                for ref in reflections[:2]:  # 只取最近 2 条
                    user_prompt += f"  - {json.dumps(ref, ensure_ascii=False)[:150]}\n"

            # ⭐️ 新增:读取研究 AI 留下的"明日作业"
            if reflections:
                latest_ref = reflections[0]
                if isinstance(latest_ref, dict) and latest_ref.get('next_day_watchlist'):
                    user_prompt += "\n【🔴 研究 AI 核心关注 (优先处理)】\n"
                    for w in latest_ref['next_day_watchlist']:
                        user_prompt += f"  - {w.get('symbol')} ({w.get('name')}): {w.get('logic')}\n"
                    user_prompt += "指令:请优先评估上述标的,若符合买入条件可给予更高权重。"

            # ★ 用户手动关注池逻辑已移至 try 块外 (Line 926),此处删断代码

            # 读取历史交易胜率
            stats = ctx.get('thesis_stats', [])
            if stats:
                user_prompt += "\n【历史策略胜率】\n"
                for st in stats[:3]:  # 只取前 3 条
                    user_prompt += f"  - {st.get('type', '')}: 胜率{st.get('win_rate', '')}, 盈亏比{st.get('profit_factor', '')}, 样本{st.get('sample_size', 0)}\n"

            # ⭐️ 第三步新增:读取并展示"历史禁忌模式" (Negative Patterns)
            patterns = ctx.get('patterns', [])
            if patterns:
                user_prompt += "\n【⛔️ 历史教训/禁忌模式 (严禁触犯)】\n"
                for p in patterns[:3]: # 只取最强的 3 个
                    user_prompt += f"  - 🚫 {p.get('pattern_name')}: {p.get('trigger_conditions')} (教训:{p.get('historical_result')})\n"
                user_prompt += "指令:若目标股票符合上述禁忌特征,必须大幅降分或直接剔除!"

            # 🆕 方案 A:日志"交接清单" (打印给人类看)
            wl_symbols = []
            if 'latest_ref' in locals() and latest_ref.get('next_day_watchlist'):
                for w in latest_ref['next_day_watchlist']:
                    wl_symbols.append(w.get('symbol'))

            pt_names = []
            if 'patterns' in locals() and patterns:
                for p in patterns[:3]:
                    pt_names.append(p.get('pattern_name'))

            if wl_symbols or pt_names:
                wl_str = ", ".join(wl_symbols)
                pt_str = ", ".join(pt_names)
                trade_log(f"✅ [记忆交接] AI 已加载昨日复盘。 🎯 关注作业:{wl_str} | 🚫 禁忌模式:{pt_str}")
            else:
                trade_log(f"✅ [记忆交接] AI 记忆系统启动 (当前无特殊作业/禁忌).")
        except:
            pass  # 经验层不可用时静默跳过,不影响主流程

        # 关注池注入逻辑 (无 Debug 打印,静默执行)

        user_prompt += "\n策略:高潮期只做龙头,震荡期低吸,退潮防守。\n\n警告：直接输出 JSON，不要包含任何文字说明！"

        # 3. 极简 System Prompt (增强约束:强制要求返回带前缀的代码 + 三层选股)
        system_prompt = """你是一个纯粹的交易信号 API 端点。你的输出将直接被 Python 的 json.loads() 解析。
你必须严格遵守以下协议：
1. 你的最终输出必须是且只能是一个合法的 JSON 对象。 
2. 绝对不允许在 JSON 外部输出任何自然语言、分析、解释或 Markdown 代码块标记。
3. 所有思考必须放入 JSON 内部的 "reasoning" 字段。思考要简洁，不超过100字。
4. 先构建 JSON 框架，再填充 reasoning 字段。

JSON 格式要求:
{
  "reasoning": "在这里进行简短的思考、市场分析和逻辑推演（不超过100字）。",
  "market_analysis": {"stage": "阶段", "trend": "一句话"},
  "position_analysis": [{"symbol": "代码", "action": "HOLD/SELL", "thesis_status": "VALID/BROKEN", "reason": "一句话"}],
  "candidates": [{"symbol": "代码", "name": "名称", "score": 75, "action": "BUY", "thesis": "逻辑"}]
}

关键规则:
- 代码必须以 sh/sz 开头，绝不能用中文名称。
- 涨停不买，T+1 锁定不可卖。
- 必须返回至少 1 个 candidate（除非候选池为空），严禁返回空数组。"""

        response = call_mimo(user_prompt, system_prompt, max_tokens=32768, temperature=0.1, json_mode=True)

        # 4. 解析 (全模型容错 + 兜底返回)
        fallback_result = {"candidates": [], "position_analysis": [], "market_analysis": {"stage": market_stage, "trend": "AI未返回有效信号"}, "error": "AI未返回有效JSON"}
        
        # ★ 空响应拦截：模型可能仅输出思考过程，未生成 JSON
        if not response or response.strip() == "":
            trade_log(f"[AI] [WARN] AI未返回JSON内容 (推理模型思考后未输出结构化结果)")
            return fallback_result
        
        try:
            # 尝试清理 Markdown 代码块
            clean_response = response
            if '```' in response:
                code_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
                if code_blocks:
                    clean_response = code_blocks[0]
            
            # 尝试提取 JSON (从第一个 { 到最后一个 })
            start = clean_response.find('{')
            end = clean_response.rfind('}')
            
            if start != -1 and end != -1 and end > start:
                json_str = clean_response[start:end+1]
                result = json.loads(json_str)
                candidates = result.get('candidates', [])
                stage = result.get('market_analysis', {}).get('stage', '?')
                
                # ★ 验证: 检查返回的JSON是否包含必需字段
                if 'candidates' not in result and 'position_analysis' not in result:
                    trade_log(f"[AI] [WARN] JSON缺少必需字段(candidates/position_analysis),可能是推理思考内容")
                    trade_log(f"[AI] JSON keys: {list(result.keys())}")
                    # ★ 打印真实报错内容
                    if 'error' in result:
                        trade_log(f"[AI] [ERROR] 接口返回错误详情: {result['error']}")
                    else:
                        trade_log(f"[AI] [ERROR] AI 返回内容: {json.dumps(result, ensure_ascii=False)[:200]}")
                    return fallback_result
                
                # 打印 AI 的思考过程，方便人类观察
                reasoning = result.get('reasoning', '')
                if reasoning:
                    trade_log(f"[AI思考] {reasoning[:100]}...")
                
                # ★ 调试: 如果 candidates 为空,记录更多信息
                if not candidates:
                    has_layer2 = False
                    for s in sectors[:5]:
                        affordable = [t for t in s.get('top_stocks', []) if t.get('price', 0) <= max_price]
                        if affordable:
                            has_layer2 = True
                            break
                    trade_log(f"[AI调试] candidates为空 | stage={stage} | 第二层候选池={'有' if has_layer2 else '空'} | max_price={max_price:.1f}元 | cash={portfolio.get('cash',0):.0f}")
                    # 直接打印 AI 内部的 reasoning 字段
                    trade_log(f"[AI调试] AI内部逻辑: {result.get('reasoning', '')[:150]}")
                
                trade_log(f"[AI] 交易分析完成: stage={stage}, signals={len(candidates)}")
                return result
            else:
                trade_log(f"[AI] [WARN] JSON解析失败: 未找到有效 JSON 结构")
                trade_log(f"[AI] 原始返回片段: {clean_response[:200]}")
                return fallback_result
        except json.JSONDecodeError as e:
            trade_log(f"[AI] [WARN] JSON解析语法错误: {e}")
            trade_log(f"[AI] 原始返回片段: {clean_response[:200]}")
            return fallback_result
        except Exception as parse_e:
            trade_log(f"[AI] [WARN] 解析异常: {parse_e}")
            return fallback_result
    except Exception as e:
        trade_log(f"[AI] 系统异常: {str(e)}")
        return {"candidates": [], "position_analysis": [], "market_analysis": {"stage": market_stage, "trend": "系统异常"}, "error": str(e)}

def call_research_ai(portfolio: dict, pf: dict, slot_name: str = "") -> dict:
    """
    🔵 Model B: 研究 AI (低频深度、排雷复盘)
    从 ai_config_research.json 加载配置
    slot_name: 触发节点名称(如"早盘前预判"、"收盘后深度复盘")
    """
    if not os.path.exists(RESEARCH_CONFIG_PATH):
        return {"error": "未配置研究模型"}

    try:
        # 读取研究配置
        with open(RESEARCH_CONFIG_PATH, encoding='utf-8') as f:
            r_config = json.load(f)

        from v2.ai_model import call_mimo
        import v2.ai_model as ai_model

        # 临时切换配置
        old_url, old_key, old_mod = ai_model.API_URL, ai_model.API_KEY, ai_model.MODEL
        ai_model.API_URL = r_config.get('api_url', old_url)
        ai_model.API_KEY = r_config.get('api_key', old_key)
        ai_model.MODEL = r_config.get('model', old_mod)

        # 获取深度数据
        from v3.experience_layer import get_ai_context
        ctx = get_ai_context()

        # 🆕 获取全市场情绪数据 (供复盘使用)
        market_context = ""
        try:
            breadth = fetch_market_breadth()
            if breadth:
                market_context += f"【全市场情绪】:{breadth.get('up', 0)}家上涨,{breadth.get('down', 0)}家下跌,{breadth.get('limit_up', 0)}家涨停。"

            # 获取三大指数
            indices = fetch_indices()
            if indices:
                names = {'sh000001': '上证', 'sz399001': '深成', 'sz399006': '创指'}
                idx_parts = []
                for code, data in indices.items():
                    if code in names:
                        pct = data.get('change_pct', 0)
                        idx_parts.append(f"{names[code]}{pct:+.2f}%")
                if idx_parts:
                    market_context += f" 【核心指数】:{', '.join(idx_parts)}"
        except Exception as e:
            market_context = f"[WARN] 获取盘面数据失败:{e}"

        # 根据节点类型生成不同的 Prompt
        if slot_name == "早盘前预判":
            # ⭐️ 盘前策略推演模式
            user_prompt = "现在是盘前推演阶段(开盘前)。请基于以下信息生成今日交易计划。输出 JSON:\n"
            user_prompt += f"0. 当前盘面环境:{market_context}\n"
            user_prompt += f"1. 近期复盘教训:{ctx.get('mistakes', [])}\n"
            user_prompt += f"2. 策略胜率:{ctx.get('thesis_stats', [])}\n"

            positions = portfolio.get('positions', {})
            if positions:
                user_prompt += "3. 当前持仓:\n"
                for sym, pos_entry in positions.items():
                    batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
                    total_qty = sum(b.get("qty", 0) for b in batches)
                    avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty if total_qty > 0 else 0
                    avg_cur = sum(b.get("current_price", 0) * b.get("qty", 0) for b in batches) / total_qty if total_qty > 0 else 0
                    name = batches[0].get("name", "") if batches else ""
                    pnl_pct = ((avg_cur - avg_cost) / avg_cost * 100) if avg_cost else 0
                    user_prompt += f"   - {sym} ({name}): 成本{avg_cost:.2f}, 盈亏{pnl_pct:.1f}%\n"
            else:
                user_prompt += "3. 当前持仓:空仓\n"

            user_prompt += "请输出以下 JSON 结构:\n"
            user_prompt += '{\n'
            user_prompt += '  "risk_warnings": ["今日风险提示 1"],\n'
            user_prompt += '  "strategy_hint": "一句话今日策略建议",\n'
            user_prompt += '  "daily_reflection": {\n'
            user_prompt += '    "date": "今日日期",\n'
            user_prompt += '    "market_summary": "盘前市场预判:今天可能强势的板块",\n'
            user_prompt += '    "portfolio_review": "重点观察标的(带代码)及开盘建议",\n'
            user_prompt += '    "actionable_advice": "早盘特定风险提示及操作计划"\n'
            user_prompt += '  }\n'
            user_prompt += '}\n'

            system_prompt = "你是资深盘前策略师。请基于历史交易教训、当前持仓和市场环境,生成今日交易计划。\n" \
                           "必须包含 'daily_reflection' 字段供写入数据库。严格输出 JSON,不要输出其他文字。"
        else:
            # 盘后复盘模式
            user_prompt = "请基于当前持仓和市场环境,进行深度复盘。输出 JSON:\n"
            user_prompt += f"0. 当前盘面环境:{market_context}\n"
            user_prompt += f"1. 历史失败记录 (Mistakes): {ctx.get('mistakes', [])}\n"
            user_prompt += f"2. 策略胜率统计 (Stats): {ctx.get('thesis_stats', [])}\n"

        # 3. 注入真实持仓数据
        positions = portfolio.get('positions', {})
        if positions:
            user_prompt += "3. 当前真实持仓明细:\n"
            for sym, pos_entry in positions.items():
                batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
                total_qty = sum(b.get("qty", 0) for b in batches)
                avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty if total_qty > 0 else 0
                avg_cur = sum(b.get("current_price", 0) * b.get("qty", 0) for b in batches) / total_qty if total_qty > 0 else 0
                name = batches[0].get("name", "") if batches else ""
                reason = batches[0].get('buy_reason', '未记录') if batches else '未记录'
                pnl_pct = ((avg_cur - avg_cost) / avg_cost * 100) if avg_cost else 0
                user_prompt += f"   - {sym} ({name}): 成本{avg_cost:.2f}, 现价{avg_cur:.2f}, 盈亏{pnl_pct:.1f}%, 买入理由:{reason}\n"
        else:
            user_prompt += "3. 当前持仓:空仓\n"

        user_prompt += "请重点分析:当前持仓是否符合主线?是否有逻辑破坏风险?\n"
        user_prompt += "请额外输出【明日关注名单】(next_day_watchlist):基于近期主线延续性、隔夜消息预期或技术形态,推演 2-3 只明日核心观察标的。即使当前盘面数据静止/不全,也请基于你的市场记忆给出逻辑推演名单,严禁返回空数组。\n"

        system_prompt = "你是资深投研分析师。请严格按照以下 JSON 格式输出,必须包含 'daily_reflection' 字段以供入库记录:\n" \
                        "{\n" \
                        "  \"risk_warnings\": [\"风险提示 1\"],\n" \
                        "  \"strategy_hint\": \"一句话策略建议\",\n" \
                        "  \"next_day_watchlist\": [{\"symbol\": \"shxxxxxx\", \"name\": \"名称\", \"logic\": \"关注逻辑\"}],\n" \
                        "  \"negative_patterns\": [{\"pattern_name\": \"错误模式名称\", \"condition\": \"触发特征\", \"lesson\": \"教训\"}],\n" \
                        "  \"daily_reflection\": {\n" \
                        "    \"date\": \"今日日期\",\n" \
                        "    \"market_summary\": \"今日盘面核心特征与情绪周期判断\",\n" \
                        "    \"portfolio_review\": \"当前持仓逻辑评价及风险点\",\n" \
                        "    \"actionable_advice\": \"具体的加减仓或调仓建议\"\n" \
                        "  }\n" \
                        "}"

        response = call_mimo(user_prompt, system_prompt, max_tokens=32768, temperature=0.3, json_mode=True)
        
        # 研究AI也使用鲁棒的JSON提取
        if not response or response.strip() == "":
            trade_log(f"[研究 AI] ⚠️ 返回内容为空，可能模型超时或网络问题")
            result = {"error": "研究AI未返回JSON内容"}
        else:
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end > start:
                try:
                    result = json.loads(response[start:end+1])
                except Exception as e:
                    trade_log(f"[研究 AI] ⚠️ JSON解析失败: {e}")
                    result = {"error": f"研究AI JSON格式异常 ({response[:100]}...)"}
            else:
                trade_log(f"[研究 AI] ⚠️ 未找到JSON结构: {response[:200]}...")
                trade_log(f"[研究 AI] 原始返回内容：{response}")
                result = {"error": "研究AI未返回有效JSON结构"}

        # 恢复配置
        ai_model.API_URL, ai_model.API_KEY, ai_model.MODEL = old_url, old_key, old_mod
        return result
    except Exception as e:
        return {"error": str(e)}

# 全局缓存全市场情绪数据
_market_breadth_cache = None

def fetch_market_breadth() -> dict:
    """获取全市场情绪指标 (基于 5 大核心指数实时拟合)"""
    import requests
    # 5 大指数:上证、深证、创业板、科创 50、中小 100
    indices = ["sh000001", "sz399001", "sz399006", "sh000688", "sz399101"]
    url = f"https://qt.gtimg.cn/q={','.join(indices)}"
    try:
        res = requests.get(url, timeout=5)
        lines = res.text.strip().split(';')

        pcts = []
        for line in lines:
            if '~' in line:
                data = line.split('~')
                # 3: 现价, 4: 昨收
                try:
                    curr = float(data[3])
                    prev = float(data[4])
                    if prev > 0:
                        pcts.append((curr - prev) / prev * 100)
                except:
                    continue

        if pcts:
            avg_pct = sum(pcts) / len(pcts)
            up_count = sum(1 for p in pcts if p > 0)
            return {
                "avg_change": avg_pct,
                "up_indices": up_count,
                "total_indices": len(pcts),
                "is_divergence": (max(pcts) - min(pcts)) > 1.5 # 分化严重
            }
    except Exception:
        pass
    return None

def calc_market_mood():
    """计算当前市场情绪系数 (基于全市场指数拟合)"""
    breadth = _market_breadth_cache
    if not breadth:
        return 1.0 # 获取失败时使用默认保守值

    avg_pct = breadth.get('avg_change', 0)
    up_ratio = (breadth.get('up_indices', 0) / breadth.get('total_indices', 1)) * 100
    is_divergence = breadth.get('is_divergence', False)

    # 动态环境系数 M (优化逻辑)

    # 1. 冰点/恐慌:全市场平均跌幅超过 1%,或者无一指数上涨
    if avg_pct <= -1.0 or up_ratio == 0:
        return 0.2

    # 2. 退潮/分化:指数表现平平,且存在严重分化(权重护盘题材杀跌)
    if avg_pct < 0.3 or (avg_pct < 0.8 and is_divergence):
        return 0.6

    # 3. 升温:普涨格局,平均涨幅 > 0.8% 且没有分化
    if avg_pct >= 0.8 and not is_divergence:
        return 1.2

    # 4. 高潮:极热状态,平均涨幅 > 1.5%
    if avg_pct >= 1.5:
        return 1.0  # 不放大,防止追高

    # 5. 震荡/常态
    return 0.9

def calc_dynamic_budget(score: int, cash: float, recent_wr: float = 0.5, has_positions: bool = True) -> float:
    """动态仓位计算 (重构版 - 单核心 + 仓位调节器)
    
    架构：
    1. Score → 决定基础仓位 (主引擎)
    2. Mood  → 小幅调整 (裁剪到 0.8~1.2)
    3. Winrate → 仓位调节器 (0.4~1.1)，不归零，让小仓试错成为可能
    
    核心原则：风控是"仓位调节器"，不是"系统停止器"
    """
    # 1. 核心仓位 (Score 决定主引擎)
    if score >= 90: base_pct = 0.35  # 单票硬顶 35%
    elif score >= 80: base_pct = 0.15
    elif score >= 70: base_pct = 0.07
    else: return 0

    # 2. 环境微调 (Mood 仅 ±20%，防止过度缩放)
    mood = calc_market_mood()
    mood = max(0.8, min(1.2, mood))

    # 3. 仓位调节器 (Winrate 连续缩放，绝不归零)
    if recent_wr < 0.2:
        pos_mult = 0.4   # 低胜率：小仓试错
    elif recent_wr < 0.3:
        pos_mult = 0.7   # 恢复中
    elif recent_wr < 0.5:
        pos_mult = 0.9   # 接近正常
    elif recent_wr < 0.6:
        pos_mult = 1.0   # 正常
    else:
        pos_mult = 1.1   # 连胜：适度放大

    # 4. 空仓恢复：清仓代表"释放风险"，系统不应被历史锁死
    if not has_positions:
        pos_mult = max(pos_mult, 0.8)

    final_pct = min(base_pct * mood * pos_mult, 0.35)
    return cash * final_pct

# 兼容旧接口
def call_ai(market_structure: dict, portfolio: dict, key_events: list = None) -> dict:
    return call_trading_ai(market_structure, portfolio, key_events)

def execute_trade(signal: dict, portfolio: dict, market_data: dict, market_stage: str = "neutral") -> bool:
    """
    执行交易: 获取实时价格,写入Thesis,更新Lifecycle
    返回: 是否成功
    """
    try:
        from v3.position_lifecycle import PositionManager, Thesis, PositionState
        from v2.risk_engine import check_signal, MarketData, Signal, get_position_manager
        from v2.db import save_trade, update_position_lifecycle

        sym = signal.get("symbol", "")
        action = str(signal.get("action", "HOLD")).upper()

        if action == "HOLD" or not sym:
            return {"executed": False, "reason": "无效信号"}

        # ★ 清洗并补齐股票代码前缀 (增加智能反查逻辑)
        if '.' in sym:
            sym = sym.split('.')[0]  # 去除 AI 输出的 .SZ/.SH 后缀
        if not sym.startswith(('sh', 'sz')):
            # 1. 尝试常规补全
            if sym.startswith('6'): sym = 'sh' + sym
            elif sym.startswith(('0', '3')): sym = 'sz' + sym
            # 2. 如果还是不对(比如是中文名),尝试在 market_data 中通过名称反查
            else:
                name_to_find = sym
                for m_sym, m_data in market_data.items():
                    if m_data.get('name') == name_to_find:
                        sym = m_sym
                        trade_log(f"[智能纠错] AI 返回了中文名 '{name_to_find}',已自动匹配代码 {sym}")
                        break

        # 获取实时价格
        current_price = market_data.get(sym, {}).get("price", 0)

        # ★ 如果不在当前监控池中,立即单独获取(实现全市场交易)
        if current_price <= 0:
            quote = fetch_single_quote(sym)
            if quote and quote.get("price", 0) > 0:
                current_price = quote["price"]
                # 补全 market_data
                market_data[sym] = {
                    "price": quote["price"],
                    "name": quote.get("name", signal.get("name", "")),
                    "change_pct": quote.get("change_pct", 0),
                    "turnover_rate": quote.get("turnover_rate", 0),
                    "prev_close": quote.get("price", 0),
                    "open": quote.get("price", 0),
                    "high": quote.get("price", 0),
                    "low": quote.get("price", 0),
                    "volume": 0,
                    "amount": 0
                }
                trade_log(f"[交易] 获取到池外股票 {sym} 价格: {current_price}")
            else:
                return {"executed": False, "reason": "无法获取价格(可能停牌或代码错误)"}

        name = market_data.get(sym, {}).get("name", signal.get("name", ""))
        change_pct = market_data.get(sym, {}).get("change_pct", 0)
        limit_up_price = market_data.get(sym, {}).get("limit_up_price", 0)
        limit_down_price = market_data.get(sym, {}).get("limit_down_price", 0)

        # ★ 涨跌停预拦截(基于真实涨停价/跌停价)
        if action == "BUY":
            if limit_up_price > 0 and current_price >= limit_up_price * 0.99:
                trade_log(f"[涨跌停拦截] {sym}({name}) 现价{current_price} >= 涨停价{limit_up_price}*0.99,拒绝买入")
                return {"executed": False, "reason": f"涨停限制(涨停价{limit_up_price})"}
        if action == "SELL":
            if limit_down_price > 0 and current_price <= limit_down_price * 1.01:
                trade_log(f"[跌停拦截] {sym}({name}) 现价{current_price} <= 跌停价{limit_down_price}*1.01,无法卖出")
                # ★ 新增:标记UNEXECUTABLE,暂停后续卖出尝试,带次数限制
                today = datetime.now().strftime('%Y-%m-%d')
                portfolio.setdefault("sell_blocked", {})
                blocked = portfolio["sell_blocked"].get(sym, {})
                blocked["since"] = blocked.get("since", today)
                blocked["last_price"] = current_price
                blocked["last_limit_down"] = limit_down_price
                blocked["attempts"] = blocked.get("attempts", 0) + 1
                portfolio["sell_blocked"][sym] = blocked
                
                # 连续3次尝试失败(不同交易日),标记为永久UNEXECUTABLE
                if blocked["attempts"] >= 3:
                    blocked["unexecutable"] = True
                    trade_log(f"[跌停告警] {sym} 连续{blocked['attempts']}次跌停无法卖出,标记为UNEXECUTABLE")
                
                return {"executed": False, "reason": f"跌停限制(跌停价{limit_down_price})"}
            
            # 跌停恢复:如果之前被标记,现价已脱离跌停价,清除标记
            elif sym in portfolio.get("sell_blocked", {}):
                blocked = portfolio["sell_blocked"][sym]
                if blocked.get("unexecutable"):
                    # 永久标记不清除,每日仅检查一次
                    trade_log(f"[UNEXECUTABLE] {sym} 仍被标记为无法卖出,跳过")
                    return {"executed": False, "reason": "UNEXECUTABLE-连续跌停无法卖出"}
                else:
                    del portfolio["sell_blocked"][sym]
                    trade_log(f"[跌停恢复] {sym} 已脱离跌停价,清除卖出拦截标记")

        # 获取手持现金 (纯动态配置)
        cash = portfolio.get("cash", 0)

        # 动态预算与数量计算 (仅针对 BUY 生效)
        qty = 0
        if action == "BUY":
            # ★ 动态仓位系统 (Scheme 1 + 2)
            score = signal.get('score', 75)

            # ★ 优化: 最近10笔 + Bug过滤 + 空仓恢复
            try:
                from v2.db import get_conn
                conn = get_conn()
                c = conn.cursor()
                # 取最近15笔交易(过滤后取前10笔正常交易)
                c.execute("""SELECT result, reason FROM thesis_outcomes
                    WHERE result IN ('win', 'loss')
                    ORDER BY created_at DESC LIMIT 15""")
                rows = c.fetchall()
                conn.close()

                # 过滤 Bug/异常/测试交易(不计入胜率)
                clean = []
                for r in rows:
                    reason = (r[1] or '').lower()
                    skip = any(k in reason for k in ['bug', '测试', 'error', '异常', 'api错误', '串台', '幻觉'])
                    if not skip:
                        clean.append(r[0])
                    if len(clean) >= 10:
                        break

                total = len(clean)
                wins = sum(1 for r in clean if r == 'win')

                # ★ 胜率冷启动与初始化保护
                # 如果样本量不足 10 笔（说明历史数据少或刚清洗完脏数据），
                # 给予初始胜率 0.6，让系统以健康心态开始运行。
                if total < 10:
                    recent_wr = 0.6
                else:
                    recent_wr = wins / total
            except Exception:
                # 极端情况（如数据库锁死）下的兜底
                recent_wr = 0.5

            # 判断是否空仓(传入 calc_dynamic_budget 内部处理空仓恢复)
            has_positions = len(portfolio.get('positions', {})) > 0

            buy_budget = calc_dynamic_budget(score, cash, recent_wr, has_positions)

            # ★ 加仓预算调整:如果是加仓,预算减半(更保守)
            is_add_position = signal.get('is_add_position', False)
            if is_add_position:
                buy_budget = buy_budget * 0.5  # 加仓预算减半
                trade_log(f"[加仓] 预算调整为原预算的50%: {int(buy_budget)}")

            # === 手数决策系统 ===
            # 核心单位不是"钱"，而是"股数（lot）"，避免离散化崩溃
            LOT = 100
            min_amount = current_price * LOT
            max_lots = int(cash // (current_price * LOT))

            if max_lots < 1:
                # 现金连 1 手都买不起，彻底放弃
                trade_log(f"[交易] {sym} 资金不足 (现价{current_price}, 可用现金{int(cash)})")
                return {"executed": False, "reason": "资金不足,买不起 100 股"}

            # 目标手数（基于动态预算，向下取整）
            target_lots = int(buy_budget // (current_price * LOT))

            # 取交集：至少 1 手，不超过现金能买的最大数量
            final_lots = max(1, min(max_lots, target_lots))
            qty = final_lots * LOT

        cost = qty * current_price

        # 构建 Signal 对象
        sig = Signal(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol=sym,
            name=name,
            action=action,
            score=signal.get("score", 50),
            confidence=signal.get("confidence", 0.5),
            position_ratio=0.1,
            reason=signal.get("thesis", ""),
            holding_days_expectation=5,
            price=current_price,
            qty=qty,  # 使用动态计算的真实数量
            is_leader=signal.get("is_leader", False)
        )

        # 构建MarketData对象
        md = MarketData(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol=sym,
            name=name,
            price=current_price,
            prev_close=market_data.get(sym, {}).get("prev_close", current_price),
            open=market_data.get(sym, {}).get("open", current_price),
            high=market_data.get(sym, {}).get("high", current_price),
            low=market_data.get(sym, {}).get("low", current_price),
            volume=market_data.get(sym, {}).get("volume", 0),
            amount=market_data.get(sym, {}).get("amount", 0),
            change_pct=market_data.get(sym, {}).get("change_pct", 0),
            turnover_rate=market_data.get(sym, {}).get("turnover_rate", 0),
            sector="其他",
            sector_strength=50,
            market_state="neutral",
            limit_up_price=market_data.get(sym, {}).get("limit_up_price", 0),
            limit_down_price=market_data.get(sym, {}).get("limit_down_price", 0)
        )

        # 风控检查
        positions = portfolio.get("positions", {})
        
        # ★ 修复:计算当日实际交易次数
        today = datetime.now().strftime('%Y-%m-%d')
        daily_trade_count = 0
        for t in portfolio.get("transactions", []):
            if t.get("time", "")[:10] == today:
                daily_trade_count += 1

        # ★ 总资产计算防缩水兜底:如果现价缺失,必须用成本价代替,绝不能用 0
        # ★ 修复:使用 pos_sym 而不是 sym,避免覆盖传入的信号股票代码
        pos_market_value = 0
        for pos_sym, entry in positions.items():
            batches = entry if isinstance(entry, list) else [entry]
            for b in batches:
                price = b.get("current_price", 0)
                if price <= 0: price = b.get("cost_price", 0)
                pos_market_value += b.get("qty", 0) * price
        
        # ★ 修复:从portfolio实时获取cash (纯动态配置)
        cash = portfolio.get("cash", 0)
        total = cash + pos_market_value

        pm = get_position_manager()
        # ★ 关键修复:在风控检查前,将 AI 的最新判断 (BROKEN/SELL) 同步给内存中的 PositionLifecycle
        # 防止因内存状态未更新导致风控误拦截卖出指令
        if action == "SELL":
            pos_obj = pm.get_position(sym)
            if pos_obj:
                reason_text = str(signal.get("reason", "")) + str(signal.get("logic", ""))
                if "BROKEN" in reason_text or "逻辑破坏" in reason_text:
                    pos_obj.health.thesis_status = "BROKEN"
                    pos_obj.conviction = 20  # 降至阈值以下,强制允许卖出
                    trade_log(f"[同步] 已将 {sym} 内存状态更新为 BROKEN,准备强平")

        # ★ 新增:Conviction 动态更新 (根据市场反馈加减分)
        # 使用 position_lifecycle 的统一方法,避免逻辑重复
        pos_obj = pm.get_position(sym)
        if pos_obj and action == "HOLD":
            sym_data = market_data.get(sym, {})
            price = sym_data.get("price", 0)
            change_pct = sym_data.get("change_pct", 0)
            turnover = sym_data.get("turnover_rate", 0)

            # 使用 PositionLifecycle 的统一 update_conviction 方法
            if change_pct > 3.0 and turnover > 5.0:
                pos_obj.update_conviction("volume_breakout", f"涨幅{change_pct:.1f}% 换手{turnover:.1f}%")
            elif change_pct > 2.0:
                pos_obj.update_conviction("sector_strength", f"涨幅{change_pct:.1f}%")
            elif change_pct < 0 and turnover < 2.0:
                pos_obj.update_conviction("volume_decline", f"跌幅{abs(change_pct):.1f}% 换手{turnover:.1f}%")
            elif pos_obj.thesis and price < pos_obj.thesis.entry_price * 0.95:
                pos_obj.update_conviction("break_ma5", f"现价{price} < 成本{pos_obj.thesis.entry_price}*0.95")

            # 日志: conviction 变化
            if pos_obj.conviction_history:
                last = pos_obj.conviction_history[-1]
                if last.get("delta", 0) != 0:
                    trade_log(f"[Conviction] {sym}: {last.get('old',0)} → {last.get('new',0)} ({last.get('signal','')})")

        result = check_signal(sig, md, positions, cash, total, daily_trade_count, market_stage, pm)

        if not result.approved:
            trade_log(f"[风控] 拒绝 {sym}: {result.reason}")

            # 1. 记录风控拒绝到 portfolio(供前端显示)
            portfolio.setdefault("risk_logs", []).append({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": sym,
                "name": name,
                "action": action,
                "reason": result.reason,
                "risk_level": result.risk_level,
            })
            if len(portfolio.get("risk_logs", [])) > 50:
                portfolio["risk_logs"] = portfolio["risk_logs"][-50:]

            # 2. ⭐️ 新增:加入 AI 冷却名单(写入内存变量,15 分钟内禁止再次推荐)
            global _cooldown_list
            _cooldown_list[sym] = {
                "name": name,
                "reason": result.reason,
                "until": __import__('time').time() + 900  # 15 分钟 = 900 秒
            }

            # 🚨 关键修复:实时保存风控日志,防止数据丢失
            save_json(PORTFOLIO_PATH, portfolio)

            return {"executed": False, "reason": result.reason}

        # 执行交易
        if action == "BUY":
            # ★ 修复"无限重复买入"Bug:防抖机制
            # 检查最近 5 分钟内是否已经买入过该股票。防止因系统未记账导致的死循环。
            # 注意:这不阻止正常的"加仓"(比如隔天再买),只阻止高频重复下单。
            now_ts = __import__('time').time()
            last_buy_time = 0
            for t in portfolio.get("transactions", []):
                if t.get("symbol") == sym and t.get("type") == "buy":
                    # 简单解析时间字符串 "YYYY-MM-DD HH:MM:SS"
                    try:
                        t_time = __import__('datetime').datetime.strptime(t["time"], "%Y-%m-%d %H:%M:%S").timestamp()
                        if t_time > last_buy_time: last_buy_time = t_time
                    except: pass

            if (now_ts - last_buy_time) < 300: # 300秒 = 5分钟
                trade_log(f"[风控] {sym}({name}) 5 分钟内已买入过,防抖拦截")
                return {"executed": False, "reason": "防抖拦截 (5min 冷却)"}

            # 使用上方动态仓位计算的结果 (qty),不再重复计算
            # 避免旧逻辑 (min(cash * 0.1, 5000)) 覆盖掉动态预算

            cost = qty * current_price

            # 创建Thesis
            thesis = Thesis(
                entry_reason=signal.get("thesis", "AI推荐买入"),
                invalid_conditions=["跌破5日线", "板块退潮", "龙头炸板"],
                entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                entry_price=current_price,
            )

            # 添加仓位生命周期
            pm.add_position(sym, name, thesis)

            # 更新portfolio (增加加权平均逻辑)
            # ★ 修复:统一使用已清洗的sym,避免target_sym重新解析导致不一致
            portfolio["cash"] = cash - cost

            batch = {
                "name": name,
                "qty": qty,
                "cost_price": current_price,
                "current_price": current_price,
                "buy_date": datetime.now().strftime("%Y-%m-%d"),
                "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "buy_reason": signal.get("thesis", ""),
                "pnl": 0,
                # ★ 新增:批次状态管理 (T+1 核心)
                "status": "locked",
                # ★ 新增:持久化保护期/冷静期状态,程序重启后可恢复
                "state_entered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "conviction": 60,  # 初始信念值
                "thesis_status": "VALID",
                # 🟢 风控初始化：买入瞬间建立保护线
                "highest_since_buy": current_price,
                "risk_line": round(current_price * 0.95, 2)
            }
            if sym in portfolio["positions"]:
                portfolio["positions"][sym].append(batch)
            else:
                portfolio["positions"][sym] = [batch]
            portfolio.setdefault("transactions", []).append({
                "type": "buy",
                "symbol": sym,
                "name": name,
                "price": current_price,
                "qty": qty,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "reason": signal.get("thesis", ""),
            })

            # 记录交易
            save_trade({
                "type": "buy",
                "symbol": sym,
                "name": name,
                "price": current_price,
                "qty": qty,
                "amount": cost,
                "reason": signal.get("thesis", ""),
            })

            trade_log(f"[交易] 买入 {name}: {qty}股 @ {current_price}")

            # 🚨 关键修复:实时保存交易记录
            save_json(PORTFOLIO_PATH, portfolio)

            # 🚨 新增:同步更新数据库 positions 表
            try:
                from v2.db import get_conn
                conn = get_conn()
                c = conn.cursor()
                thesis_json = json.dumps({"reason": signal.get("thesis", ""), "entry_price": current_price}, ensure_ascii=False)
                c.execute("INSERT OR REPLACE INTO positions (symbol, status, avg_cost, qty, current_pnl, conviction, thesis_json, entry_reason, created_at, updated_at) VALUES (?, 'holding', ?, ?, 0, 60, ?, ?, datetime('now'), datetime('now'))", (sym, current_price, qty, thesis_json, signal.get("thesis", "")))
                conn.commit()
                conn.close()
            except Exception as db_e:
                trade_log(f"[DB] positions同步失败: {db_e}")

            return {"executed": True, "reason": "风控通过,已买入"}

        elif action == "SELL":
            # 🛡️ 卖出校验:从持仓档案锁定真实数据,防止串台
            pos_entry = portfolio.get("positions", {}).get(sym, [])
            if not pos_entry:
                trade_log(f"[风控拦截] {sym} 无持仓档案,拒绝卖出")
                return {"executed": False, "reason": "无持仓"}

            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            true_name = batches[0].get("name", sym)

            # 名称一致性校验:AI 信号名与档案名必须匹配
            signal_name = signal.get("name", "")
            if signal_name and true_name and signal_name not in true_name and true_name not in signal_name:
                trade_log(f"[严重拦截] 意图串台!AI 想卖 {signal_name},但档案显示 {sym} 是 {true_name}。")
                return {"executed": False, "reason": "名称严重不匹配"}

            name = true_name  # 强制使用档案真名
            total_qty = sum(b.get("qty", 0) for b in batches)
            if total_qty <= 0:
                trade_log(f"[风控拦截] {sym}({name}) 档案数量为 0,拒绝卖出")
                return {"executed": False, "reason": "数量为 0"}

            # 计算加权平均成本
            avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty

            # 检查现价是否离谱(防止用 A 的价格卖 B)
            # 如果 现价 > 成本价 * 1.5 且涨幅巨大,提示警告(允许卖出但记录日志)
            if current_price > avg_cost * 1.5:
                trade_log(f"[风险提示] {name} 现价 ({current_price}) 远高于成本 ({avg_cost}),请确认数据无误。")

            pnl = (current_price - avg_cost) * total_qty

            # 更新 portfolio 现金
            portfolio["cash"] = cash + current_price * total_qty

            # FIFO 扣除旧仓 (严格 T+1 拦截: 只扣减 status != 'locked' 的批次)
            rem = total_qty
            
            # 1. 校验可卖数量
            sellable_qty = sum(b.get("qty", 0) for b in batches if b.get("status") != "locked")
            if sellable_qty < total_qty:
                 trade_log(f"[风控拦截] {sym}({name}) 可卖数量不足 (T+1 限制)。需卖:{total_qty}, 可卖:{sellable_qty}")
                 return {"executed": False, "reason": "可卖数量不足 (T+1 限制)"}

            # 2. 执行扣减
            for b in batches:
                if rem <= 0: break
                if b.get("status") == "locked": continue # 跳过冻结批次
                
                if b["qty"] > rem:
                    b["qty"] -= rem
                    rem = 0
                else:
                    rem -= b["qty"]
                    b["qty"] = 0 
            
            # 3. 保存清仓前的批次信息(必须在清理前保存)
            cleared_batches = [b for b in batches if b.get("qty", 0) > 0]
            original_batches = list(batches)  # 保存原始批次用于冷静期记录
            
            # 4. 清理数量为 0 的批次
            portfolio["positions"][sym] = [b for b in batches if b.get("qty", 0) > 0]
            
            if not portfolio["positions"][sym]:
                # 清仓:保存冷静期信息到portfolio.json,程序重启后可恢复
                pos_obj = pm.get_position(sym)
                conv = pos_obj.conviction if pos_obj else 50
                
                # ★ 修复:使用清仓前保存的原始批次,而非已清空的batches
                first_batch = original_batches[0] if original_batches else {}
                portfolio.setdefault("cooldown_positions", []).append({
                    "symbol": sym,
                    "name": name,
                    "cost_price": avg_cost,
                    "buy_time": first_batch.get("buy_time", ""),
                    "buy_reason": first_batch.get("buy_reason", ""),
                    "sell_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "conviction": conv,
                })
                # 只保留最近5条冷静期记录
                if len(portfolio["cooldown_positions"]) > 5:
                    portfolio["cooldown_positions"] = portfolio["cooldown_positions"][-5:]
                del portfolio["positions"][sym]
            else:
                # 部分卖出,更新state_entered_at和conviction
                pos_obj = pm.get_position(sym)
                if pos_obj:
                    for b in batches:
                        b["state_entered_at"] = pos_obj.state_entered_at
                        b["conviction"] = pos_obj.conviction
                        b["thesis_status"] = pos_obj.health.thesis_status

            # 写入交易记录
            # 🛡️ 风控卖出处理：如果触发风控，记录打折后的委托价
            order_price = current_price
            is_risk_sell = "风控" in signal.get("reason", "")
            if is_risk_sell:
                limit_price = signal.get("trigger_price", current_price) * 0.98
                # 记录实际委托价（用于前端展示）
                order_price = round(limit_price, 2)
                trade_log(f"[风控执行] {sym} 委托价: {order_price:.2f} (防守线{signal.get('trigger_price', current_price):.2f} 的 98%)")

            portfolio.setdefault("transactions", []).append({
                "type": "sell",
                "symbol": sym,
                "name": name,
                "price": current_price,  # 实际成交价（用于盈亏计算）
                "order_price": order_price, # 委托价（用于前端展示风控逻辑）
                "qty": total_qty,
                "pnl": pnl,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "reason": result.reason,
            })

            # 记录交易 (原有逻辑)
            save_trade({
                "type": "sell",
                "symbol": sym,
                "name": name,
                "price": current_price,
                "qty": total_qty,
                "amount": current_price * total_qty,
                "pnl": pnl,
                "reason": result.reason,
            })

            # 新增:将交易结果写入 thesis_outcomes 供研究 AI 分析
            try:
                from v2.db import get_conn
                conn = get_conn()
                c = conn.cursor()

                # 计算持仓天数(取最早批次)
                buy_date_str = batches[0].get("buy_date", datetime.now().strftime("%Y-%m-%d")) if batches else datetime.now().strftime("%Y-%m-%d")
                try:
                    buy_dt = datetime.strptime(buy_date_str, "%Y-%m-%d")
                    days = (datetime.now() - buy_dt).days
                except:
                    days = 0

                # 判定结果:Win or Loss
                result_type = "win" if pnl > 0 else "loss"

                # 提取 Thesis (取最早批次买入理由的前 20 字作为策略类型)
                thesis_type = batches[0].get("buy_reason", "General") if batches else "General"
                if len(thesis_type) > 20: thesis_type = thesis_type[:20]

                c.execute("""INSERT INTO thesis_outcomes
                    (thesis_type, market_state, pnl, result, reason, holding_days, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (thesis_type, "Unknown", pnl, result_type, result.reason, days, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                # 更新统计数据
                from v3.experience_layer import update_thesis_stats_logic
                update_thesis_stats_logic(c, thesis_type)

                conn.commit()
                conn.close()
                trade_log(f"[经验层] 已记录 {name} 的卖出结果 ({result_type}) 到数据库")
            except Exception as db_e:
                trade_log(f"[经验层] 记录卖出结果失败: {db_e}")

            trade_log(f"[交易] 卖出 {name}: {total_qty}股 @ {current_price}, 盈亏={pnl:+.2f}")

            # 🚨 关键修复:实时保存交易记录
            save_json(PORTFOLIO_PATH, portfolio)

            # 🚨 新增:同步更新数据库 positions 表 - 标记为已清仓
            try:
                from v2.db import get_conn
                conn = get_conn()
                c = conn.cursor()
                # 删除该持仓记录(已卖出)
                c.execute("DELETE FROM positions WHERE symbol=?", (sym,))
                conn.commit()
                conn.close()
            except Exception as db_e:
                trade_log(f"[DB] positions删除失败: {db_e}")

            return {"executed": True, "reason": "风控通过,已卖出"}

    except Exception as e:
        trade_log(f"[交易] 错误: {e}")
        return {"executed": False, "reason": f"异常:{str(e)[:50]}"}

def run_cycle(research_mode=False):
    """完整分析循环"""
    if research_mode:
        trade_log("[研究 AI] 开始执行深度分析...")
        pf = load_json(PORTFOLIO_PATH)
        # ★ 修复:传入 pf 而不是 {},让研究 AI 能看到真实持仓
        result = call_research_ai(pf, pf)
        if "error" not in result:
            trade_log(f"[研究] 风险提示: {result.get('risk_warnings', [])}")
            trade_log(f"[研究] 策略建议: {result.get('strategy_hint', '')}")

            # ★ 关键修复:将研究 AI 的复盘内容写入经验层,形成闭环
            try:
                from v3.experience_layer import save_daily_reflection
                reflection_payload = {
                    "risk_warnings": result.get('risk_warnings', []),
                    "strategy_hint": result.get('strategy_hint', ''),
                    "full_result": result # 保存完整结果供未来分析
                }
                save_daily_reflection(reflection_payload)
                trade_log("[经验层] 研究 AI 复盘已成功入库")

                # ★ 第三步新增:提取并保存"负面模式" (Negative Patterns)
                patterns = result.get('negative_patterns', [])
                if patterns:
                    from v3.experience_layer import save_pattern
                    for p in patterns:
                        name = p.get('pattern_name', '')
                        condition = p.get('condition', '')
                        lesson = p.get('lesson', '')
                        if name and condition:
                            save_pattern(name, condition, lesson, 0.85)
                            trade_log(f"[经验层] 已登记禁忌模式:{name}")
            except Exception as e:
                trade_log(f"[经验层] 保存研究结果失败: {e}")
        return

    trade_log("[周期] 开始执行分析周期...")

    try:
        executed_count = 0  # 确保在 try 块最开始初始化,防止后续引用报错
        current_data = fetch_quotes()

        # 🚨 关键修复：T+1 自动解锁 (在每次分析周期前执行)
        # 修复之前因为状态未同步导致卖出被静默拦截的 Bug
        try:
            pf_temp = load_json(PORTFOLIO_PATH)
            if pf_temp:
                today_str = datetime.now().strftime("%Y-%m-%d")
                fixed_unlock = 0
                pos = pf_temp.get("positions", {})
                for sym, entry in pos.items():
                    batches = entry if isinstance(entry, list) else [entry]
                    for b in batches:
                        # 不是今天买的，强制设为可卖
                        if b.get("buy_date", "") != today_str and b.get("status") == "locked":
                            b["status"] = "sellable"
                            b["sellable_qty"] = b.get("qty", 0)
                            b["locked_qty"] = 0
                            fixed_unlock += 1
                if fixed_unlock > 0:
                    trade_log(f"[T+1] 自动解冻 {fixed_unlock} 个批次")
                    # 保存修正后的状态，供本次交易循环使用
                    from pathlib import Path
                    import json, shutil
                    bak = str(PORTFOLIO_PATH) + ".bak_sync"
                    if Path(PORTFOLIO_PATH).exists(): shutil.copy2(PORTFOLIO_PATH, bak)
                    with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
                        json.dump(pf_temp, f, ensure_ascii=False, indent=2)
                    # 更新全局 pf 变量
                    pf = pf_temp
                # 同步 PositionManager
                from v2.risk_engine import get_position_manager
                pm = get_position_manager()
                pm.sync_from_portfolio(pf_temp)
        except Exception as sync_e:
            trade_log(f"[同步] T+1状态同步失败: {sync_e}")

        # 🆕 获取全市场情绪数据 (供动态仓位使用)
        global _market_breadth_cache
        _market_breadth_cache = fetch_market_breadth()

        indices = fetch_indices()
        news = fetch_news()
        pf = load_json(PORTFOLIO_PATH)
        if pf is None:
            trade_log("[严重] 读取 portfolio.json 失败,本轮跳过。")
            return

        if not current_data:
            trade_log("[周期] 无行情数据,跳过")
            return

        # ★ 关键修复:同步更新 pf 中持仓的现价
        pos_in_pf = pf.get("positions", {})
        for sym, pos_entry in pos_in_pf.items():
            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            if sym in current_data and batches:
                price = current_data[sym].get("price", 0)
                if price > 0:
                    for b in batches:
                        b["current_price"] = price

        # ★ 新增:清理过期冷静期记录(超过30分钟)
        now_ts = __import__('time').time()
        cooldown_list = pf.get("cooldown_positions", [])
        valid_cooldown = []
        for cd in cooldown_list:
            try:
                sell_time = __import__('datetime').datetime.strptime(cd.get("sell_time", ""), "%Y-%m-%d %H:%M:%S")
                elapsed = (now_ts - sell_time.timestamp()) / 60
                if elapsed < 30:  # 冷静期30分钟
                    valid_cooldown.append(cd)
            except:
                pass
        pf["cooldown_positions"] = valid_cooldown

        market_structure = build_market_structure(current_data)
        market_stage = market_structure.get("market_stage", "neutral")

        # 🟢 动态风控线计算 (Stop & Trail) - 放在 market_stage 之后确保不报错
        for sym, pos_entry in pos_in_pf.items():
            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            if sym in current_data and batches:
                price = current_data[sym].get("price", 0)
                if price > 0:
                    for b in batches:
                        highest = b.get("highest_since_buy", b.get("cost_price", price))
                        if price > highest:
                            b["highest_since_buy"] = price
                            highest = price
                        
                        cost = b.get("cost_price", price)
                        trail_pct = 0.03 
                        is_20cm = sym.startswith(('sz30', 'sh68'))
                        if is_20cm: trail_pct = 0.06
                        
                        if "高潮" in market_stage: trail_pct = 0.08 if is_20cm else 0.05
                        elif "退潮" in market_stage or "冰点" in market_stage: trail_pct = 0.03 if is_20cm else 0.015
                        
                        profit_ratio = (highest - cost) / cost if cost > 0 else 0
                        if profit_ratio > 0.03: new_line = highest * (1 - trail_pct)
                        else: new_line = cost * 0.95 
                        
                        # 线只升不降 + 保留 2 位小数
                        b["risk_line"] = round(max(b.get("risk_line", new_line), new_line), 2)

        limit_stats = market_structure.get("limit_stats", {})
        key_events = extract_key_events(current_data, limit_stats)

        # ★ 修复:日志使用全市场情绪数据(基于监控池),而非仅266只活跃股的局部统计
        breadth = _market_breadth_cache or {}
        up_ratio = market_structure.get("sentiment", {}).get("up_ratio", 0)
        up_c = market_structure.get("sentiment", {}).get("up_count", 0)
        down_c = market_structure.get("sentiment", {}).get("down_count", 0)
        lu = limit_stats.get('limit_up_count', 0)
        ld = limit_stats.get('limit_down_count', 0)
        trade_log(f"[周期] 市场状态: {market_stage} | 上涨:{up_c} 下跌:{down_c} 上涨比:{up_ratio}% | 涨停:{lu} 跌停:{ld}")

        ai_result = call_trading_ai(market_structure, pf, key_events)

        # 🛡️ 风控拦截器：检查是否跌破风控线 (优先级高于 AI)
        risk_sells = []
        for sym, pos_entry in pos_in_pf.items():
            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            current_price = current_data.get(sym, {}).get("price", 0)
            
            if current_price > 0:
                # 检查每个批次
                for b in batches:
                    risk_line = b.get("risk_line", 0)
                    if risk_line > 0 and current_price <= risk_line:
                        # 检查 T+1
                        if b.get("status") == "locked":
                            trade_log(f"⚠️ [风控] {sym} 触及风控线 ({risk_line:.2f}),但 T+1 锁定，明日卖出")
                        else:
                            trade_log(f"🔴 [风控触发] {sym} 现价 {current_price} 跌破风控线 {risk_line:.2f},强制卖出!")
                            risk_sells.append({
                                "symbol": sym,
                                "name": b.get("name", sym),
                                "action": "SELL",
                                "score": 0,
                                "reason": f"风控触发:跌破动态防守线 {risk_line:.2f}",
                                "logic": "BROKEN",
                                "is_risk_sell": True,
                                "trigger_price": risk_line
                            })
                            # 避免重复 (一只票只卖一次)
                            break
        
        # 将风控信号注入到 AI 分析结果中，确保被循环处理
        if risk_sells:
            for rs in risk_sells:
                # 检查是否 AI 已经建议卖出，避免重复
                existing = [p for p in ai_result.get("position_analysis", []) if p.get("symbol") == rs["symbol"]]
                if not existing:
                    ai_result.setdefault("position_analysis", []).append(rs)

        if ai_result and "error" in ai_result:
            trade_log(f"[AI] 错误: {ai_result['error']}")
            return

        pos_analysis = ai_result.get("position_analysis", [])
        candidates = []  # 初始化信号列表
        
        # ★ 持仓分析循环 (优化日志输出)
        for pa in pos_analysis:
            sym = pa.get("symbol", "")
            action = pa.get("action", "HOLD")
            thesis = pa.get("thesis_status", "VALID")

            # ★ 获取股票名称并注入 (解决日志无名称问题)
            pos_entry = pf.get("positions", {}).get(sym, [])
            if isinstance(pos_entry, list):
                name = pos_entry[0].get("name", sym) if pos_entry else sym
            else:
                name = pos_entry.get("name", sym)
            pa["name"] = name

            # ★ 日志优化：正常 HOLD 只计数，异常才打印
            if action == "HOLD" and thesis == "VALID":
                # 静默计数，不打印
                pass
            else:
                trade_log(f"⚠️ [持仓警报] {sym}({name}): {action} (逻辑={thesis})")

            # ★ 防御 AI 幻觉:如果 AI 分析的标的不在实际持仓中,直接忽略
            if sym not in pf.get("positions", {}):
                trade_log(f"[AI] 忽略不存在的持仓分析: {sym}")
                continue

            if action == "SELL" and thesis == "BROKEN":
                trade_log(f"[AI] 逻辑破坏 {sym},触发卖出")
                # 获取股票名称(在持仓被删除前)
                pos_entry = pf.get("positions", {}).get(sym, [])
                if isinstance(pos_entry, list):
                    sell_name = pos_entry[0].get("name", sym) if pos_entry else sym
                else:
                    sell_name = pos_entry.get("name", sym)

                result = execute_trade({"symbol": sym, "action": "SELL", "score": 30, "reason": "逻辑破坏:AI 判定逻辑已失效", "logic": "BROKEN"}, pf, current_data, market_stage)

                # 记录卖出执行结果到历史分析数据库
                if result.get("executed", False):
                    executed_count += 1
                    candidates.append({
                        "symbol": sym,
                        "name": sell_name,
                        "action": "SELL",
                        "reason": pa.get("reason", "逻辑破坏"),
                        "risk_result": "已卖出"
                    })

        # ★ 汇总打印：持仓检查完成
        trade_log(f"[AI] 持仓检查完成: {len(pos_analysis)} 只 (全部健康 ✅)")

        # 将 AI 推荐的新信号追加到列表
        new_candidates = ai_result.get("candidates", [])
        
        # ★ 智能意图校正引擎 (AI Intent Corrector)
        # 核心逻辑：当 AI 搞混代码和名字时，尝试猜测它的真实意图并修正，而不是直接拦截。
        # 例如：AI 想买“京能电力”，但给了错代码，系统通过名字反查正确代码。
        
        # 建立 名字->代码 反向索引
        name_to_sym_map = {}
        for s, d in current_data.items():
            n = d.get("name")
            if n: name_to_sym_map[n] = s
            
        valid_candidates = []
        for cand in new_candidates:
            sym = cand.get("symbol", "")
            ai_name = cand.get("name", "")
            
            final_sym = None
            final_name = ai_name
            
            # 情况 1：代码在池子里
            if sym in current_data:
                real_name = current_data[sym].get("name")
                
                # 如果 AI 给的代码和名字对不上
                if ai_name and real_name and real_name != ai_name:
                    # 检查 AI 说的名字是否在池子里有对应的真代码
                    if ai_name in name_to_sym_map:
                        # 意图是名字，代码写错了 -> 修正代码
                        final_sym = name_to_sym_map[ai_name]
                        trade_log(f"[校正] AI 代码幻觉：想买 '{ai_name}' 但给错代码 ({sym} 其实是 {real_name}) -> 修正为 {final_sym}")
                    else:
                        # 名字也找不到，说明纯瞎编 -> 丢弃
                        trade_log(f"[拦截] AI 幻觉：代码 {sym} ({real_name}) 与名称 '{ai_name}' 均无法对应 -> 丢弃")
                        continue
                else:
                    final_sym = sym
            
            # 情况 2：代码不在池子里（可能是停牌或代码错误）
            else:
                # 尝试通过名字找人
                if ai_name in name_to_sym_map:
                    final_sym = name_to_sym_map[ai_name]
                    trade_log(f"[校正] AI 代码失效 ({sym})，通过名称 '{ai_name}' 反查锁定 {final_sym}")
                else:
                    trade_log(f"[拦截] AI 瞎编：找不到代码 {sym} 且名称 '{ai_name}' 不在监控池中 -> 丢弃")
                    continue
            
            if final_sym:
                cand["symbol"] = final_sym
                # 确保名字是最新的
                if final_sym in current_data:
                    cand["name"] = current_data[final_sym].get("name")
                valid_candidates.append(cand)
        
        # ★ 日志优化：删除冗余的中间过程打印
        # trade_log(f"[AI] 信号处理：...")  # 已删除
        # trade_log(f"[AI] 原始候选信号: ...")  # 已删除
        candidates.extend(valid_candidates)

        # 遍历所有信号(包含已执行的卖出和新买入信号)
        for cand in candidates:
            sym = cand.get("symbol", "")
            name = cand.get("name", "")
            action = str(cand.get("action", "HOLD")).upper()
            score = float(cand.get("score", 0))

            # ★ 清洗并补齐股票代码前缀 (去除 .SZ/.SH 后缀)
            if sym and '.' in sym:
                sym = sym.split('.')[0]

            if sym and not sym.startswith(('sh', 'sz')):
                if sym.startswith('6'): sym = 'sh' + sym
                elif sym.startswith(('0', '3')): sym = 'sz' + sym
            elif sym and sym.startswith('sh') and len(sym) >= 8 and sym[2] in ('0', '3'):
                # 修复错误前缀:sh301175 -> sz301175
                sym = 'sz' + sym[2:]

            trade_log(f"[AI] 信号: {name}({sym}) 动作={action} 评分={score}")

            # ★ 加仓逻辑:检查是否已持仓,决定是加仓还是拒绝
            if action == "BUY":
                existing_pos = pf.get("positions", {}).get(sym, [])
                if existing_pos:
                    # 已持仓,检查加仓条件
                    batches = existing_pos if isinstance(existing_pos, list) else [existing_pos]
                    total_qty = sum(b.get("qty", 0) for b in batches)
                    avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty if total_qty > 0 else 0
                    current_price = batches[0].get("current_price", avg_cost)
                    pos_mv = total_qty * current_price

                    # 计算总资产和单票占比
                    total_assets = pf.get("cash", 0) + sum(
                        sum(b.get("qty", 0) * b.get("current_price", b.get("cost_price", 0)) for b in (e if isinstance(e, list) else [e]))
                        for e in pf.get("positions", {}).values()
                    )
                    pos_pct = pos_mv / total_assets * 100 if total_assets > 0 else 0

                    # 加仓条件检查
                    # 1. 单票仓位上限 15%
                    # 2. 评分足够高(>=85)
                    # 3. 加仓预算减半(更保守)
                    # 注: 已移除T+1加仓限制(A股T+1仅限制卖出,不限制买入)

                    if pos_pct >= 15:
                        trade_log(f"[风控] {sym} 单票仓位已达{pos_pct:.1f}%上限,拒绝加仓")
                        cand["risk_result"] = f"仓位上限({pos_pct:.1f}%>=15%"
                        continue

                    # 涨跌停检查(加仓也受限制,基于真实涨停价)
                    limit_up_price = current_data.get(sym, {}).get("limit_up_price", 0)
                    current_price = batches[0].get("current_price", avg_cost)
                    if limit_up_price > 0 and current_price >= limit_up_price * 0.99:
                        trade_log(f"[风控] {sym} 现价{current_price} >= 涨停价{limit_up_price}*0.99,涨停无法加仓")
                        cand["risk_result"] = f"涨停限制(涨停价{limit_up_price})"
                        continue

                    if score < 85:
                        trade_log(f"[风控] {sym} 加仓评分不足({score}<85)")
                        cand["risk_result"] = f"加仓评分不足({score}<85"
                        continue

                    # 标记为加仓信号(后续处理会调整预算)
                    cand["is_add_position"] = True
                    trade_log(f"[加仓] {sym}({name}) 允许加仓,当前仓位{pos_pct:.1f}%,评分{score}")

            if action == "BUY" and score >= 60:
                result = execute_trade(cand, pf, current_data, market_stage)
                # 统计实际成交
                if result.get("executed", False):
                    executed_count += 1
                # 把风控结果保存到 candidates 中(供前端显示)
                cand["risk_result"] = result.get("reason", "")
                if not result.get("executed", False):
                    trade_log(f"[风控] {sym} {name} 被拦截:{result.get('reason', '')}")
            elif action == "BUY" and score < 60:
                trade_log(f"[风控] {sym} {name} 评分不足 {score}/60")
                cand["risk_result"] = f"评分不足 ({score:.0f}/60)"
                pf.setdefault("risk_logs", []).append({
                    "time": __import__('datetime').datetime.now().strftime("%H:%M:%S"),
                    "symbol": sym, "name": name, "action": "BUY",
                    "reason": f"AI 评分不足 {score:.0f}/60",
                    "risk_level": "INFO",
                })
            else:
                cand["risk_result"] = "未触发"
                trade_log(f"[AI] 信号: {name} 动作={action} 评分={score}")

        # 限制 risk_logs 数量
        if len(pf.get("risk_logs", [])) > 50:
            pf["risk_logs"] = pf["risk_logs"][-50:]

        # 记录到 ai_log(供前端显示)- 必须在 save_json 之前
        ai_log_entry = {
            "time": __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "reasoning": ai_result.get("market_analysis", {}).get("trend", ""),
            "stage": ai_result.get("market_analysis", {}).get("stage", ""),
            "position_analysis": ai_result.get("position_analysis", []),
            "signals": candidates,
            "signals_count": len(candidates),
        }
        pf.setdefault("ai_log", []).append(ai_log_entry)
        if len(pf["ai_log"]) > 20: pf["ai_log"] = pf["ai_log"][-20:]

        update_market_json(current_data, pf, key_events, indices, news)
        save_json(PORTFOLIO_PATH, pf)

        # 记录到数据库(仅当有信号或有卖出动作时才记录,避免空记录泛滥)
        if candidates or any(pa.get("action") == "SELL" for pa in pos_analysis):
            from v2.db import save_ai_analysis
            save_ai_analysis({
                "reasoning": ai_result.get("market_analysis", {}).get("trend", ""),
                "events": __import__('json').dumps(key_events[:5], ensure_ascii=False) if key_events else "",
                "signals": candidates,
                "signals_count": len(candidates),
                "executed": executed_count,
                "model": pf.get("ai_model", "qwen-plus"),
            })

        trade_log(f"[周期] 执行完毕。生成信号: {len(candidates)} 个")

        # 更新收益曲线
        try:
            # 🆕 指向 user_data
            pnl_hist_path = USER_DATA_DIR / "pnl_history.json"
            pnl_hist = {"history": []}
            if pnl_hist_path.exists():
                with open(pnl_hist_path, encoding='utf-8') as f:
                    pnl_hist = json.load(f)
            total = cash + sum(b.get("qty",0)*b.get("current_price",b.get("cost_price",0)) for batches in pf.get("positions", {}).values() for b in (batches if isinstance(batches, list) else [batches]))
            init = pf.get("initial_cash")
            if init is None:
                trade_log("[WARN] initial_cash 未配置，跳过盈亏统计")
                return
            pnl_hist.setdefault("history", []).append({
                "time": __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_assets": round(total, 2),
                "cash": round(cash, 2),
                "pnl": round(total - init, 2),
                "pnl_pct": round((total - init) / init * 100, 2) if init else 0,
                "positions_count": len(pf.get("positions", {})),
            })
            # 最多保留1000条
            if len(pnl_hist["history"]) > 1000: pnl_hist["history"] = pnl_hist["history"][-1000:]
            with open(pnl_hist_path, 'w', encoding='utf-8') as f:
                json.dump(pnl_hist, f, ensure_ascii=False, indent=2)
        except: pass

    except Exception as e:
        trade_log(f"[周期] 错误: {e}")
        __import__('traceback').print_exc()

def run_manual_analysis(stock: str = None):
    """
    手动分析单只股票
    """
    trade_log(f"[手动] 分析 {stock or '大盘'}...")
    run_cycle()

def set_mode(mode: str):
    """
    设置运行模式: AUTO / MANUAL
    """
    global _mode
    _mode = mode
    trade_log(f"[系统] 模式已切换至 {mode}")

def get_trading_phase():
    """
    返回当前交易阶段和是否可执行交易
    集合竞价是"市场情绪预告片",不是正式交易。
    - 09:15-09:20 可挂可撤,假动作多,适合观察
    - 09:20-09:25 可挂不可撤,真金白银,最能看出主力意图
    - 09:25 开盘价已出,不可交易,但能判断强弱
    - 09:30 连续竞价开始,正式交易
    """
    import datetime
    now = datetime.datetime.now()
    m = now.hour * 60 + now.minute

    if m < 555:   return '盘前准备', False          # 09:15前
    if m < 560:   return '集合竞价(可挂可撤)', False  # 09:15-09:19 假动作多
    if m < 565:   return '竞价锁定(不可撤单)', False  # 09:20-09:24 真金白银
    if m < 570:   return '开盘价已出(等连续竞价)', False  # 09:25-09:29
    if m < 690:   return '上午连续竞价', True         # 09:30-11:30 正式交易
    if m < 780:   return '午间休市', False            # 11:30-13:00
    if m < 900:   return '下午连续竞价', True         # 13:00-15:00 正式交易
    if m < 930:   return '盘后整理', False            # 15:00-15:30
    return '已收盘', False

def is_trading_time(symbol=None):
    """
    A 股现行标准交易时间 (周一至周五)
    - 上午: 09:15 (竞价) - 11:30
    - 下午: 13:00 - 15:00 (连续竞价)
    - 盘后固定价格: 15:05 - 15:30 (仅科创板688/创业板300/301)
    - 11:30 - 13:00 午休休眠
    
    参数:
        symbol: 股票代码，用于判断是否支持盘后交易
    """
    import datetime
    now = datetime.datetime.now()
    wd = now.weekday()
    if wd >= 5: return False  # 周末休市

    m = now.hour * 60 + now.minute
    # 上午段 (555=09:15, 690=11:30) OR 下午段 (780=13:00, 900=15:00)
    normal_trading = (555 <= m <= 690) or (780 <= m <= 900)
    
    # 盘后固定价格交易 (905=15:05, 930=15:30) - 仅科创板/创业板
    after_hours_trading = False
    if 905 <= m <= 930 and symbol:
        sym_upper = symbol.upper()
        # 科创板(688)或创业板(300/301/302)支持盘后固定价格
        if sym_upper.startswith('SH688') or sym_upper.startswith('SZ300') or sym_upper.startswith('SZ301') or sym_upper.startswith('SZ302'):
            after_hours_trading = True
    
    return normal_trading or after_hours_trading

def trading_loop(base_interval: int = 90):
    """🟢 交易 AI 独立线程 (高优先级,永不阻塞)"""
    global _running
    trade_log(f"[交易 AI] 线程已启动,间隔 {base_interval} 秒 (优先级:高)。")

    warned_holiday = False

    while _running:
        if not is_trading_time():
            if not warned_holiday:
                trade_log("[交易 AI] 正在休市,等待开盘自动运行...")
                warned_holiday = True
            __import__('time').sleep(60)
            continue

        # 进入交易时间,重置提示
        warned_holiday = False

        t0 = __import__('time').time()
        try:
            run_cycle(research_mode=False)
        except Exception as e:
            trade_log(f"[交易线程] 错误: {e}")
            __import__('traceback').print_exc()

        elapsed = __import__('time').time() - t0
        sleep_sec = max(base_interval - elapsed, 1)  # 动态休眠

        for _ in range(int(sleep_sec)):
            if not _running: break
            __import__('time').sleep(1)

def research_loop():
    """🔵 研究 AI 独立后台线程 (生物钟调度,关键节点唤醒)"""
    global _running
    trade_log("[研究 AI] 独立后台已启动,正在后台运行中... (等待触发节点)")

    last_run_date = None
    executed_slots = set()  # 记录今天已完成的节点

    while _running:
        now = __import__('datetime').datetime.now()

        # ★ 启动补检:如果首次启动时已过早盘时间但还没执行,立即补做
        if last_run_date is None:
            m_now = now.hour * 60 + now.minute
            if m_now <= 570 and "m_pre" not in executed_slots:  # 09:30 前都可补
                slot_to_run = "m_pre"
                slot_name = "早盘前预判(补)"
                trade_log(f"[研究 AI] 启动补检:错过早盘窗口,立即补做 [{slot_name}]")

        date_str = now.strftime("%Y-%m-%d")
        wd = now.weekday()  # 0-4 Mon-Fri, 5-6 Sat-Sun

        # 跨天重置
        if last_run_date != date_str:
            executed_slots = set()
            last_run_date = date_str

        m = now.hour * 60 + now.minute
        slot_to_run = None
        slot_name = ""

        # === 调度逻辑 ===
        if wd >= 5:  # 周末
            if 600 <= m <= 660 and "weekend" not in executed_slots:  # 10:00-11:00
                slot_to_run = "weekend"
                slot_name = "周末复盘"
        else:  # 工作日
            # 1. 早盘前 (08:30-09:25) -> 覆盖集合竞价到开盘
            if 510 <= m <= 565 and "m_pre" not in executed_slots:
                slot_to_run = "m_pre"
                slot_name = "早盘前预判"
            # 2. 上午盘后 (11:35-12:00) -> 11:30 收盘后
            elif 695 <= m <= 720 and "am_post" not in executed_slots:
                slot_to_run = "am_post"
                slot_name = "上午盘后复盘"
            # 3. 下午盘前 (12:30-12:55) -> 13:00 开盘前
            elif 750 <= m <= 775 and "pm_pre" not in executed_slots:
                slot_to_run = "pm_pre"
                slot_name = "下午盘前策略"
            # 4. 收盘后 (15:35-16:00) -> 15:30 盘后交易结束后
            elif 935 <= m <= 960 and "pm_post" not in executed_slots:
                slot_to_run = "pm_post"
                slot_name = "收盘后深度复盘"

        if slot_to_run:
            trade_log(f"[研究 AI] 触发节点 [{slot_name}],开始调用进行工作...")
            try:
                pf = load_json(PORTFOLIO_PATH)
                # ★ 修复:传入 pf 而不是 {},让后台自动触发的研究 AI 也能看到持仓
                result = call_research_ai(pf, pf, slot_name=slot_to_run)

                if "error" not in result:
                    trade_log(f"[研究 AI] [{slot_name}] 工作完成。提示: {result.get('strategy_hint', '')[:80]}")

                    # 检查是否有复盘日记并入库
                    reflection = result.get("daily_reflection")
                    if reflection:
                        # ★ 修复:将 next_day_watchlist 合并进 reflection 持久化,否则次日无法加载"作业"
                        wl = result.get('next_day_watchlist', [])
                        if wl:
                            reflection['next_day_watchlist'] = wl
                        try:
                            from v2.db import get_conn
                            conn = get_conn()
                            c = conn.cursor()
                            date_val = reflection.get("date", date_str)
                            c.execute("INSERT OR REPLACE INTO daily_reflection (date, reflection_json, created_at) VALUES (?, ?, ?)",
                                      (date_val, json.dumps(reflection, ensure_ascii=False), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                            conn.commit()
                            conn.close()
                            trade_log(f"[研究 AI] 今日复盘日记已成功写入数据库。")

                            # ★ 同步写入禁忌模式 (Negative Patterns)
                            patterns = result.get('negative_patterns', [])
                            if patterns:
                                from v3.experience_layer import save_pattern
                                for p in patterns:
                                    name = p.get('pattern_name', '')
                                    condition = p.get('condition', '')
                                    lesson = p.get('lesson', '')
                                    if name and condition:
                                        save_pattern(name, condition, lesson, 0.85)
                                        trade_log(f"[经验层] 自动登记禁忌模式:{name}")
                        except Exception as e:
                            trade_log(f"[研究 AI] 复盘日记入库失败: {e}")

                else:
                    trade_log(f"[研究 AI] [{slot_name}] 异常: {result.get('error')}")

                executed_slots.add(slot_to_run)
            except Exception as e:
                trade_log(f"[研究 AI] [{slot_name}] 执行错误: {e}")

        # 每分钟检查一次
        __import__('time').sleep(60)

def _main_loop():
    """旧版兼容"""
    global _running
    while _running:
        try:
            current_data = fetch_quotes()
            global _market_breadth_cache
            _market_breadth_cache = fetch_market_breadth()
            indices = fetch_indices()
            news = fetch_news()
            pf = load_json(PORTFOLIO_PATH)
            update_market_json(current_data, pf, [], indices, news)
            time.sleep(60)
        except Exception as e:
            time.sleep(30)
