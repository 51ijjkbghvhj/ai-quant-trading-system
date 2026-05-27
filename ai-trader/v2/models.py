"""v2.0 共享数据模型 - 所有模块通过这些结构通信"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime
import json


@dataclass
class MarketData:
    """数据层输出"""
    timestamp: str
    symbol: str
    name: str
    price: float
    prev_close: float
    open: float
    high: float
    low: float
    volume: float
    amount: float
    change_pct: float
    turnover_rate: float
    sector: str
    sector_strength: float  # 0-100
    market_state: str       # risk_on / risk_off / neutral
    ma5: float = 0.0        # 5日均线
    ma10: float = 0.0       # 10日均线
    limit_up_price: float = 0.0   # 涨停价（实时）
    limit_down_price: float = 0.0 # 跌停价（实时）

    def to_dict(self):
        return asdict(self)


@dataclass
class IndexData:
    """指数数据"""
    timestamp: str
    symbol: str
    name: str
    price: float
    change_pct: float
    volume: float

    def to_dict(self):
        return asdict(self)


@dataclass
class NewsEvent:
    """新闻事件（仅标签化）"""
    timestamp: str
    title: str
    source: str
    impact: str           # positive / negative / neutral
    sectors: List[str]
    url: str
    relevance_score: float  # 0-1

    def to_dict(self):
        return asdict(self)


@dataclass
class Signal:
    """策略层输出 - 标准化交易信号"""
    timestamp: str
    symbol: str
    name: str
    action: str            # BUY / SELL / HOLD
    score: float           # 0-100
    confidence: float      # 0-1
    position_ratio: float  # 建议仓位比例 0-1
    reason: str
    holding_days_expectation: int  # 预期持仓天数
    price: float
    qty: int
    is_leader: bool = False  # 是否为板块龙头

    def to_dict(self):
        return asdict(self)


@dataclass
class RiskResult:
    """风控层输出"""
    timestamp: str
    symbol: str
    approved: bool
    action_override: Optional[str]   # SELL / HOLD / REDUCE_50% / None
    reason: str
    risk_level: str                  # LOW / MEDIUM / HIGH / CRITICAL
    original_signal: Optional[dict]  # 原始信号引用
    sell_qty: int = 0                # 分批止盈时指定卖出数量

    def to_dict(self):
        return asdict(self)


@dataclass
class Order:
    """执行层输入"""
    timestamp: str
    symbol: str
    name: str
    direction: str         # buy / sell
    price: float
    qty: int
    amount: float
    fee: float
    reason: str
    signal_score: float
    risk_approved: bool

    def to_dict(self):
        return asdict(self)


@dataclass
class ExecutionResult:
    """执行层输出"""
    timestamp: str
    order: dict
    success: bool
    execution_price: float
    pnl: float             # 本次盈亏（卖出时）
    error: str

    def to_dict(self):
        return asdict(self)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    symbol: str
    action: str
    strategy_score: float
    risk_result: str       # approved / rejected / override
    execution_price: float
    position_change: str
    pnl: str
    reason: str

    def to_dict(self):
        return asdict(self)


@dataclass
class PortfolioState:
    """账户状态"""
    timestamp: str
    initial_cash: float
    cash: float
    positions: dict        # {symbol: {name, qty, cost_price, current_price, ...}}
    total_assets: float
    total_pnl: float
    total_pnl_pct: float
    position_ratio: float
    transactions: list
    ai_log: list
    watchlist: list

    def to_dict(self):
        return asdict(self)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now().strftime("%Y-%m-%d")
