"""AI分析和风控记录数据库（SQLite）"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "trading_history.db"

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS ai_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        reasoning TEXT,
        events TEXT,
        signals_json TEXT,
        signals_count INTEGER DEFAULT 0,
        hold_count INTEGER DEFAULT 0,
        trade_count INTEGER DEFAULT 0,
        executed INTEGER DEFAULT 0,
        model TEXT,
        status TEXT DEFAULT 'success'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS risk_control (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id INTEGER,
        timestamp TEXT NOT NULL,
        symbol TEXT,
        name TEXT,
        action TEXT,
        result TEXT,
        reason TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS trade_execution (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        type TEXT,
        symbol TEXT,
        name TEXT,
        price REAL,
        qty INTEGER,
        amount REAL,
        pnl REAL,
        reason TEXT
    )''')
    
    c.execute("""CREATE TABLE IF NOT EXISTS market_daily (
    date TEXT PRIMARY KEY, market_state TEXT, limit_up_count INTEGER, broken_board_rate REAL, 
    highest_board INTEGER, total_volume REAL, hot_themes TEXT, leaders TEXT, 
    sentiment_score REAL, leader_success_rate REAL)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY, status TEXT, avg_cost REAL, qty INTEGER, current_pnl REAL, 
    max_profit REAL DEFAULT 0, max_drawdown REAL DEFAULT 0, conviction REAL DEFAULT 50, 
    thesis_json TEXT, market_state_entered TEXT, entry_reason TEXT, 
    created_at TEXT, updated_at TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS thesis_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, thesis_type TEXT, market_state TEXT, 
    pnl REAL, result TEXT, reason TEXT,
        holding_days REAL, created_at TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS thesis_stats (
    thesis_type TEXT PRIMARY KEY, total_trades INTEGER DEFAULT 0, win_rate REAL, 
    avg_profit REAL, avg_drawdown REAL, max_profit REAL, effective_market_states TEXT, 
    failure_patterns TEXT, last_updated TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS daily_reflection (
    date TEXT PRIMARY KEY, reflection_json TEXT, created_at TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS ai_mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, ai_decision TEXT, 
    actual_result TEXT, failure_reason TEXT, ignored_risk_signal TEXT, 
    market_state TEXT, importance REAL DEFAULT 0.5, decay_date TEXT)""")
    

    c.execute("""CREATE TABLE IF NOT EXISTS pattern_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_name TEXT UNIQUE,
    trigger_conditions TEXT,
    historical_result TEXT,
    confidence REAL,
    created_at TEXT
    )""")

    
    # Migration: Add holding_days if missing
    try:
        c.execute("SELECT holding_days FROM thesis_outcomes LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE thesis_outcomes ADD COLUMN holding_days REAL")
        print("[DB] Migration: Added holding_days to thesis_outcomes.")

    # Migration: Add quality_flag if missing (区分正常交易 / Bug交易 / 测试单)
    try:
        c.execute("SELECT quality_flag FROM thesis_outcomes LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE thesis_outcomes ADD COLUMN quality_flag TEXT DEFAULT 'normal'")
        print("[DB] Migration: Added quality_flag to thesis_outcomes.")

    c.execute('CREATE INDEX IF NOT EXISTS idx_ai_ts ON ai_analysis(timestamp)')

    # Migration: Update thesis_stats with new columns
    cols = [
        ("profit_factor", "REAL"),
        ("win_loss_ratio", "REAL"),
        ("worst_loss", "REAL"),
        ("avg_holding_days", "REAL"),
        ("sample_size", "INTEGER")
    ]
    for col_name, col_type in cols:
        try:
            c.execute(f"SELECT {col_name} FROM thesis_stats LIMIT 1")
        except sqlite3.OperationalError:
            c.execute(f"ALTER TABLE thesis_stats ADD COLUMN {col_name} {col_type}")
            print(f"[DB] Migration: Added {col_name} to thesis_stats.")

    c.execute('CREATE INDEX IF NOT EXISTS idx_ai_ts ON ai_analysis(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_risk_ts ON risk_control(timestamp)')
    c.execute("""CREATE TABLE IF NOT EXISTS feature_store (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        macd_dif REAL,
        macd_dea REAL,
        macd_hist REAL,
        rsi_6 REAL,
        ma5_dist REAL,
        ma20_dist REAL,
        volume_ratio REAL,
        capital_flow_proxy REAL,
        raw_data_snapshot TEXT
    )""")
    # Migration: Add semantic trend context fields to feature_store
    trend_cols = ["trend_direction", "trend_strength", "ma_structure", "volatility_state"]
    for col_name in trend_cols:
        try:
            c.execute(f"SELECT {col_name} FROM feature_store LIMIT 1")
        except sqlite3.OperationalError:
            c.execute(f"ALTER TABLE feature_store ADD COLUMN {col_name} TEXT")
            print(f"[DB] Migration: Added {col_name} to feature_store.")

    c.execute('CREATE INDEX IF NOT EXISTS idx_feature_sym ON feature_store(symbol)')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_trade_ts ON trade_execution(timestamp)')
    
    conn.commit()
    conn.close()

def save_ai_analysis(data):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now()
    c.execute('''INSERT INTO ai_analysis 
        (timestamp, date, time, reasoning, events, signals_json, 
         signals_count, hold_count, trade_count, executed, model, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        data.get('timestamp', now.strftime('%Y-%m-%d %H:%M:%S')),
        data.get('date', now.strftime('%Y-%m-%d')),
        data.get('time', now.strftime('%H:%M:%S')),
        data.get('reasoning', ''),
        data.get('events', ''),
        json.dumps(data.get('signals', []), ensure_ascii=False),
        data.get('signals_count', 0),
        data.get('hold_count', 0),
        data.get('trade_count', 0),
        data.get('executed', 0),
        data.get('model', ''),
        data.get('status', 'success')
    ))
    aid = c.lastrowid
    conn.commit()
    conn.close()
    return aid

def save_risk_control(data):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO risk_control 
        (analysis_id, timestamp, symbol, name, action, result, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)''', (
        data.get('analysis_id'),
        data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        data.get('symbol', ''),
        data.get('name', ''),
        data.get('action', ''),
        data.get('result', ''),
        data.get('reason', '')
    ))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid

def save_trade(data):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO trade_execution 
        (timestamp, type, symbol, name, price, qty, amount, pnl, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        data.get('type', ''),
        data.get('symbol', ''),
        data.get('name', ''),
        data.get('price', 0),
        data.get('qty', 0),
        data.get('amount', 0),
        data.get('pnl', 0),
        data.get('reason', '')
    ))
    tid = c.lastrowid
    conn.commit()
    conn.close()
    return tid

def update_position_lifecycle(symbol, status=None, avg_cost=None, qty=None, current_pnl=None, max_profit=None, max_drawdown=None, conviction=None, thesis_json=None, market_state_entered=None, entry_reason=None):
    """
    更新持仓生命周期数据
    """
    conn = get_conn()
    c = conn.cursor()
    
    # 构建 SET 子句
    updates = []
    params = []
    if status is not None: updates.append("status=?"); params.append(status)
    if avg_cost is not None: updates.append("avg_cost=?"); params.append(avg_cost)
    if qty is not None: updates.append("qty=?"); params.append(qty)
    if current_pnl is not None: updates.append("current_pnl=?"); params.append(current_pnl)
    if max_profit is not None: updates.append("max_profit=?"); params.append(max_profit)
    if max_drawdown is not None: updates.append("max_drawdown=?"); params.append(max_drawdown)
    if conviction is not None: updates.append("conviction=?"); params.append(conviction)
    if thesis_json is not None: updates.append("thesis_json=?"); params.append(thesis_json)
    if market_state_entered is not None: updates.append("market_state_entered=?"); params.append(market_state_entered)
    if entry_reason is not None: updates.append("entry_reason=?"); params.append(entry_reason)
    
    # 总是更新 updated_at
    from datetime import datetime
    updates.append("updated_at=?")
    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    if updates:
        params.append(symbol)
        sql = f"UPDATE positions SET {', '.join(updates)} WHERE symbol=?"
        c.execute(sql, params)
        conn.commit()
    
    conn.close()

def query(date_from=None, date_to=None, table='ai_analysis', limit=200, offset=0):
    conn = get_conn()
    c = conn.cursor()
    
    # 检查表是否有date列
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    has_date = 'date' in columns
    
    sql = f"SELECT * FROM {table} WHERE 1=1"
    params = []
    if date_from and has_date:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to and has_date:
        sql += " AND date <= ?"
        params.append(date_to)
    if date_from and not has_date:
        sql += " AND timestamp >= ?"
        params.append(date_from)
    if date_to and not has_date:
        sql += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    for row in rows:
        if 'signals_json' in row and row['signals_json']:
            try: row['signals'] = json.loads(row['signals_json'])
            except: row['signals'] = []
    conn.close()
    return rows

def get_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM ai_analysis")
    analyses = c.fetchone()['cnt']
    c.execute("SELECT COUNT(*) as cnt FROM risk_control")
    risk_count = c.fetchone()['cnt']
    c.execute("SELECT COUNT(*) as cnt FROM trade_execution")
    trades = c.fetchone()['cnt']
    c.execute("SELECT COALESCE(SUM(pnl),0) as total FROM trade_execution")
    pnl = c.fetchone()['total']
    c.execute("SELECT COUNT(*) as cnt FROM trade_execution WHERE type='buy'")
    buys = c.fetchone()['cnt']
    c.execute("SELECT COUNT(*) as cnt FROM trade_execution WHERE type='sell'")
    sells = c.fetchone()['cnt']
    conn.close()
    return {
        "analyses": analyses, "trades": trades, "pnl": round(pnl, 2),
        "buys": buys, "sells": sells, "risk_controls": risk_count
    }

def search_all(keyword, limit=100, offset=0):
    """全文搜索三表"""
    conn = get_conn()
    c = conn.cursor()
    kw = f"%{keyword}%"
    rows = []
    
    # 搜索ai_analysis
    c.execute("""SELECT id, timestamp, date, time, reasoning, signals_json, 
        signals_count, executed, 'ai_analysis' as source_table
        FROM ai_analysis WHERE reasoning LIKE ? OR signals_json LIKE ? 
        ORDER BY id DESC LIMIT 50""", (kw, kw))
    for r in c.fetchall():
        d = dict(r)
        if d.get('signals_json'):
            try: d['signals'] = json.loads(d['signals_json'])
            except: d['signals'] = []
        rows.append(d)
    
    # 搜索trade_execution
    c.execute("""SELECT id, timestamp, '' as date, '' as time, symbol, name, type as direction,
        price, qty, amount, pnl, reason, 'trade_execution' as source_table
        FROM trade_execution WHERE name LIKE ? OR reason LIKE ? OR symbol LIKE ?
        ORDER BY id DESC LIMIT 50""", (kw, kw, kw))
    for r in c.fetchall():
        d = dict(r)
        rows.append(d)
    
    # 搜索risk_control
    c.execute("""SELECT id, timestamp, '' as date, '' as time, symbol, reason, 
        result as risk_level, (result='通过') as approved, '' as action_override, 'risk_control' as source_table
        FROM risk_control WHERE reason LIKE ? ORDER BY id DESC LIMIT 50""", (kw,))
    for r in c.fetchall():
        d = dict(r)
        rows.append(d)
    
    total = len(rows)
    rows.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    rows = rows[offset:offset+limit]
    conn.close()
    return rows, total

init_db()
