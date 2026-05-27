"""
市场结构压缩层 - Market Structure Engine
职责:将原始股票数据压缩为市场结构摘要
只做聚合,不做判断(判断交给AI)
"""

import json
from collections import defaultdict
from pathlib import Path

# 加载板块映射
SECTOR_MAP_PATH = Path(__file__).parent / "sector_map.json"
_SECTOR_MAP = {}
_STOCK_TO_SECTOR = {}

def _load_sector_map():
    """加载板块映射"""
    global _SECTOR_MAP, _STOCK_TO_SECTOR
    try:
        if SECTOR_MAP_PATH.exists():
            with open(SECTOR_MAP_PATH, encoding="utf-8") as f:
                _SECTOR_MAP = json.load(f)
            # 构建 股票代码 -> 板块 的反向映射
            for sector_id, sector_data in _SECTOR_MAP.items():
                for sym in sector_data.get("stocks", {}):
                    _STOCK_TO_SECTOR[sym] = sector_id
        else:
            print(f"[WARN] sector_map.json not found at {SECTOR_MAP_PATH}, using keyword matching only")
    except Exception as e:
        print(f"[WARN] Failed to load sector_map: {e}, using keyword matching only")

_load_sector_map()


def build_market_structure(current_data: dict) -> dict:
    """
    将200只股票数据压缩为市场结构摘要
    输入: {symbol: {price, change_pct, turnover_rate, volume, ...}}
    输出: 市场结构字典
    """
    if not current_data:
        return {"error": "no_data", "market_stage": "未知", "sentiment": {}, "breadth": {}, "limit_stats": {}, "sectors": [], "dragons": []}

    try:
        # ═══ 1. 板块聚合 ═══
        sectors = _aggregate_sectors(current_data)

        # ═══ 2. 市场情绪 ═══
        sentiment = _calc_sentiment(current_data)

        # ═══ 3. 涨跌停统计 ═══
        limit_stats = _calc_limit_stats(current_data)

        # ═══ 4. Breadth(上涨比例)══
        breadth = _calc_breadth(current_data)

        # ═══ 5. 龙头识别 ═══
        dragons = _identify_dragons(current_data, sectors)

        # ═══ 6. 市场阶段判断(简单规则)══
        market_stage = _judge_stage(sentiment, limit_stats, breadth)

        return {
            "market_stage": market_stage,
            "sentiment": sentiment,
            "breadth": breadth,
            "limit_stats": limit_stats,
            "sectors": sectors[:10],
            "dragons": dragons[:5],
        }
    except Exception as e:
        return {"error": str(e), "market_stage": "未知", "sentiment": {}, "breadth": {}, "limit_stats": {}, "sectors": [], "dragons": []}


def _aggregate_sectors(current_data: dict) -> list:
    """板块聚合:按板块分组,计算板块指标"""
    sector_map = defaultdict(lambda: {
        "stocks": [], "total_change": 0, "up_count": 0,
        "limit_up": 0, "limit_down": 0, "total_volume": 0
    })

    for sym, d in current_data.items():
        if d.get("price", 0) <= 0:
            continue

        name = d.get("name", "")
        sector = _classify_sector(name, sym)

        s = sector_map[sector]
        s["stocks"].append({"symbol": sym, "name": name, "price": d.get("price", 0), "change_pct": d.get("change_pct", 0), "turnover_rate": d.get("turnover_rate", 0)})
        s["total_change"] += d.get("change_pct", 0)
        if d.get("change_pct", 0) > 0:
            s["up_count"] += 1
        if d.get("change_pct", 0) >= 9.9:
            s["limit_up"] += 1
        if d.get("change_pct", 0) <= -9.9:
            s["limit_down"] += 1
        s["total_volume"] += d.get("volume", 0)

    # 转换为列表并排序
    result = []
    for name, stats in sector_map.items():
        count = len(stats["stocks"])
        if count >= 2:  # 至少2只股票才算板块
            # 按涨幅排序，取龙头
            sorted_stocks = sorted(stats["stocks"], key=lambda x: x["change_pct"], reverse=True)
            leader = sorted_stocks[0] if sorted_stocks else None
            
            result.append({
                "name": name,
                "stock_count": count,
                "avg_change": round(stats["total_change"] / count, 2),
                "up_ratio": round(stats["up_count"] / count * 100, 1),
                "limit_up": stats["limit_up"],
                "limit_down": stats["limit_down"],
                "strength": _calc_sector_strength(stats, count),
                "leader": leader,
                "top_stocks": sorted_stocks[:5],  # 前5只股票
            })

    result.sort(key=lambda x: x["strength"], reverse=True)
    return result


def _classify_sector(name: str, sym: str) -> str:
    """板块分类:优先查映射表,再用关键词"""
    # 1. 先查映射表
    if sym in _STOCK_TO_SECTOR:
        sector_id = _STOCK_TO_SECTOR[sym]
        return _SECTOR_MAP.get(sector_id, {}).get("name", "其他")

    # 2. 关键词匹配
    sector_keywords = {
        "半导体": ["半导体", "芯片", "封测", "晶圆", "光刻"],
        "AI/人工智能": ["AI", "人工智能", "智能", "算法", "大模型"],
        "新能源": ["光伏", "风电", "储能", "锂电", "新能源", "太阳能"],
        "消费电子": ["消费电子", "手机", "面板"],
        "汽车": ["汽车", "整车", "零部件"],
        "医药": ["医药", "生物", "疫苗", "创新药"],
        "白酒/消费": ["白酒", "茅台", "五粮液", "汾酒", "食品"],
        "金融": ["银行", "证券", "保险", "金融"],
        "地产": ["地产", "万科", "保利", "金地"],
        "钢铁/资源": ["钢铁", "煤炭", "有色", "铜", "铝", "锂"],
        "军工": ["军工", "国防", "航空", "航天"],
        "电力": ["电力", "电网", "发电", "核电"],
        "通信": ["通信", "5G", "光纤"],
    }

    for sector, keywords in sector_keywords.items():
        for kw in keywords:
            if kw in name:
                return sector

    # 3. 根据代码前缀简单分类
    if sym.startswith("sh688"):
        return "科创板"
    elif sym.startswith("sz300"):
        return "创业板"
    else:
        return "其他"


def _calc_sector_strength(stats: dict, count: int) -> int:
    """计算板块强度 (0-100)"""
    score = 0

    # 上涨比例 (0-40分)
    up_ratio = stats["up_count"] / count if count > 0 else 0
    score += int(up_ratio * 40)

    # 涨停数 (0-30分)
    score += min(stats["limit_up"] * 5, 30)

    # 平均涨幅 (0-30分)
    avg_change = stats["total_change"] / count if count > 0 else 0
    score += min(max(int(avg_change * 3), 0), 30)

    return min(score, 100)


def _calc_sentiment(current_data: dict) -> dict:
    """计算市场情绪"""
    total = 0
    up = 0
    down = 0
    flat = 0
    total_change = 0

    for d in current_data.values():
        if d.get("price", 0) <= 0:
            continue
        total += 1
        chg = d.get("change_pct", 0)
        total_change += chg
        if chg > 0:
            up += 1
        elif chg < 0:
            down += 1
        else:
            flat += 1

    avg_change = total_change / total if total > 0 else 0
    up_ratio = up / total * 100 if total > 0 else 0

    # 情绪等级
    if up_ratio >= 80 and avg_change > 3:
        level = "极度乐观"
    elif up_ratio >= 65:
        level = "乐观"
    elif up_ratio >= 50:
        level = "中性偏多"
    elif up_ratio >= 35:
        level = "中性偏空"
    elif up_ratio >= 20:
        level = "悲观"
    else:
        level = "极度悲观"

    return {
        "level": level,
        "up_ratio": round(up_ratio, 1),
        "avg_change": round(avg_change, 2),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "total_count": total,
    }


def _calc_limit_stats(current_data: dict) -> dict:
    """涨跌停统计"""
    limit_up = []
    limit_down = []

    for sym, d in current_data.items():
        if d.get("price", 0) <= 0:
            continue
        chg = d.get("change_pct", 0)
        if chg >= 9.9:
            limit_up.append({"symbol": sym, "name": d.get("name", ""), "change_pct": chg})
        elif chg <= -9.9:
            limit_down.append({"symbol": sym, "name": d.get("name", ""), "change_pct": chg})

    limit_up.sort(key=lambda x: x["change_pct"], reverse=True)
    limit_down.sort(key=lambda x: x["change_pct"])

    return {
        "limit_up_count": len(limit_up),
        "limit_down_count": len(limit_down),
        "limit_up": limit_up[:10],  # 只取前10
        "limit_down": limit_down[:10],
    }


def _calc_breadth(current_data: dict) -> dict:
    """Breadth - 上涨比例"""
    total = 0
    up = 0
    strong_up = 0  # 涨幅>5%
    strong_down = 0  # 跌幅>5%

    for d in current_data.values():
        if d.get("price", 0) <= 0:
            continue
        total += 1
        chg = d.get("change_pct", 0)
        if chg > 0:
            up += 1
        if chg > 5:
            strong_up += 1
        elif chg < -5:
            strong_down += 1

    return {
        "up_ratio": round(up / total * 100, 1) if total > 0 else 0,
        "strong_up_ratio": round(strong_up / total * 100, 1) if total > 0 else 0,
        "strong_down_ratio": round(strong_down / total * 100, 1) if total > 0 else 0,
        "total": total,
    }


def _identify_dragons(current_data: dict, sectors: list) -> list:
    """识别各板块龙头 - 加权评分"""
    dragons = []
    
    # 按板块分组
    sector_stocks = defaultdict(list)
    for sym, d in current_data.items():
        if d.get("price", 0) <= 0:
            continue
        name = d.get("name", "")
        sector = _classify_sector(name, sym)
        sector_stocks[sector].append((sym, d))
    
    # 每个板块取评分最高的
    for sector, stocks in sector_stocks.items():
        if len(stocks) < 2:
            continue
        
        # 计算每只股票的龙头评分
        scored = []
        for sym, d in stocks:
            chg = d.get("change_pct", 0)
            turnover = d.get("turnover_rate", 0)
            volume = d.get("volume", 0)
            
            # 加权评分
            # 涨幅 0.3 + 换手 0.3 + 成交量 0.2 + 涨停加分 0.2
            score = 0
            score += min(chg / 20 * 30, 30)  # 涨幅分 (max 30)
            score += min(turnover / 20 * 30, 30)  # 换手分 (max 30)
            score += min(volume / 1000000 * 20, 20)  # 成交量分 (max 20)
            if chg >= 9.9:
                score += 20  # 涨停加分
            
            scored.append((sym, d, score))
        
        # 取评分最高的
        scored.sort(key=lambda x: x[2], reverse=True)
        if scored:
            sym, d, score = scored[0]
            dragons.append({
                "symbol": sym,
                "name": d.get("name", ""),
                "sector": sector,
                "price": d.get("price", 0),
                "change_pct": d.get("change_pct", 0),
                "turnover_rate": d.get("turnover_rate", 0),
                "score": round(score, 1),
            })
    
    # 按评分排序
    dragons.sort(key=lambda x: x["score"], reverse=True)
    return dragons[:10]


def _judge_stage(sentiment: dict, limit_stats: dict, breadth: dict) -> str:
    """判断市场阶段"""
    up_ratio = breadth.get("up_ratio", 0)
    limit_up_count = limit_stats.get("limit_up_count", 0)
    limit_down_count = limit_stats.get("limit_down_count", 0)

    if limit_up_count > 50 and up_ratio > 75:
        return "高潮"
    elif limit_up_count > 20 and up_ratio > 60:
        return "升温"
    elif up_ratio > 50:
        return "震荡偏多"
    elif up_ratio > 40:
        return "震荡"
    elif up_ratio > 25:
        return "震荡偏空"
    elif limit_down_count > 20:
        return "恐慌"
    else:
        return "低迷"


def format_for_ai(structure: dict, key_events: list = None) -> str:
    """
    将市场结构格式化为AI输入文本
    结构摘要 + Top5关键事件
    """
    lines = []

    # 市场阶段
    lines.append(f"【市场阶段】{structure.get('market_stage', '未知')}")

    # 情绪
    sent = structure.get("sentiment", {})
    lines.append(f"【市场情绪】{sent.get('level', '')} | 上涨比{sent.get('up_ratio', 0)}% | 均涨幅{sent.get('avg_change', 0)}%")

    # Breadth
    breadth = structure.get("breadth", {})
    lines.append(f"【强度】上涨{breadth.get('up_ratio', 0)}% | 强涨{breadth.get('strong_up_ratio', 0)}% | 强跌{breadth.get('strong_down_ratio', 0)}%")

    # 涨跌停
    ls = structure.get("limit_stats", {})
    lu = ls.get("limit_up_count", 0)
    ld = ls.get("limit_down_count", 0)
    lines.append(f"【涨跌停】涨停{lu}只 | 跌停{ld}只")

    # === 风险指标 (新增) ===
    breadth = structure.get("breadth", {})
    strong_down = breadth.get("strong_down_ratio", 0) # 跌幅>5%比例
    
    risk_warning = []
    if ld > 10: risk_warning.append("跌停潮")
    if strong_down > 15: risk_warning.append("亏钱效应扩散")
    if lu > 0 and ld / lu > 0.2: risk_warning.append("炸板率高/分歧大")
    
    if risk_warning:
        lines.append(f"⚠️【高危风险】{', '.join(risk_warning)}")
    else:
        lines.append("✅【环境安全】无显著风险")


    # 板块(前5)
    sectors = structure.get("sectors", [])
    if sectors:
        lines.append("【板块强度】")
        for s in sectors[:5]:
            lines.append(f"  {s['name']}: 强度{s['strength']} | 涨停{s['limit_up']} | 上涨比{s['up_ratio']}%")

    # 龙头(前5)
    dragons = structure.get("dragons", [])
    if dragons:
        lines.append("【龙头股】")
        for d in dragons[:5]:
            lines.append(f"  {d['name']}({d['sector']}): {d['change_pct']:+.1f}% 换手{d['turnover_rate']:.1f}%")

    # Top5关键事件(补充上下文)
    if key_events:
        lines.append("【关键事件】")
        for e in key_events[:5]:
            lines.append(f"  {e}")

    return "\n".join(lines)


def extract_key_events(current_data: dict, limit_stats: dict) -> list:
    """
    从市场数据中提取关键事件
    用于补充市场结构摘要
    """
    events = []

    # 1. 涨停龙头(涨幅最高的3只)
    limit_up = limit_stats.get("limit_up", [])
    for stock in limit_up[:3]:
        events.append(f"涨停: {stock['name']}({stock['symbol']}) +{stock['change_pct']:.1f}%")

    # 2. 跌停股(跌幅最大的2只)
    limit_down = limit_stats.get("limit_down", [])
    for stock in limit_down[:2]:
        events.append(f"跌停: {stock['name']}({stock['symbol']}) {stock['change_pct']:.1f}%")

    # 3. 异常换手(换手率>20%的股票)
    high_turnover = [(sym, d) for sym, d in current_data.items()
                     if d.get('turnover_rate', 0) > 20 and d.get('price', 0) > 0]
    high_turnover.sort(key=lambda x: x[1].get('turnover_rate', 0), reverse=True)
    for sym, d in high_turnover[:2]:
        events.append(f"异常换手: {d.get('name','')}({sym}) 换手{d.get('turnover_rate',0):.1f}% +{d.get('change_pct',0):.1f}%")

    return events
