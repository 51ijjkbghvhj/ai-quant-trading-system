"""
Fundamental Risk Layer - 异步财务背景层 (v7.6 动态配置版)
职责：分析持仓和关注池股票的基本面风险，提取标签供 AI 参考。
数据源：严格读取 ai_config.json，使用用户配置的 AI 模型。
原则：
1. 绝对不阻塞主循环（后台线程运行）。
2. 严格输出 JSON 风险标签，不生成冗余文本。
3. 仅作为 AI 的背景信息，不参与风控否决。
4. **动态配置**：不使用任何硬编码模型，完全跟随系统设置。
"""

import os
import sys
import json
import threading
import time
import re
import requests
from datetime import datetime

# 线程安全的标签存储
_fundamental_tags = {}
_tags_lock = threading.Lock()

# 🆕 动态指向 user_data (指向根目录 OH-WorkSpace)
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 3个 parent 回到根目录
USER_DATA_DIR = BASE_DIR / "user_data"
CONFIG_PATH = str(USER_DATA_DIR / "ai_config.json")

def get_tags(symbol):
    """获取某只股票的风险标签"""
    with _tags_lock:
        return _fundamental_tags.get(symbol, {})

def _get_ai_config():
    """读取系统当前的 AI 配置"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return {
            "api_url": config.get("api_url", ""),
            "api_key": config.get("api_key", ""),
            "model": config.get("model", "")
        }
    except Exception as e:
        print(f"[基本面层] 加载 AI 配置错误: {e}")
        return None

def _analyze_stock_with_skill(symbol, name):
    """
    【核心接口】调用系统配置的 AI 进行风险扫描。
    注意：这里直接发起 HTTP 请求，严格使用配置文件中的模型参数。
    """
    config = _get_ai_config()
    if not config or not config['api_key']:
        return {"risk_level": "error", "tags": ["未配置 AI Key"], "reason": "请在前端设置 AI 配置"}

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}"
        }
        
        # 强制使用配置的模型
        payload = {
            "model": config['model'],
            "messages": [
                {
                    "role": "system",
                    "content": """你是一个资深的 A 股财务与基本面风险分析师。
你的任务是分析给定的股票，并以纯 JSON 格式输出其基本面风险标签。
不要输出任何解释性文字，只输出 JSON。

JSON 格式要求：
{
  "risk_level": "low" 或 "medium" 或 "high",
  "tags": ["标签 1", "标签 2"], 
  "reason": "一句话简述核心风险或亮点"
}

标签词库参考：
风险类："业绩亏损", "ST 风险", "股东减持", "巨额解禁", "高质押", "商誉减值"
机会类："业绩预增", "行业龙头", "高分红", "国企改革"

注意：必须保证 JSON 格式合法。"""
                },
                {
                    "role": "user",
                    "content": f"请快速分析以下 A 股的基本面风险：代码：{symbol}，名称：{name}。请输出 JSON 分析结果。"
                }
            ],
            "max_tokens": 300,
            "temperature": 0.1
        }

        print(f"  -> 调用 AI: {config['model']} 分析 {symbol}...")
        
        # 智能处理 API URL 路径 (确保包含 /chat/completions)
        api_url = config['api_url']
        if not api_url.endswith('/chat/completions'):
            if api_url.endswith('/v1'):
                api_url += '/chat/completions'
            elif not api_url.endswith('/'):
                api_url += '/chat/completions'
        
        print(f"  -> API 端点: {api_url}")

        # 发起请求 (设置超时 60 秒)
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        # 防崩修复：检查响应体是否为空
        if not response.text or len(response.text.strip()) == 0:
            return {"risk_level": "error", "tags": ["AI 响应为空"], "reason": "接口返回了空数据"}
            
        result_json = response.json()
        content = result_json.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # 清洗并解析 JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            return {
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "risk_level": result.get("risk_level", "unknown"),
                "tags": result.get("tags", []),
                "reason": result.get("reason", "")
            }
        else:
            return {"risk_level": "unknown", "tags": ["解析失败"], "reason": content[:50]}

    except requests.exceptions.Timeout:
        return {"risk_level": "error", "tags": ["超时"], "reason": "AI 请求超时"}
    except Exception as e:
        print(f"[基本面层] 分析失败: {e}")
        return {"risk_level": "error", "tags": ["分析错误"], "reason": str(e)}

def _analysis_loop(portfolio_path, interval=3600):
    """后台分析循环"""
    first_run = True
    
    while True:
        try:
            targets = []
            
            # 1. 收集目标：持仓 + 关注池
            try:
                with open(portfolio_path, 'r', encoding='utf-8') as f:
                    pf = json.load(f)
                    for sym, pos_data in pf.get("positions", {}).items():
                        # 适配多批次结构：pos_data 现在是列表
                        if isinstance(pos_data, list):
                            name = pos_data[0].get("name", "") if pos_data else ""
                        else:
                            name = pos_data.get("name", "")
                        targets.append({"symbol": sym, "name": name})
                    for w in pf.get("watchlist", []):
                        if w.get("symbol") not in [t["symbol"] for t in targets]:
                            targets.append({"symbol": w["symbol"], "name": w.get("name", "")})
            except Exception as e:
                print(f"[基本面层] 加载持仓数据错误: {e}")

            # 2. 执行分析
            if targets and first_run:
                
                # 限制每次循环分析数量，防止 API 限流
                for target in targets[:5]: 
                    sym = target["symbol"]
                    name = target["name"]
                    
                    if not sym: continue
                    
                    # 检查缓存 (4 小时内有效，避免重复请求浪费 Token)
                    current_data = get_tags(sym)
                    if current_data.get("timestamp") and not first_run:
                        try:
                            last_time = datetime.strptime(current_data["timestamp"], '%Y-%m-%d %H:%M:%S')
                            if (datetime.now() - last_time).total_seconds() < 14400:
                                continue
                        except:
                            pass

                    result = _analyze_stock_with_skill(sym, name)
                    with _tags_lock:
                        _fundamental_tags[sym] = result
                    
                    # API 请求间隔保护
                    time.sleep(5)
            
            first_run = False
            
            # 循环休眠
            time.sleep(interval)
            
        except Exception as e:
            print(f"[基本面层] 循环错误: {e}")
            time.sleep(60)

def start_layer(portfolio_path):
    """启动财务背景层"""
    t = threading.Thread(target=_analysis_loop, args=(portfolio_path, 3600), daemon=True)
    t.start()
    print("[基本面层] 后台分析层已启动。")
