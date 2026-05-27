"""Risk Engine v3 - 风控层（最高优先级）
职责：审核/覆盖所有策略信号
优先级：可以覆盖一切策略输出
独立性：不依赖AI，基于硬规则

v3 改进：
- 集成Position Lifecycle系统
- 使用Conviction值决策
- Thesis驱动的卖出逻辑
- 防震荡交易规则
"""
from .models import Signal, RiskResult, MarketData, now_str
from typing import List, Optional, Dict
from datetime import datetime
import sys
from pathlib import Path

# 导入Position Lifecycle
sys.path.insert(0, str(Path(__file__).parent.parent))
from v3.position_lifecycle import (
    PositionManager, PositionLifecycle, PositionState, Thesis,
    PositionHealth, CONVICTION_SELL_THRESHOLD, CONVICTION_BUY_THRESHOLD,
    BUILDING_DURATION, COOLDOWN_DURATION, MIN_PROFIT_TO_SELL
)

# 全局仓位管理器实例
_position_manager = PositionManager()

def get_position_manager() -> PositionManager:
    """获取全局仓位管理器"""
    return _position_manager


# ══════════════════════════════════════════════════════════
# 风控优先级系统
# ══════════════════════════════════════════════════════════
# S级：硬止损（绝对不能违反）
# A级：仓位/止盈/资金/交易次数（严格遵守）
# B级：技术面/时间退出（条件触发）

# ══════════════════════════════════════════════════════════
# S级参数（硬止损）
# ══════════════════════════════════════════════════════════
STOP_LOSS_NORMAL = -5.0       # 普通票止损
STOP_LOSS_GEM = -7.0          # 创业板(30xxxx)止损
STOP_LOSS_STAR = -8.0         # 科创板(688xxx)止损

# ══════════════════════════════════════════════════════════
# A级参数（止盈/仓位/交易次数）
# ══════════════════════════════════════════════════════════
TAKE_PROFIT_1 = 10.0          # 第一档止盈：卖1/3
TAKE_PROFIT_2 = 15.0          # 第二档止盈：再卖1/3
TAKE_PROFIT_FINAL = 20.0      # 最终止盈：清仓
MAX_HOLDING_DAYS = 7          # 最大持仓天数（强制清仓）
# BUY_COOLDOWN_MINUTES 已移至 Position Lifecycle 系统

# 动态仓位（根据市场状态）
MAX_POSITION_MAP = {
    "low":      0.50,   # 市场低迷：最大50%
    "neutral":  0.60,   # 震荡市：最大60%
    "warm":     0.70,   # 升温：最大70%
    "hot":      0.80,   # 高潮：最大80%
    "extreme":  0.90,   # 极端牛市：最大90%
}
DEFAULT_MAX_POSITION = 0.70   # 默认最大仓位

# 单只仓位限制
MAX_SINGLE_POSITION = 0.15   # 普通票：15%
MAX_SINGLE_LEADER = 0.20     # 龙头确认：20%
MAX_SINGLE_MAX = 0.25        # 绝对上限：25%

MAX_DAILY_TRADES = 4         # 每日最大交易次数（默认）
MAX_DAILY_TRADES_HOT = 6     # 市场高潮时放宽到6笔

# ══════════════════════════════════════════════════════════
# B级参数（技术面/时间退出）
# ══════════════════════════════════════════════════════════
SECTOR_STRENGTH_MIN = 40      # 板块最低强度（配合5日线规则使用）

# 市场阶段 -> 风控市场状态映射
MARKET_STAGE_MAP = {
    "低迷": "low",
    "震荡偏空": "low",
    "震荡": "neutral",
    "震荡偏多": "warm",
    "升温": "warm",
    "高潮": "hot",
    "恐慌": "low",
}


def market_stage_to_state(market_stage: str) -> str:
    """将市场阶段转换为风控市场状态"""
    return MARKET_STAGE_MAP.get(market_stage, "neutral")


def get_stop_loss_pct(symbol: str) -> float:
    """根据股票类型返回动态止损"""
    if symbol.startswith("688"):
        return STOP_LOSS_STAR      # 科创板 -8%
    elif symbol.startswith("30"):
        return STOP_LOSS_GEM       # 创业板 -7%
    else:
        return STOP_LOSS_NORMAL    # 普通票 -5%


def get_stock_type_name(symbol: str) -> str:
    """获取股票类型名称"""
    if symbol.startswith("688"):
        return "科创板"
    elif symbol.startswith("30"):
        return "创业板"
    elif symbol.startswith("60"):
        return "沪市主板"
    elif symbol.startswith("00"):
        return "深市主板"
    else:
        return "其他"


def get_max_position(market_state: str = "neutral") -> float:
    """根据市场状态返回动态最大仓位"""
    return MAX_POSITION_MAP.get(market_state, DEFAULT_MAX_POSITION)


def is_euphoria(market_state: str) -> bool:
    """是否处于高潮期"""
    return market_state in ("hot", "extreme")


def get_euphoria_buy_limit(signal_score: int, is_leader: bool, market_state: str) -> tuple:
    """高潮期买入限制调整
    
    返回: (允许买入, 原因)
    高潮期不是禁止交易，而是切换为龙头主升模式：
    - 优先高质量龙头
    - 允许高评分补涨股(>=75)
    - 降低评分要求(非龙头需>=75)
    """
    if not is_euphoria(market_state):
        return True, ""
    
    # 高潮期：龙头股质量分>=65即可
    if is_leader and signal_score >= 65:
        return True, "高潮期龙头模式：允许高质量龙头交易"
    
    # 高潮期：非龙头股(补涨)需>=75分
    if not is_leader and signal_score >= 75:
        return True, "高潮期补涨模式：评分充足，允许试错"
    
    # 评分不足
    if signal_score < 65:
        return False, f"[高潮期]质量分不足：score={signal_score}<65，高潮期要求更高"
    
    # 非龙头且评分在65-75之间，谨慎拦截
    if not is_leader:
        return False, f"[高潮期]跟风股评分不足：score={signal_score}<75，高潮期非龙头需更高分"
    
    return True, "高潮期模式：允许交易"


def get_max_daily_trades(market_state: str = "neutral") -> int:
    """根据市场状态返回每日最大交易次数"""
    if market_state in ("hot", "extreme"):
        return MAX_DAILY_TRADES_HOT
    return MAX_DAILY_TRADES


def is_limit_limit(symbol: str, current_price: float, limit_up_price: float = 0, limit_down_price: float = 0) -> str:
    """
    检测涨跌停状态（基于真实涨停价/跌停价，绝不降级为阈值估算）
    返回: 'LIMIT_UP' / 'LIMIT_DOWN' / 'NORMAL'
    """
    if limit_up_price > 0 and current_price > 0:
        if current_price >= limit_up_price * 0.99:
            return 'LIMIT_UP'
    if limit_down_price > 0 and current_price > 0:
        if current_price <= limit_down_price * 1.01:
            return 'LIMIT_DOWN'
    return 'NORMAL'

def check_signal(signal: Signal,
                 market_data: MarketData,
                 current_positions: dict,
                 portfolio_cash: float,
                 portfolio_total: float,
                 daily_trade_count: int,
                 market_state: str = "neutral",
                 position_manager: PositionManager = None) -> RiskResult:
    """
    审核单个交易信号（v3 - 集成Position Lifecycle）
    返回风控结果：通过/拒绝/覆盖
    
    优先级：S级 > A级 > B级 > Position Lifecycle
    """
    ts = now_str()
    sym = signal.symbol
    name = signal.name  # ★ 修复:从signal获取name,而非使用未定义变量
    pos = current_positions.get(sym, {})
    
    # 兼容多批次结构
    batches = pos if isinstance(pos, list) else [pos]
    
    total_qty = sum(b.get("qty", 0) for b in batches)
    if total_qty > 0:
        cost = sum(b.get("cost_price", 0) * b.get("qty", 0) for b in batches) / total_qty
        # 取最早批次日期计算持仓天数
        first_date = batches[0].get("buy_date", "")
        try:
            holding_days = (datetime.now() - datetime.strptime(first_date, "%Y-%m-%d")).days
        except:
            holding_days = 0
    else:
        cost = 0
        holding_days = 0
    
    qty = total_qty
    
    # A股 T+1 规则：今日买入不可卖出 (S级硬性规则)
    if signal.action == "SELL":
        buy_date = batches[0].get("buy_date", "") if batches else ""
        today = datetime.now().strftime("%Y-%m-%d")
        if buy_date == today:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[S级]T+1限制：今日({today})买入不可卖出",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    holding_days = 0
    is_leader = False
    if isinstance(pos, list):
        if pos:
            first_pos = pos[0]
            is_leader = first_pos.get("is_leader", False) or signal.is_leader
    else:
        holding_days = pos.get("holding_days", 0)
        is_leader = pos.get("is_leader", False) or signal.is_leader
    
    # 获取Position Lifecycle状态
    pos_lifecycle = None
    if position_manager:
        pos_lifecycle = position_manager.get_position(sym)

    # ══════════════════════════════════════════════════════════
    # S级：硬止损（绝对不能违反）
    # ══════════════════════════════════════════════════════════
    
    # S1: 硬止损
    if cost > 0 and qty > 0:
        pnl_pct = (market_data.price - cost) / cost * 100
        stop_loss = get_stop_loss_pct(sym)
        if pnl_pct <= stop_loss:
            # [修复] 止损是卖出的理由，绝不能因为触发止损而拒绝卖出
            if signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[S级]硬止损：浮亏{pnl_pct:.1f}% <= {stop_loss}%（{get_stock_type_name(sym)}）",
                    risk_level="CRITICAL",
                    original_signal=signal.to_dict(),
                )

    # S1.5: 涨跌停限制（硬拦截：涨停不可买，跌停不可卖）
    if signal.action == "BUY":
        limit_status = is_limit_limit(sym, market_data.price, market_data.limit_up_price, market_data.limit_down_price)
        if limit_status == 'LIMIT_UP':
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[S级]涨停限制：{name} 涨幅{market_data.change_pct:+.1f}%，无法买入",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )
    if signal.action == "SELL":
        limit_status = is_limit_limit(sym, market_data.price, market_data.limit_up_price, market_data.limit_down_price)
        if limit_status == 'LIMIT_DOWN':
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[S级]跌停限制：{name} 跌幅{market_data.change_pct:+.1f}%，无法卖出",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    # S2: Position Lifecycle检查（建仓保护期）
    if signal.action == "SELL" and pos_lifecycle:
        can_sell, sell_reason = pos_lifecycle.can_sell(market_data.price)
        if not can_sell:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[S级]仓位状态：{sell_reason}",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )
    
    # S3: Conviction检查（卖出必须thesis破坏）
    if signal.action == "SELL" and pos_lifecycle:
        if pos_lifecycle.conviction >= CONVICTION_SELL_THRESHOLD:
            # Conviction还够，检查thesis状态
            if pos_lifecycle.thesis_status != "BROKEN":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="HOLD",
                    reason=f"[S级]信念值充足：conviction={pos_lifecycle.conviction:.0f}，thesis={pos_lifecycle.thesis_status}",
                    risk_level="MEDIUM",
                    original_signal=signal.to_dict(),
                )

    # S4: 冷静期检查（买入）
    if signal.action == "BUY" and pos_lifecycle:
        can_buy, buy_reason = pos_lifecycle.can_buy()
        if not can_buy:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[S级]仓位状态：{buy_reason}",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    # ══════════════════════════════════════════════════════════
    # A级：仓位限制 / 止盈 / 资金 / 交易次数
    # ══════════════════════════════════════════════════════════
    
    # A1: 仓位控制（动态）
    if signal.action == "BUY":
        max_pos = get_max_position(market_state)
        current_ratio = 1 - (portfolio_cash / portfolio_total) if portfolio_total > 0 else 1
        if current_ratio >= max_pos:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[A级]仓位已满：当前{current_ratio*100:.0f}% >= 市场{market_state}最大{max_pos*100:.0f}%",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    # A2: 单只仓位限制（龙头放宽）
    if signal.action == "BUY":
        max_single = MAX_SINGLE_LEADER if is_leader else MAX_SINGLE_POSITION
        max_single = min(max_single, MAX_SINGLE_MAX)
        buy_amount = signal.price * signal.qty
        if buy_amount / portfolio_total > max_single:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[A级]单只超限：{buy_amount/portfolio_total*100:.0f}% > {'龙头' if is_leader else '普通'}上限{max_single*100:.0f}%",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    # A2.5: 高潮期龙头模式（EUPHORIA）
    if signal.action == "BUY":
        euphoria_allowed, euphoria_reason = get_euphoria_buy_limit(
            signal.score, is_leader, market_state
        )
        if not euphoria_allowed:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=euphoria_reason,
                risk_level="MEDIUM",
                original_signal=signal.to_dict(),
            )

    # A3: 资金检查
    if signal.action == "BUY":
        buy_amount = signal.price * signal.qty
        if buy_amount > portfolio_cash:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[A级]资金不足：需要{buy_amount:.0f} > 可用{portfolio_cash:.0f}",
                risk_level="MEDIUM",
                original_signal=signal.to_dict(),
            )

    # A4: 每日交易次数限制 - 已移除（不应阻碍正常止损和调仓）

    # A5: 止盈（分批）
    if cost > 0 and qty > 0:
        pnl_pct = (market_data.price - cost) / cost * 100
        
        # 最终止盈：清仓
        if pnl_pct >= TAKE_PROFIT_FINAL:
            if signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[A级]最终止盈：浮盈{pnl_pct:.1f}% >= {TAKE_PROFIT_FINAL}%清仓",
                    risk_level="HIGH",
                    original_signal=signal.to_dict(),
                )
        
        # 第二档止盈：卖2/3
        if pnl_pct >= TAKE_PROFIT_2:
            sell_qty = int(qty * 2 / 3 / 100) * 100
            if sell_qty >= 100 and signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[A级]第二档止盈：浮盈{pnl_pct:.1f}% >= {TAKE_PROFIT_2}%卖2/3",
                    risk_level="HIGH",
                    original_signal=signal.to_dict(),
                    sell_qty=sell_qty,
                )
        
        # 第一档止盈：卖1/3
        if pnl_pct >= TAKE_PROFIT_1:
            sell_qty = int(qty / 3 / 100) * 100
            if sell_qty >= 100 and signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[A级]第一档止盈：浮盈{pnl_pct:.1f}% >= {TAKE_PROFIT_1}%卖1/3",
                    risk_level="MEDIUM",
                    original_signal=signal.to_dict(),
                    sell_qty=sell_qty,
                )

    # ══════════════════════════════════════════════════════════
    # B级：技术面 / 时间退出（条件触发）
    # ══════════════════════════════════════════════════════════
    
    # B1: 时间强制退出
    if holding_days >= MAX_HOLDING_DAYS and qty > 0:
        if signal.action != "SELL":
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="SELL",
                reason=f"[B级]持仓超时：{holding_days}天 >= {MAX_HOLDING_DAYS}天强制清仓",
                risk_level="HIGH",
                original_signal=signal.to_dict(),
            )

    # B2: 技术破位（条件触发：跌破5日线 + 板块转弱 + 量能恶化）
    if cost > 0 and qty > 0 and market_data.ma5 > 0:
        if market_data.price < market_data.ma5:
            sector_weak = market_data.sector_strength < SECTOR_STRENGTH_MIN
            volume_bad = market_data.turnover_rate < 3  # 换手率<3%算缩量
            
            if sector_weak and volume_bad:
                if signal.action != "SELL":
                    return RiskResult(
                        timestamp=ts, symbol=sym,
                        approved=False,
                        action_override="SELL",
                        reason=f"[B级]技术破位：价格{market_data.price} < MA5({market_data.ma5:.2f}) + 板块弱({market_data.sector_strength:.0f}) + 缩量(换手{market_data.turnover_rate:.1f}%)",
                        risk_level="HIGH",
                        original_signal=signal.to_dict(),
                    )
            elif sector_weak:
                if signal.action != "SELL":
                    return RiskResult(
                        timestamp=ts, symbol=sym,
                        approved=False,
                        action_override="REDUCE_50%",
                        reason=f"[B级]板块转弱：价格<MA5 + 板块强度{market_data.sector_strength:.0f}",
                        risk_level="MEDIUM",
                        original_signal=signal.to_dict(),
                    )

    # B3: 冲高回落
    if cost > 0 and qty > 0:
        intraday_high_pct = (market_data.high - cost) / cost * 100
        current_pnl = (market_data.price - cost) / cost * 100
        if intraday_high_pct >= 5 and current_pnl < 2:
            if signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[B级]冲高回落：最高涨{intraday_high_pct:.1f}%现仅{current_pnl:.1f}%",
                    risk_level="HIGH",
                    original_signal=signal.to_dict(),
                )

    # B4: 放量滞涨
    if cost > 0 and qty > 0:
        if market_data.turnover_rate > 15 and abs((market_data.price - cost) / cost * 100) < 1:
            if signal.action != "SELL":
                return RiskResult(
                    timestamp=ts, symbol=sym,
                    approved=False,
                    action_override="SELL",
                    reason=f"[B级]放量滞涨：换手{market_data.turnover_rate:.1f}%涨幅仅{(market_data.price-cost)/cost*100:.1f}%",
                    risk_level="HIGH",
                    original_signal=signal.to_dict(),
                )

    # B5: 龙头退潮（跌破10日线禁止新开仓）
    if signal.action == "BUY" and market_data.ma10 > 0:
        if market_data.price < market_data.ma10:
            return RiskResult(
                timestamp=ts, symbol=sym,
                approved=False,
                action_override="HOLD",
                reason=f"[B级]禁止开仓：价格{market_data.price} < MA10({market_data.ma10:.2f})",
                risk_level="MEDIUM",
                original_signal=signal.to_dict(),
            )

    # ══════════════════════════════════════════════════════════
    # 通过
    # ══════════════════════════════════════════════════════════
    return RiskResult(
        timestamp=ts, symbol=sym,
        approved=True,
        action_override=None,
        reason=f"风控通过 评分{signal.score} 信号{signal.action}",
        risk_level="LOW",
        original_signal=signal.to_dict(),
    )


def review_all_signals(signals: List[Signal],
                       market_data_map: dict,
                       current_positions: dict,
                       portfolio_cash: float,
                       portfolio_total: float,
                       daily_trade_count: int,
                       market_state: str = "neutral") -> List[RiskResult]:
    """
    批量审核所有信号
    返回风控结果列表
    """
    results = []
    for sig in signals:
        md = market_data_map.get(sig.symbol)
        if not md:
            results.append(RiskResult(
                timestamp=now_str(), symbol=sig.symbol,
                approved=False, action_override=None,
                reason="无行情数据", risk_level="LOW",
                original_signal=sig.to_dict(),
            ))
            continue
        result = check_signal(sig, md, current_positions,
                            portfolio_cash, portfolio_total, daily_trade_count,
                            market_state)
        results.append(result)
    return results
