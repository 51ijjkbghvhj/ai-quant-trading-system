"""
Position Lifecycle Manager - 仓位生命周期管理
职责: 管理每个持仓的生命周期状态
状态: BUILDING → HOLDING → EXITING → COOLDOWN

v1.0 - 2026-05-15
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from enum import Enum


class PositionState(Enum):
    """仓位状态"""
    BUILDING = "BUILDING"      # 建仓期（刚买入，观察中）
    HOLDING = "HOLDING"        # 持有期（逻辑成立，继续持有）
    EXITING = "EXITING"        # 退出期（逻辑弱化，准备退出）
    COOLDOWN = "COOLDOWN"      # 冷静期（刚卖出，禁止重新买入）


class MarketState(Enum):
    """市场状态"""
    ICE = "ICE"                # 冰点
    RECOVERY = "RECOVERY"      # 修复
    EXPANSION = "EXPANSION"    # 发酵
    EUPHORIA = "EUPHORIA"      # 高潮
    COLLAPSE = "COLLAPSE"      # 退潮
    CHAOS = "CHAOS"            # 混沌


class ThesisStatus(Enum):
    """交易逻辑状态"""
    VALID = "VALID"            # 逻辑有效
    WEAKENING = "WEAKENING"    # 逻辑弱化
    BROKEN = "BROKEN"          # 逻辑破坏


# 市场状态转换规则（需要连续3次确认）
MARKET_STATE_TRANSITIONS = {
    MarketState.ICE: [MarketState.RECOVERY, MarketState.ICE],
    MarketState.RECOVERY: [MarketState.EXPANSION, MarketState.ICE, MarketState.RECOVERY],
    MarketState.EXPANSION: [MarketState.EUPHORIA, MarketState.COLLAPSE, MarketState.EXPANSION],
    MarketState.EUPHORIA: [MarketState.COLLAPSE, MarketState.EUPHORIA],
    MarketState.COLLAPSE: [MarketState.ICE, MarketState.CHAOS, MarketState.COLLAPSE],
    MarketState.CHAOS: [MarketState.ICE, MarketState.RECOVERY, MarketState.CHAOS],
}

# 仓位状态转换规则
POSITION_STATE_TRANSITIONS = {
    PositionState.BUILDING: [PositionState.HOLDING, PositionState.EXITING],
    PositionState.HOLDING: [PositionState.EXITING, PositionState.HOLDING],
    PositionState.EXITING: [PositionState.COOLDOWN],
    PositionState.COOLDOWN: [PositionState.BUILDING],  # 冷静期结束后可以重新建仓
}

# 时间配置（分钟）
BUILDING_DURATION = 15       # 建仓保护期
COOLDOWN_DURATION = 30       # 卖出冷静期
MIN_PROFIT_TO_SELL = 0.5     # 最小利润率（%），覆盖手续费

# Conviction阈值
CONVICTION_SELL_THRESHOLD = 30   # 低于此值允许SELL
CONVICTION_BUY_THRESHOLD = 60    # 高于此值允许BUY

# Conviction变化规则
# ⚠️ 注意：以下为完整规则集，实际生效的信号取决于 run_cycle 中的触发逻辑
# 当前 run_cycle 中已实现的信号：volume_breakout, sector_strength, volume_decline, break_ma5
# 信号源：系统根据实时行情数据自动计算（非AI输出）
CONVICTION_RULES = {
    # 正面信号
    "volume_breakout": +20,      # 放量突破（涨幅>3% 且 换手>5%）
    "sector_strength": +15,      # 板块加强（涨幅>2%）
    "leader_acceleration": +15,  # 龙头加速（预留，待实现）
    "market_recovery": +10,      # 市场修复（预留，待实现）
    "positive_news": +10,        # 正面新闻（预留，待实现）
    
    # 负面信号
    "volume_decline": -15,       # 量能萎缩（跌幅 且 换手<2%）
    "break_ma5": -25,            # 跌破5日线（现价<成本*0.95）
    "break_ma10": -30,           # 跌破10日线（预留，待实现）
    "sector_weakness": -20,      # 板块退潮（预留，待实现）
    "leader_crack": -40,         # 龙头炸板（预留，待实现）
    "negative_news": -15,        # 负面新闻（预留，待实现）
    "follower_buy": -10,         # 跟风股买入（预留，待实现）
}

# 高潮期(EUPHORIA)Conviction 调节规则
# 设计原则：高潮期盛极而衰，应警惕风险而非放大信念
EUPHORIA_RULES = {
    "leader_conviction_multiplier": 0.8,    # 高潮期龙头信念衰减(防止锁定)
    "follower_conviction_multiplier": 0.5,  # 高潮期跟风信念减半
    "max_positions": 2,                      # 最多2只持仓
    "min_quality_score": 70,                 # 最低质量分
    "allow_follower": False,                 # 禁止跟风股
}


@dataclass
class Thesis:
    """交易逻辑"""
    entry_reason: str                    # 为什么买
    invalid_conditions: List[str]        # 什么情况下逻辑失效
    entry_time: str = ""                 # 入场时间
    entry_price: float = 0               # 入场价格
    entry_sector_strength: float = 0     # 入场时板块强度
    entry_market_state: str = ""         # 入场时市场状态
    
    def to_dict(self):
        return asdict(self)


@dataclass
class PositionHealth:
    """持仓健康度"""
    position_health: float = 0.5         # 0.0-1.0
    thesis_status: str = "VALID"         # VALID / WEAKENING / BROKEN
    market_regime: str = "NEUTRAL"       # 市场状态
    sector_strength: float = 50          # 板块强度 0-100
    leader_status: str = "UNKNOWN"       # 龙头状态
    risk_level: str = "MEDIUM"           # 风险等级
    recommended_action: str = "HOLD"     # HOLD / REDUCE / EXIT
    
    def to_dict(self):
        return asdict(self)


@dataclass
class PositionLifecycle:
    """仓位生命周期"""
    symbol: str
    name: str
    state: PositionState = PositionState.BUILDING
    thesis: Optional[Thesis] = None
    conviction: float = 50               # 初始信念值
    health: PositionHealth = field(default_factory=PositionHealth)
    
    # 时间戳
    state_entered_at: str = ""           # 进入当前状态的时间
    last_updated_at: str = ""            # 最后更新时间
    
    # 历史
    state_history: List[dict] = field(default_factory=list)
    conviction_history: List[dict] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.state_entered_at:
            self.state_entered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.last_updated_at:
            self.last_updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def thesis_status(self) -> str:
        return self.health.thesis_status
    
    @thesis_status.setter
    def thesis_status(self, value: str):
        self.health.thesis_status = value
    
    def to_dict(self):
        d = {
            'symbol': self.symbol, 'name': self.name,
            'state': self.state.value,
            'conviction': self.conviction,
            'state_entered_at': self.state_entered_at,
            'last_updated_at': self.last_updated_at,
            'thesis_status': self.thesis_status,
        }
        if self.thesis:
            d['thesis'] = self.thesis.to_dict()
        d['health'] = self.health.to_dict()
        d['state_history'] = self.state_history
        d['conviction_history'] = self.conviction_history
        return d
    
    def can_sell(self, current_price: float) -> tuple:
        """检查是否可以卖出"""
        now = datetime.now()
        # 🚨 修复：如果状态进入时间为空，默认为很久以前（1 天前），防止触发假保护期
        state_time = datetime.strptime(self.state_entered_at, "%Y-%m-%d %H:%M:%S") if self.state_entered_at else (now - timedelta(days=1))
        
        # S级：Conviction太低强制卖（覆盖一切）
        if self.conviction < CONVICTION_SELL_THRESHOLD:
            return True, f"信念值过低：{self.conviction:.0f} < {CONVICTION_SELL_THRESHOLD}"
        
        # S级：Thesis破坏强制卖（覆盖一切）
        if self.health.thesis_status == "BROKEN":
            return True, f"Thesis破坏"
        
        # A级：建仓保护期不能卖（但可被S级覆盖）
        if self.state == PositionState.BUILDING:
            elapsed = (now - state_time).total_seconds() / 60
            if elapsed < BUILDING_DURATION:
                return False, f"建仓保护期：剩余{BUILDING_DURATION - elapsed:.0f}分钟"
        
        # 最小利润过滤（盈利但不足覆盖手续费）
        if self.thesis and self.thesis.entry_price > 0:
            profit_pct = (current_price - self.thesis.entry_price) / self.thesis.entry_price * 100
            if profit_pct > 0 and profit_pct < MIN_PROFIT_TO_SELL:
                return False, f"利润不足：{profit_pct:.1f}% < {MIN_PROFIT_TO_SELL}%"
        
        # 默认不允许卖出（除非conviction低或thesis破坏）
        return False, f"信念值充足：conviction={self.conviction:.0f}，thesis={self.thesis_status}"
    
    def can_buy(self) -> tuple:
        """检查是否可以买入"""
        now = datetime.now()
        state_time = datetime.strptime(self.state_entered_at, "%Y-%m-%d %H:%M:%S") if self.state_entered_at else now
        
        # 冷静期不能买
        if self.state == PositionState.COOLDOWN:
            elapsed = (now - state_time).total_seconds() / 60
            if elapsed < COOLDOWN_DURATION:
                return False, f"冷静期：剩余{COOLDOWN_DURATION - elapsed:.0f}分钟"
        
        # Conviction太低不能买
        if self.conviction < CONVICTION_BUY_THRESHOLD:
            return False, f"信念值不足：{self.conviction:.0f} < {CONVICTION_BUY_THRESHOLD}"
        
        return True, "可以买入"
    
    def update_conviction(self, signal_type: str, reason: str = ""):
        """更新信念值"""
        delta = CONVICTION_RULES.get(signal_type, 0)
        old_conviction = self.conviction
        self.conviction = max(0, min(100, self.conviction + delta))
        
        self.conviction_history.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signal": signal_type,
            "delta": delta,
            "old": old_conviction,
            "new": self.conviction,
            "reason": reason
        })
        
        return delta
    
    def transition_state(self, new_state: PositionState, reason: str = ""):
        """转换状态"""
        allowed = POSITION_STATE_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            return False, f"不允许从{self.state.value}转换到{new_state.value}"
        
        old_state = self.state
        self.state = new_state
        self.state_entered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.state_history.append({
            "time": self.state_entered_at,
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason
        })
        
        return True, f"状态转换：{old_state.value} → {new_state.value}"


@dataclass
class MarketStateTracker:
    """市场状态追踪器（带惯性）"""
    current_state: MarketState = MarketState.EXPANSION
    candidate_state: Optional[MarketState] = None
    confirmation_count: int = 0
    required_confirmations: int = 3  # 需要连续3次确认
    last_updated: str = ""
    history: List[dict] = field(default_factory=list)
    
    def to_dict(self):
        d = asdict(self)
        d['current_state'] = self.current_state.value
        if self.candidate_state:
            d['candidate_state'] = self.candidate_state.value
        return d
    
    def propose_state(self, proposed_state: MarketState, reason: str = ""):
        """提议新状态（需要连续确认）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 如果提议的状态和当前状态相同，重置计数
        if proposed_state == self.current_state:
            self.candidate_state = None
            self.confirmation_count = 0
            return False, f"状态未变化：{self.current_state.value}"
        
        # 检查是否是允许的转换
        allowed = MARKET_STATE_TRANSITIONS.get(self.current_state, [])
        if proposed_state not in allowed:
            return False, f"不允许从{self.current_state.value}转换到{proposed_state.value}"
        
        # 如果是新的候选状态
        if proposed_state != self.candidate_state:
            self.candidate_state = proposed_state
            self.confirmation_count = 1
            return False, f"新候选状态：{proposed_state.value}（1/{self.required_confirmations}）"
        
        # 连续确认
        self.confirmation_count += 1
        
        if self.confirmation_count >= self.required_confirmations:
            # 确认转换
            old_state = self.current_state
            self.current_state = proposed_state
            self.candidate_state = None
            self.confirmation_count = 0
            self.last_updated = now
            
            self.history.append({
                "time": now,
                "from": old_state.value,
                "to": proposed_state.value,
                "reason": reason
            })
            
            return True, f"状态转换确认：{old_state.value} → {proposed_state.value}"
        
        return False, f"确认中：{proposed_state.value}（{self.confirmation_count}/{self.required_confirmations}）"
    
    def get_state_value(self) -> str:
        """获取当前状态对应的风控值"""
        mapping = {
            MarketState.ICE: "low",
            MarketState.RECOVERY: "neutral",
            MarketState.EXPANSION: "warm",
            MarketState.EUPHORIA: "hot",
            MarketState.COLLAPSE: "low",
            MarketState.CHAOS: "low",
        }
        return mapping.get(self.current_state, "neutral")


class PositionManager:
    """仓位管理器"""
    
    def __init__(self):
        self.positions: Dict[str, PositionLifecycle] = {}
        self.market_tracker = MarketStateTracker()
    
    def add_position(self, symbol: str, name: str, thesis: Thesis, state_entered_at: str = None) -> PositionLifecycle:
        """添加新持仓"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # ★ 核心修复:优先使用真实买入时间,绝不用当前时间(now)覆盖旧持仓
        final_time = state_entered_at
        if not final_time and thesis and thesis.entry_time:
            final_time = thesis.entry_time
        if not final_time:
            final_time = now

        pos = PositionLifecycle(
            symbol=symbol,
            name=name,
            state=PositionState.BUILDING,
            thesis=thesis,
            conviction=60,  # 初始信念值
            state_entered_at=final_time,
            last_updated_at=now,
        )
        self.positions[symbol] = pos
        return pos
    
    def remove_position(self, symbol: str):
        """移除持仓（进入冷静期）"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.transition_state(PositionState.COOLDOWN, "卖出")
            # 保留冷静期记录，5分钟后清理
            # 这里先保留，由外部定时清理
    
    def get_position(self, symbol: str) -> Optional[PositionLifecycle]:
        """获取持仓"""
        return self.positions.get(symbol)
    
    def get_active_positions(self) -> Dict[str, PositionLifecycle]:
        """获取活跃持仓（排除冷静期）"""
        return {k: v for k, v in self.positions.items() 
                if v.state != PositionState.COOLDOWN}
    
    def get_cooldown_positions(self) -> Dict[str, PositionLifecycle]:
        """获取冷静期持仓"""
        return {k: v for k, v in self.positions.items() 
                if v.state == PositionState.COOLDOWN}
    
    def cleanup_cooldown(self):
        """清理过期的冷静期记录"""
        now = datetime.now()
        to_remove = []
        for sym, pos in self.positions.items():
            if pos.state == PositionState.COOLDOWN:
                try:
                    entered = datetime.strptime(pos.state_entered_at, "%Y-%m-%d %H:%M:%S")
                    if (now - entered).total_seconds() / 60 > COOLDOWN_DURATION:
                        to_remove.append(sym)
                except:
                    pass
        for sym in to_remove:
            del self.positions[sym]
    
    def update_market_state(self, market_stage: str, reason: str = ""):
        """更新市场状态（带惯性）"""
        stage_mapping = {
            "低迷": MarketState.ICE,
            "震荡偏空": MarketState.ICE,
            "震荡": MarketState.EXPANSION,
            "震荡偏多": MarketState.EXPANSION,
            "升温": MarketState.EXPANSION,
            "高潮": MarketState.EUPHORIA,
            "恐慌": MarketState.COLLAPSE,
        }
        proposed = stage_mapping.get(market_stage, MarketState.EXPANSION)
        return self.market_tracker.propose_state(proposed, reason)
    
    def get_all_health(self) -> Dict[str, PositionHealth]:
        """获取所有持仓健康度"""
        return {sym: pos.health for sym, pos in self.positions.items()}
    
    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "positions": {sym: pos.to_dict() for sym, pos in self.positions.items()},
            "market_state": self.market_tracker.to_dict(),
        }
    
    def sync_from_portfolio(self, portfolio: dict):
        """从portfolio.json同步持仓(含保护期/冷静期持久化恢复)"""
        for sym, pos_entry in portfolio.get("positions", {}).items():
            batches = pos_entry if isinstance(pos_entry, list) else [pos_entry]
            if not batches:
                continue
            # 用最早批次初始化（如果尚未跟踪）
            if sym not in self.positions:
                oldest = batches[0]
                thesis = Thesis(
                    entry_reason=oldest.get("buy_reason", ""),
                    invalid_conditions=[],
                    entry_time=oldest.get("buy_time", ""),
                    entry_price=oldest.get("cost_price", 0),
                )
                state_time = oldest.get("state_entered_at", oldest.get("buy_time", ""))
                self.add_position(sym, oldest.get("name", ""), thesis, state_entered_at=state_time)
                # 设置为HOLDING状态（因为已经持仓了）
                self.positions[sym].state = PositionState.HOLDING
                # ★ 恢复持久化的conviction
                saved_conv = oldest.get("conviction", None)
                if saved_conv is not None:
                    self.positions[sym].conviction = float(saved_conv)
                # ★ 恢复health状态
                saved_thesis = oldest.get("thesis_status", None)
                if saved_thesis:
                    self.positions[sym].health.thesis_status = saved_thesis

        # ★ 恢复冷静期记录
        for cooldown in portfolio.get("cooldown_positions", []):
            sym = cooldown.get("symbol", "")
            if sym and sym not in self.positions:
                thesis = Thesis(
                    entry_reason=cooldown.get("buy_reason", ""),
                    entry_time=cooldown.get("buy_time", ""),
                    entry_price=cooldown.get("cost_price", 0),
                )
                self.add_position(sym, cooldown.get("name", ""), thesis, state_entered_at=cooldown.get("sell_time", ""))
                self.positions[sym].state = PositionState.COOLDOWN
                self.positions[sym].conviction = float(cooldown.get("conviction", 50))
