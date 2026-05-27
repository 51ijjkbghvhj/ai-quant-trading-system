"""
Kline Fetcher - 真实日 K 线获取模块
数据源：新浪财经 K 线 API
原则：
1. 获取真实的日 K 线数据。
2. 本地计算 MA, MACD, RSI。
3. 内存缓存机制（默认缓存 30 分钟），防止频繁请求被封 IP。
"""
import urllib.request
import json
import time
from datetime import datetime

# 内存缓存：{symbol: {'data': klines, 'time': timestamp}}
_kline_cache = {}

def get_kline_data(symbol: str) -> dict:
    """
    获取某只股票的日 K 线数据及技术指标。
    返回: {'ma5': float, 'ma20': float, 'macd_dif': float, 'macd_dea': float, 'macd_hist': float, 'rsi': float}
    """
    if not symbol:
        return None
    
    # 新浪 API 需要的格式 (sh600000, sz000001)
    if symbol.startswith('sh') or symbol.startswith('sz'):
        sina_symbol = symbol
    else:
        # 如果没有前缀，尝试根据代码判断
        if symbol.startswith('6'):
            sina_symbol = 'sh' + symbol
        elif symbol.startswith(('0', '3')):
            sina_symbol = 'sz' + symbol
        else:
            return None

    # 1. 检查缓存 (30 分钟有效)
    now = time.time()
    if sina_symbol in _kline_cache:
        cache = _kline_cache[sina_symbol]
        if now - cache['time'] < 1800: # 30 mins
            return cache['data']

    try:
        # 2. 请求新浪 K 线 API
        # scale=240 (日线), datalen=35 (取最近 35 天数据以确保指标计算准确)
        url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_symbol}&scale=240&ma=no&datalen=35"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8")
        
        if not raw or raw == "null":
            return None
            
        klines = json.loads(raw)
        
        if len(klines) < 30:
            return None

        closes = [float(k['close']) for k in klines]
        
        # 3. 计算指标
        
        # 计算均线
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        
        # 计算 MACD (12, 26, 9)
        # 使用 EMA
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        current_dif = ema12 - ema26
        
        # 计算历史 DIF 序列以求 DEA
        # DEA = EMA(DIF, 9)
        difs = []
        for i in range(26, len(closes) + 1):
            slice_c = closes[:i]
            d = _ema(slice_c, 12) - _ema(slice_c, 26)
            difs.append(d)
        
        if len(difs) >= 9:
            current_dea = _ema(difs, 9)
        else:
            current_dea = 0 # 数据不足时的降级处理
            
        macd_hist = 2 * (current_dif - current_dea)
        
        # 计算 RSI (6)
        rsi = _calc_rsi(closes, 6)
        
        result = {
            'ma5': round(ma5, 3),
            'ma20': round(ma20, 3),
            'macd_dif': round(current_dif, 4),
            'macd_dea': round(current_dea, 4),
            'macd_hist': round(macd_hist, 4),
            'rsi': round(rsi, 2)
        }
        
        # 写入缓存
        _kline_cache[sina_symbol] = {'data': result, 'time': now}
        return result
        
    except Exception as e:
        # print(f"[KlineFetcher] Error fetching {symbol}: {e}")
        return None

def _ema(data, period):
    """计算指数移动平均线"""
    if len(data) < period:
        return data[-1] if data else 0
    multiplier = 2 / (period + 1)
    # 初始值为 SMA
    ema_val = sum(data[:period]) / period
    for price in data[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val

def _calc_rsi(closes, period=6):
    """计算相对强弱指标 RSI"""
    if len(closes) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    # 计算最近的涨跌幅
    # 从倒数第 period+1 个开始算
    start_index = len(closes) - period - 1
    
    for i in range(start_index, len(closes) - 1):
        diff = closes[i+1] - closes[i]
        if diff > 0: 
            gains.append(diff)
        else: 
            losses.append(abs(diff))
            
    # 如果不够 period 个，就取所有可用的
    # Wilder's smoothing is complex, here use simple average for approximation
    # 或者取最后 period 个 diff
    
    # 重新取最后 period 个 diff 计算
    last_diffs = [closes[i] - closes[i-1] for i in range(len(closes)-period, len(closes))]
    g = sum([d for d in last_diffs if d > 0]) / period
    l = sum([abs(d) for d in last_diffs if d < 0]) / period
    
    if l == 0: return 100
    rs = g / l
    return 100 - (100 / (1 + rs))

def get_raw_klines(symbol: str) -> list:
    """
    获取原始 K 线数据用于绘图
    返回: [{'date':..., 'open':..., 'close':..., 'low':..., 'high':..., 'volume':...}]
    """
    if not symbol or not symbol.startswith(('sh', 'sz')):
        return []

    now = __import__('time').time()
    if symbol in _kline_cache:
        cache = _kline_cache[symbol]
        if now - cache['time'] < 1800:
            return cache.get('raw_data', [])

    try:
        url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=60"
        req = __import__('urllib.request').Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = __import__('urllib.request').urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8")
        if not raw or raw == "null": return []
        
        data = __import__('json').loads(raw)
        # Cache raw data
        if symbol in _kline_cache:
            _kline_cache[symbol]['raw_data'] = data
        else:
            _kline_cache[symbol] = {'data': None, 'time': now, 'raw_data': data}
        return data
    except: return []
