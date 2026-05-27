"""
Feature Store - 结构化特征库 (Trend Context Layer)
职责：记录实时行情与趋势背景，供 Experience Layer 归因。
定位：趋势背景数据，严禁直接作为交易信号。
原则：
1. 获取真实的日 K 线数据。
2. 将指标转化为语义化描述 (如 "多头排列", "高位震荡")。
3. 绝不使用模拟数据。
"""
import os
import sys
import json
import threading
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 导入真实的 K 线获取模块
from v3.kline_fetcher import get_kline_data

def calculate_and_store_features(symbol: str, current_data: dict, market_state: str):
    """
    在后台线程中计算特征并入库。
    """
    try:
        price = current_data.get('price', 0)
        if price <= 0: return

        # 1. 获取实时快照数据
        chg = current_data.get('change_pct', 0.0)
        turnover_rate = current_data.get('turnover_rate', 0.0)
        capital_flow_proxy = (chg * 0.6 + turnover_rate * 0.4)

        # 2. 获取 K 线技术指标 (Trend Context Layer)
        kline_indicators = get_kline_data(symbol)
        
        # 默认值
        k_ma5 = 0.0
        k_ma20 = 0.0
        k_macd_dif = 0.0
        k_macd_dea = 0.0
        k_macd_hist = 0.0
        k_rsi = 0.0
        
        # 语义化背景字段
        trend_direction = "Unknown"
        trend_strength = "Weak"
        ma_structure = "Unknown"
        volatility_state = "Normal"
        
        ma5_dist = 0.0
        ma20_dist = 0.0

        if kline_indicators:
            k_ma5 = kline_indicators.get('ma5', 0.0)
            k_ma20 = kline_indicators.get('ma20', 0.0)
            k_macd_dif = kline_indicators.get('macd_dif', 0.0)
            k_macd_dea = kline_indicators.get('macd_dea', 0.0)
            k_macd_hist = kline_indicators.get('macd_hist', 0.0)
            k_rsi = kline_indicators.get('rsi', 0.0)
            
            # --- 语义化计算 (转换为 AI 易读的文本) ---
            
            # A. 均线距离 (乖离率)
            if k_ma5 > 0:
                ma5_dist = (price - k_ma5) / k_ma5
            if k_ma20 > 0:
                ma20_dist = (price - k_ma20) / k_ma20
            
            # B. 趋势方向 (Trend Direction)
            # 逻辑：价格 > MA20 且 MA5 > MA20 视为向上
            if price > k_ma20 and k_ma5 > k_ma20:
                trend_direction = "Upward"
            elif price < k_ma20 and k_ma5 < k_ma20:
                trend_direction = "Downward"
            else:
                trend_direction = "Sideways"
            
            # C. 均线结构 (MA Structure)
            # 逻辑：MA5 和 MA20 的斜率及排列
            if k_ma5 > k_ma20 and ma5_dist > 0:
                ma_structure = "Long_Bullish" # 多头
            elif k_ma5 < k_ma20 and ma5_dist < 0:
                ma_structure = "Short_Bearish" # 空头
            else:
                ma_structure = "Entangled" # 纠缠/震荡
            
            # D. 趋势强度 (Trend Strength)
            # 逻辑：MACD 柱状体大小 + 乖离率
            macd_momentum = abs(k_macd_hist)
            if macd_momentum > 0.1 or abs(ma5_dist) > 0.05: # 阈值视股价而定，这里做归一化处理较难，简单判断
                trend_strength = "Strong"
            else:
                trend_strength = "Normal"
                
            # E. 波动率状态 (Volatility State)
            # 逻辑：通过 RSI 的极端值辅助判断，或者 K 线实体大小（这里简化用 RSI 辅助）
            if k_rsi > 80 or k_rsi < 20:
                volatility_state = "Extreme"
            elif k_rsi > 70 or k_rsi < 30:
                volatility_state = "High"
            else:
                volatility_state = "Normal"

        # 3. 写入数据库
        from v2.db import get_conn
        conn = get_conn()
        c = conn.cursor()
        
        # 插入语句需包含新增的语义字段
        c.execute("""INSERT INTO feature_store 
        (symbol, timestamp, macd_dif, macd_dea, macd_hist, rsi_6, ma5_dist, ma20_dist, 
         volume_ratio, capital_flow_proxy, raw_data_snapshot, 
         trend_direction, trend_strength, ma_structure, volatility_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            symbol,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            k_macd_dif, k_macd_dea, k_macd_hist, k_rsi, 
            ma5_dist, ma20_dist,
            0.0, # Volume Ratio (暂不可用)
            capital_flow_proxy, 
            json.dumps(current_data, ensure_ascii=False)[:500],
            trend_direction,
            trend_strength,
            ma_structure,
            volatility_state
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"[FeatureStore] Error calculating features for {symbol}: {e}")

def update_features_async(symbol, current_data, market_state):
    """启动后台线程更新特征"""
    t = threading.Thread(target=calculate_and_store_features, args=(symbol, current_data, market_state))
    t.daemon = True
    t.start()
