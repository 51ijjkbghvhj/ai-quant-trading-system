"""
Experience Layer v7.1 - 经验积累层 (事务增强版)
"""
import sys, os
import json
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from v2.db import get_conn, DB_PATH

# --- 核心事务包装器 ---
def run_transaction(operations):
    """
    执行一组数据库操作作为事务。
    operations 是一个函数列表，每个函数接收 (conn, cursor) 并执行 SQL。
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("BEGIN")
        for op in operations:
            op(c)
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[EXP] Transaction Rollback: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- 1. 记录交易循环 (原子操作) ---
def commit_experience_cycle(trade_data, position_data, outcome_data):
    """
    同时写入 trade_execution, positions, thesis_outcomes
    """
    def op_trade(c):
        c.execute("""INSERT INTO trade_execution 
        (timestamp, type, symbol, name, price, qty, amount, pnl, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            trade_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            trade_data.get('type', 'buy'),
            trade_data.get('symbol', ''),
            trade_data.get('name', ''),
            trade_data.get('price', 0),
            trade_data.get('qty', 0),
            trade_data.get('amount', 0),
            trade_data.get('pnl', 0),
            trade_data.get('reason', '')
        ))

    def op_position(c):
        # 使用 INSERT OR REPLACE 更新 positions
        c.execute("""INSERT OR REPLACE INTO positions 
        (symbol, status, avg_cost, qty, current_pnl, max_profit, max_drawdown, conviction, thesis_json, market_state_entered, entry_reason, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM positions WHERE symbol=?), ?), ?)""", (
            position_data.get('symbol'), position_data.get('status'), position_data.get('avg_cost'),
            position_data.get('qty'), position_data.get('current_pnl'), position_data.get('max_profit'),
            position_data.get('max_drawdown'), position_data.get('conviction'), position_data.get('thesis_json'),
            position_data.get('market_state_entered'), position_data.get('entry_reason'),
            position_data.get('symbol'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # created_at if new
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # updated_at
        ))

    def op_outcome(c):
        # 如果是卖出，记录 outcome
        if trade_data.get('type') == 'sell':
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("""INSERT INTO thesis_outcomes 
            (thesis_type, market_state, pnl, result, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (
                outcome_data.get('thesis_type', 'General'),
                outcome_data.get('market_state', 'Unknown'),
                outcome_data.get('pnl', 0),
                outcome_data.get('result', 'unknown'),
                outcome_data.get('reason', ''),
                now
            ))
            # 触发 Stats 更新
            update_thesis_stats_logic(c, outcome_data.get('thesis_type', 'General'))

    return run_transaction([op_trade, op_position, op_outcome])


# --- 2. 增强的 Stats 计算 (盈亏比 / 回撤 / 样本量) ---
def update_thesis_stats_logic(c, thesis_type):
    """在事务中更新统计"""
    # 1. 获取样本量
    c.execute("SELECT COUNT(*) FROM thesis_outcomes WHERE thesis_type=?", (thesis_type,))
    count = c.fetchone()[0]
    
    if count > 0:
        # 2. 详细统计数据
        c.execute("""SELECT 
            AVG(CASE WHEN result='win' THEN 1.0 ELSE 0.0 END), -- win_rate
            SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END),        -- gross_profit
            SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END),        -- gross_loss (negative)
            AVG(pnl),                                          -- avg_pnl
            MAX(pnl),                                          -- max_profit
            MIN(pnl),                                          -- worst_loss
            AVG(holding_days),                                 -- avg_holding_days
            COUNT(CASE WHEN result='win' THEN 1 END),          -- win_count
            COUNT(CASE WHEN result='loss' THEN 1 END)          -- loss_count
            FROM thesis_outcomes WHERE thesis_type=?""", (thesis_type,))
            
        res = c.fetchone()
        
        win_rate = res[0] or 0
        gross_profit = res[1] or 0
        gross_loss = res[2] or 0 # this is negative
        avg_pnl = res[3] or 0
        max_profit = res[4] or 0
        worst_loss = res[5] or 0
        avg_hold_days = res[6] or 0
        win_count = res[7] or 0
        loss_count = res[8] or 0
        
        # 3. 计算核心指标
        # Profit Factor = Gross Profit / |Gross Loss|
        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else (gross_profit if gross_profit > 0 else 0)
        
        # Win/Loss Ratio = Avg Win / Avg Loss (Absolute value)
        # Need separate query for averages if we want precision, but we can estimate
        # Better: (GrossProfit / WinCount) / (GrossLoss / LossCount)
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else 0
        
        # 4. 更新或插入
        c.execute("""INSERT OR REPLACE INTO thesis_stats 
        (thesis_type, total_trades, win_rate, profit_factor, win_loss_ratio, 
         avg_profit, worst_loss, avg_holding_days, sample_size, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            thesis_type, count, win_rate, round(profit_factor, 2), round(win_loss_ratio, 2),
            round(avg_pnl, 2), round(worst_loss, 2), round(avg_hold_days, 1), count,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

# 兼容旧接口
def update_thesis_stats(thesis_type):
    conn = get_conn()
    c = conn.cursor()
    update_thesis_stats_logic(c, thesis_type)
    conn.commit()
    conn.close()

# --- 3. Pattern Memory ---
def save_pattern(pattern_name, conditions, result, confidence):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""INSERT OR REPLACE INTO pattern_memory 
        (pattern_name, trigger_conditions, historical_result, confidence, created_at)
        VALUES (?, ?, ?, ?, ?)""", (
            pattern_name, json.dumps(conditions, ensure_ascii=False), result, confidence, datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[EXP] Pattern Save Failed: {e}")
        return False
    finally:
        conn.close()

# --- 4. 上下文获取 ---
def get_ai_context():
    conn = get_conn()
    c = conn.cursor()
    context = {"reflection": [], "thesis_stats": [], "mistakes": [], "patterns": []}
    
    # 1. Reflections (最近3天)
    c.execute("SELECT reflection_json FROM daily_reflection ORDER BY date DESC LIMIT 3")
    for row in c.fetchall():
        try: context["reflection"].append(json.loads(row[0]))
        except: pass
        
    # 2. Stats (过滤样本量 < 3 的，防止幸存者偏差)
    c.execute("""SELECT thesis_type, win_rate, profit_factor, win_loss_ratio, worst_loss, sample_size 
                     FROM thesis_stats WHERE total_trades >= 3 ORDER BY profit_factor DESC LIMIT 5""")
    for row in c.fetchall():
        context["thesis_stats"].append({
            "type": row[0], "win_rate": f"{row[1]*100:.1f}%", 
            "profit_factor": row[2], "win_loss_ratio": row[3], "worst_loss": row[4], "sample_size": row[5]
        })
        
    # 3. Mistakes (重要性 > 0.6)
    now = datetime.now()
    c.execute("SELECT ai_decision, actual_result, failure_reason, market_state FROM ai_mistakes WHERE importance > 0.6 AND date(decay_date) > ? ORDER BY importance DESC LIMIT 3", (now.strftime('%Y-%m-%d'),))
    for row in c.fetchall():
        context["mistakes"].append({"decision": row[0], "result": row[1], "reason": row[2], "market_state": row[3]})
        
    # 4. Negative Patterns (高置信度的禁忌)
    c.execute("SELECT pattern_name, trigger_conditions, historical_result, confidence FROM pattern_memory WHERE confidence > 0.7 ORDER BY confidence DESC LIMIT 5")
    for row in c.fetchall():
        context["patterns"].append({
            "pattern_name": row[0], 
            "trigger_conditions": row[1], 
            "historical_result": row[2],
            "confidence": row[3]
        })
        
    conn.close()
    return context

# --- 遗留兼容 ---
def record_thesis_outcome(thesis_type, market_state, pnl, result, reason="", holding_days=0.0):
    # 为了兼容旧调用，我们构建数据包并调用事务接口，但这通常只在卖出时由 event_bus 调用
    # 这里简单写入，不保证全事务
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO thesis_outcomes (thesis_type, market_state, pnl, result, reason, holding_days, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (thesis_type, market_state, pnl, result, reason, holding_days, now))
    update_thesis_stats_logic(c, thesis_type)
    conn.commit()
    conn.close()

def update_position_lifecycle(symbol, status, avg_cost, qty, current_pnl, max_profit, max_drawdown, conviction, thesis_json, market_state_entered, entry_reason):
    # 兼容旧调用，简单 REPLACE
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""INSERT OR REPLACE INTO positions 
    (symbol, status, avg_cost, qty, current_pnl, max_profit, max_drawdown, conviction, thesis_json, market_state_entered, entry_reason, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM positions WHERE symbol=?), ?), ?)""", (
        symbol, status, avg_cost, qty, current_pnl, max_profit, max_drawdown, conviction,
        thesis_json, market_state_entered, entry_reason, symbol, now, now
    ))
    conn.commit()
    conn.close()

# --- 5. Daily Reflection (New) ---
def save_daily_reflection(reflection_data: dict):
    """将研究 AI 的复盘内容存入 daily_reflection 表"""
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        # 使用 REPLACE 覆盖当天的旧复盘，保持记忆最新
        c.execute("""INSERT OR REPLACE INTO daily_reflection 
        (date, reflection_json)
        VALUES (?, ?)""", (today, json.dumps(reflection_data, ensure_ascii=False)))
        conn.commit()
        print(f"[EXP] Daily reflection saved for {today}")
        return True
    except Exception as e:
        print(f"[EXP] Reflection Save Failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
