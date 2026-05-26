<div align="right">

[English](./README-EN.md) | 中文

</div>

<div align="center">

# 🚀 AI Quant Trader

### AI驱动的A股短线量化交易系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg"/>
  <img src="https://img.shields.io/badge/AI-GPT%20%7C%20DeepSeek%20%7C%20Qwen-green"/>
  <img src="https://img.shields.io/badge/License-MIT-orange"/>
  <img src="https://img.shields.io/badge/Status-Active-success"/>
</p>

> 一个具备「认知-执行分离」「动态仓位」「三级风控」「Conviction信念系统」的AI量化交易框架

</div>

---

# ✨ 系统特色

- 🧠 AI智能交易决策
- ⚡ 多模型兼容（OpenAI / DeepSeek / Qwen / GLM / Ollama）
- 🛡️ 三层风控系统
- 📈 动态仓位调节
- 🔄 事件驱动架构
- 📊 实时Web仪表盘
- 💾 SQLite本地数据库
- 🎯 Conviction信念交易系统
- 🔥 龙头行情识别
- 📉 自动止盈止损

---

# 🧠 核心原则

## 认知与执行分离

AI只能从【可交易候选池】中选股。

```text
【第一层：全市场全景】仅观测，不可推荐
   ├── 板块龙头
   ├── 资金主线
   └── 市场情绪

【第二层：可交易候选池】
   ├── 预算限制
   ├── 风险过滤
   └── 可执行标的
```

---

## 手数决策系统

系统核心单位不是“钱”，而是“股数(lot)”。

```python
lots = budget // (price * 100)
shares = lots * 100
```

---

## 风控一票否决

S级风控不可绕过：

- T+1限制
- 硬止损
- 跌停拦截
- Conviction强制卖出

---

## 动态仓位引擎

```python
base_pct = score_to_base_pct(score)

mood = clamp(
    calc_market_mood(),
    0.8,
    1.2
)

pos_mult = winrate_to_multiplier(wr)

budget = cash * min(
    base_pct * mood * pos_mult,
    0.35
)
```

---

# 🏗️ 系统架构

```text
AI Quant Trader
│
├── 市场数据层
├── AI认知层
├── 可交易池过滤层
├── AI执行层
├── 风控系统
└── Dashboard监控层
```

---

# 🚀 快速开始

# 环境要求

- Python 3.9+
- pip
- Windows / Linux / macOS
- 推荐使用 venv

---

# 📦 安装步骤

## 1. 克隆仓库

```bash
git clone https://github.com/yourname/ai-quant-trader.git
cd ai-quant-trader
```

---

## 2. 创建虚拟环境

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. 安装依赖

```bash
pip install -r requirements.txt
```

国内推荐：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

# ⚙️ 配置文件

## AI配置

```bash
cp ai_config.json.example ai_config.json
```

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "your-api-key",
  "model": "gpt-4o",
  "temperature": 0.3
}
```

---

## Research模型配置

```bash
cp ai_config_research.json.example ai_config_research.json
```

---

## 交易配置

```json
{
  "initial_cash": 100000,
  "max_single_position_pct": 0.25,
  "hard_stop_loss": -0.05
}
```

---

# ▶️ 启动系统

## 启动主程序

```bash
python v3_main.py
```

---

## 启动Dashboard

新开终端：

```bash
cd trading-dashboard
python server.py
```

浏览器访问：

```text
http://localhost:8080
```

---

# 📁 项目结构

```text
ai-quant-trader/
│
├── v3/
│   ├── event_bus.py
│   ├── market_structure.py
│   ├── position_lifecycle.py
│   └── experience_layer.py
│
├── v2/
│   ├── risk_engine.py
│   ├── ai_model.py
│   └── db.py
│
├── trading-dashboard/
│   ├── server.py
│   ├── static/
│   └── index.html
│
├── ai_config.json
├── portfolio.json
├── trading_history.db
├── pnl_history.json
├── requirements.txt
├── README.md
├── README-CN.md
└── README-EN.md
```

---

# 🎯 核心机制

# 三级风控体系

| 等级 | 规则 |
|---|---|
| S级 | 硬止损 / T+1限制 |
| A级 | 动态仓位 |
| B级 | 技术退出 |

---

# Conviction信念系统

| 信号 | 变化 |
|---|---|
| 放量突破 | +20 |
| 板块加强 | +15 |
| 量能萎缩 | -15 |
| 跌破均线 | -25 |

低于30触发强制卖出。

---

# 📡 API接口

| 接口 | 方法 |
|---|---|
| /api/all | GET |
| /api/analysis/start | POST |
| /api/analysis/stop | POST |
| /api/history | GET |

---

# 🤖 支持模型

- GPT-4o / o1 / o3
- DeepSeek
- Qwen
- GLM-4
- Moonshot Kimi
- Ollama

---

# 💾 数据存储

| 文件 | 内容 |
|---|---|
| portfolio.json | 持仓状态 |
| trading_history.db | SQLite数据库 |
| pnl_history.json | 收益曲线 |
| ai_trade.log | 系统日志 |

---

# 🗺️ 开发路线

- [x] 多模型支持
- [x] Conviction系统
- [x] Dashboard
- [x] 动态仓位引擎
- [ ] 回测系统
- [ ] 实盘接口
- [ ] 多账户支持

---

# 📊 Dashboard预览

```text
✔ 当前持仓
✔ AI分析状态
✔ 市场情绪
✔ 信念评分
✔ 历史交易
✔ 实时收益率
```

---

# ⚠️ 风险声明

本项目仅供学习研究。

量化交易存在风险：

- AI可能误判
- 市场可能极端波动
- 历史收益不代表未来

请勿直接用于大资金实盘。

---

# 📜 License

MIT License

---

# ⭐ Star History

如果这个项目对你有帮助，欢迎 Star ⭐
