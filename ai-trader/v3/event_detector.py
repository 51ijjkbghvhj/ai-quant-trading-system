"""Event Detector - 事件检测器
职责：监控市场数据，识别关键变化，生成事件
只在检测到事件时才触发AI调用
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional

# 🆕 动态指向 user_data
BASE_DIR = Path(__file__).resolve().parent.parent.parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = USER_DATA_DIR / "events.db"


@dataclass
class MarketEvent:
    """市场事件"""
    event_type: str       # 事件类型
    symbol: str           # 股票代码
    name: str             # 股票名称
    timestamp: str        # 事件时间
    price: float          # 当前价格
    trigger_value: float  # 触发值
    severity: str         # CRITICAL / HIGH / MEDIUM / LOW
    description: str      # 事件描述
    context: dict         # 相关上下文

    def to_dict(self):
        return asdict(self)


# ── 事件类型定义 ──
class EventType:
    PRICE_BREAKOUT_UP = "price_breakout_up"      # 价格向上突破
    PRICE_BREAKOUT_DOWN = "price_breakout_down"  # 价格向下突破
    MA_CROSS_ABOVE = "ma_cross_above"            # 突破均线
    MA_CROSS_BELOW = "ma_cross_below"            # 跌破均线
    VOLUME_SPIKE = "volume_spike"                # 成交量放大
    SECTOR_STRENGTH_SHIFT = "sector_shift"       # 板块强度突变
    STOP_LOSS_HIT = "stop_loss_hit"              # 触发止损
    TAKE_PROFIT_HIT = "take_profit_hit"          # 触发止盈
    HOLDING_TIMEOUT = "holding_timeout"          # 持仓超时
    INTRADAY_REVERSAL = "intraday_reversal"      # 冲高回落
    HIGH_TURNOVER_STAGNATION = "high_turnover"   # 放量滞涨
    NEW_STOCK_CANDIDATE = "new_candidate"        # 新股候选
    MARKET_SENTIMENT_SHIFT = "sentiment_shift"   # 市场情绪转变


def init_event_db():
    """初始化事件数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        event_type TEXT NOT NULL,
        symbol TEXT,
        name TEXT,
        price REAL,
        trigger_value REAL,
        severity TEXT,
        description TEXT,
        context_json TEXT,
        processed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evt_date ON events(trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evt_type ON events(event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evt_processed ON events(processed)")
    conn.commit()
    conn.close()


def save_event(event: MarketEvent):
    """保存事件到数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT INTO events
        (ts, trade_date, event_type, symbol, name, price, trigger_value,
         severity, description, context_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (event.timestamp, event.timestamp.split(" ")[0],
         event.event_type, event.symbol, event.name,
         event.price, event.trigger_value, event.severity,
         event.description, json.dumps(event.context, ensure_ascii=False)))
    conn.commit()
    conn.close()


def get_unprocessed_events() -> List[dict]:
    """获取未处理的事件"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE processed=0 ORDER BY severity DESC, ts DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_events_processed(event_ids: List[int]):
    """标记事件为已处理"""
    if not event_ids:
        return
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ",".join("?" * len(event_ids))
    conn.execute(f"UPDATE events SET processed=1 WHERE id IN ({placeholders})", event_ids)
    conn.commit()
    conn.close()


def detect_events(current_data: dict, previous_data: dict, portfolio: dict) -> List[MarketEvent]:
    """
    核心函数：对比当前数据和上次数据，检测事件
    current_data: {symbol: {price, high, low, volume, change_pct, turnover_rate, ...}}
    previous_data: {symbol: {price, volume, ...}}
    portfolio: {positions: {symbol: {cost_price, qty, buy_date, ...}}}
    """
    init_event_db()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    events = []
    positions = portfolio.get("positions", {})

    for symbol, cur in current_data.items():
        prev = previous_data.get(symbol, {})
        if not prev or cur.get("price", 0) <= 0:
            continue

        price = cur["price"]
        prev_price = prev.get("price", price)
        change_pct = cur.get("change_pct", 0)
        turnover = cur.get("turnover_rate", 0)
        high = cur.get("high", price)
        low = cur.get("low", price)

        # ── 持仓相关事件 ──
        if symbol in positions:
            pos_entry = positions[symbol]
            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            if not batches: continue
            
            total_qty = sum(b.get("qty", 0) for b in batches)
            if total_qty == 0: continue
            
            # 计算加权平均成本
            avg_cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty
            
            cost = avg_cost
            buy_date = batches[0].get("buy_date", "")
            qty = total_qty

            if cost > 0 and qty > 0:
                pnl_pct = (price - cost) / cost * 100

                # 止损
                if pnl_pct <= -5:
                    events.append(MarketEvent(
                        event_type=EventType.STOP_LOSS_HIT,
                        symbol=symbol, name=cur.get("name", ""),
                        timestamp=ts, price=price,
                        trigger_value=pnl_pct,
                        severity="CRITICAL",
                        description=f"止损触发：浮亏{pnl_pct:.1f}% <= -5%",
                        context={"cost": cost, "pnl_pct": pnl_pct, "qty": qty}
                    ))

                # 止盈
                elif pnl_pct >= 10:
                    events.append(MarketEvent(
                        event_type=EventType.TAKE_PROFIT_HIT,
                        symbol=symbol, name=cur.get("name", ""),
                        timestamp=ts, price=price,
                        trigger_value=pnl_pct,
                        severity="HIGH",
                        description=f"止盈触发：浮盈{pnl_pct:.1f}% >= 10%",
                        context={"cost": cost, "pnl_pct": pnl_pct, "qty": qty}
                    ))

                # 冲高回落
                intraday_high_pct = (high - cost) / cost * 100
                if intraday_high_pct >= 5 and pnl_pct < 2:
                    events.append(MarketEvent(
                        event_type=EventType.INTRADAY_REVERSAL,
                        symbol=symbol, name=cur.get("name", ""),
                        timestamp=ts, price=price,
                        trigger_value=intraday_high_pct,
                        severity="HIGH",
                        description=f"冲高回落：最高涨{intraday_high_pct:.1f}%现仅{pnl_pct:.1f}%",
                        context={"high": high, "high_pct": intraday_high_pct, "current_pct": pnl_pct}
                    ))

                # 放量滞涨
                if turnover > 15 and abs(pnl_pct) < 1:
                    events.append(MarketEvent(
                        event_type=EventType.HIGH_TURNOVER_STAGNATION,
                        symbol=symbol, name=cur.get("name", ""),
                        timestamp=ts, price=price,
                        trigger_value=turnover,
                        severity="MEDIUM",
                        description=f"放量滞涨：换手{turnover:.1f}%涨幅仅{pnl_pct:.1f}%",
                        context={"turnover": turnover, "pnl_pct": pnl_pct}
                    ))

                # 持仓超时
                if buy_date:
                    try:
                        holding_days = (datetime.strptime(ts.split(" ")[0], "%Y-%m-%d") -
                                       datetime.strptime(buy_date, "%Y-%m-%d")).days
                        if holding_days >= 7:
                            events.append(MarketEvent(
                                event_type=EventType.HOLDING_TIMEOUT,
                                symbol=symbol, name=cur.get("name", ""),
                                timestamp=ts, price=price,
                                trigger_value=holding_days,
                                severity="HIGH",
                                description=f"持仓超时：{holding_days}天 >= 7天强制清仓",
                                context={"holding_days": holding_days, "cost": cost, "pnl_pct": pnl_pct}
                            ))
                        elif holding_days >= 5 and price < high:
                            events.append(MarketEvent(
                                event_type=EventType.HOLDING_TIMEOUT,
                                symbol=symbol, name=cur.get("name", ""),
                                timestamp=ts, price=price,
                                trigger_value=holding_days,
                                severity="MEDIUM",
                                description=f"持仓{holding_days}天未创新高（现{price} < 高{high}）",
                                context={"holding_days": holding_days, "high": high}
                            ))
                    except:
                        pass

        # ── 价格突破事件 ──
        price_change = (price - prev_price) / prev_price * 100 if prev_price > 0 else 0

        # 急涨突破（单次检测涨幅>3%）
        if price_change > 3:
            events.append(MarketEvent(
                event_type=EventType.PRICE_BREAKOUT_UP,
                symbol=symbol, name=cur.get("name", ""),
                timestamp=ts, price=price,
                trigger_value=price_change,
                severity="MEDIUM",
                description=f"价格急涨：{price_change:+.1f}%（{prev_price}→{price}）",
                context={"prev_price": prev_price, "change": price_change}
            ))

        # 急跌突破
        elif price_change < -3:
            events.append(MarketEvent(
                event_type=EventType.PRICE_BREAKOUT_DOWN,
                symbol=symbol, name=cur.get("name", ""),
                timestamp=ts, price=price,
                trigger_value=price_change,
                severity="MEDIUM",
                description=f"价格急跌：{price_change:+.1f}%（{prev_price}→{price}）",
                context={"prev_price": prev_price, "change": price_change}
            ))

        # 成交量放大（换手率>10%，且比上次有显著变化）
        prev_turnover = prev.get("turnover_rate", 0)
        if turnover > 10 and (turnover - prev_turnover) > 3:
            events.append(MarketEvent(
                event_type=EventType.VOLUME_SPIKE,
                symbol=symbol, name=cur.get("name", ""),
                timestamp=ts, price=price,
                trigger_value=turnover,
                severity="LOW",
                description=f"成交量放大：换手{turnover:.1f}%（上次{prev_turnover:.1f}%）",
                context={"turnover": turnover, "prev_turnover": prev_turnover, "change_pct": change_pct}
            ))

    # ── 市场情绪转变 ──
    total = len(current_data)
    up_count = sum(1 for d in current_data.values() if d.get("change_pct", 0) > 0)
    up_ratio = up_count / total * 100 if total else 0

    prev_total = len(previous_data)
    prev_up = sum(1 for d in previous_data.values() if d.get("change_pct", 0) > 0)
    prev_ratio = prev_up / prev_total * 100 if prev_total else 0

    ratio_change = up_ratio - prev_ratio
    # 只在变化>20%时触发，且排除首次运行（prev_ratio=0）
    if abs(ratio_change) > 20 and prev_ratio > 0:
        direction = "转暖" if ratio_change > 0 else "转冷"
        events.append(MarketEvent(
            event_type=EventType.MARKET_SENTIMENT_SHIFT,
            symbol="MARKET", name="市场",
            timestamp=ts, price=0,
            trigger_value=ratio_change,
            severity="MEDIUM",
            description=f"市场情绪{direction}：上涨比{prev_ratio:.0f}%→{up_ratio:.0f}%（变化{ratio_change:+.0f}%）",
            context={"prev_ratio": prev_ratio, "curr_ratio": up_ratio, "change": ratio_change}
        ))

    # 保存事件到数据库
    for evt in events:
        save_event(evt)

    return events


def has_critical_events(events: List[MarketEvent]) -> bool:
    """检查是否有需要立即处理的关键事件"""
    return any(e.severity in ("CRITICAL", "HIGH") for e in events)


def group_events_by_symbol(events: List[MarketEvent]) -> dict:
    """按股票代码分组事件"""
    grouped = {}
    for e in events:
        grouped.setdefault(e.symbol, []).append(e)
    return grouped
