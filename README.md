# 🤖 AI量化交易系统（AI Quant Trader）

<p align="center">
  <a href="./README-CN.md">🇨🇳 中文文档</a> |
  <a href="./README-EN.md">🇺🇸 English Documentation</a>
</p>

## 📌 项目简介

AI量化交易系统是一个基于大模型驱动的智能交易框架，核心目标是：

> 将AI认知能力与交易执行彻底解耦，实现可控、可回测、可扩展的量化交易系统。

系统融合了：

- 🧠 大模型决策（GPT / DeepSeek / Qwen / GLM）
- 📊 实时行情分析与市场结构建模
- 🛡️ 多层级风控体系（S/A/B级）
- 📈 动态仓位管理系统
- 🔁 交易经验学习与胜率反馈
- 🖥️ Web可视化交易面板

---

## ⚙️ 核心设计理念

### 1️⃣ 认知与执行分离

AI **只能从“可交易候选池”中选择标的**：

```
全市场数据（仅观察）
        ↓
可交易候选池（唯一决策区）
        ↓
交易执行系统
```

👉 防止AI越权交易，提高系统可控性

---

### 2️⃣ 手数优先（Lot-Based）

系统核心单位是：

- ✔ 股数 / 手数
- ❌ 不直接使用金额决策

👉 更贴近真实交易行为

---

### 3️⃣ 风控绝对优先（S级不可绕过）

S级风控包括：

- T+1限制
- -5% / -7% / -8% 硬止损
- 跌停禁止交易
- 信念值 < 30 强制清仓

👉 风控优先级高于AI决策

---

### 4️⃣ 仓位连续调节模型

系统不是：

- ❌ 满仓 / 空仓切换

而是：

- ✔ 连续仓位缩放
- ✔ 小仓试错
- ✔ 动态加减仓

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/yourname/ai-quant-trader.git
cd ai-quant-trader
```

---

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv
```

激活环境：

#### Windows
```bash
venv\Scripts\activate
```

#### Mac / Linux
```bash
source venv/bin/activate
```

---

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

---

## ⚙️ 配置说明

### 1️⃣ AI配置文件

`ai_config.json`

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "your-api-key",
  "model": "gpt-4o",
  "temperature": 0.3
}
```

---

### 2️⃣ 交易配置文件

`config.json`

```json
{
  "initial_cash": 100000,
  "max_single_position_pct": 0.25,
  "hard_stop_loss": -0.05
}
```

---

## ▶️ 运行系统

### 启动主程序

```bash
python v3_main.py
```

---

### 启动Web面板

另开终端：

```bash
cd trading-dashboard
python server.py
```

浏览器访问：

```
http://localhost:8080
```

---

## 🧠 系统架构

```
AI认知层
   ↓
候选交易池
   ↓
风控系统（S/A/B）
   ↓
仓位管理系统
   ↓
交易执行层
   ↓
Web可视化面板
```

---

## 📂 项目结构

```
ai-quant-trader/
│
├── v2/                     # 稳定交易核心
│   ├── risk_engine.py      # 风控引擎
│   ├── ai_model.py         # AI适配层
│   └── db.py               # 数据库
│
├── v3/                     # 新一代核心系统
│   ├── event_bus.py
│   ├── market_structure.py
│   ├── position_lifecycle.py
│   └── experience_layer.py
│
├── trading-dashboard/      # Web界面
│   ├── server.py
│   └── static/
│
├── ai_config.json
├── ai_config_research.json
├── portfolio.json
├── requirements.txt
└── v3_main.py
```

---

## 📊 核心交易机制

### 1️⃣ 双层决策架构

```
【市场认知层】
- 只观察
- 不可交易

【交易执行层】
- 只能从候选池选择
```

---

### 2️⃣ 动态仓位模型

```python
base_pct = score_to_base_pct(score)
mood = clamp(market_mood, 0.8, 1.2)
pos_mult = winrate_factor(wr)

budget = cash * min(base_pct * mood * pos_mult, 0.35)
```

---

### 3️⃣ 三层风控系统

| 等级 | 规则 | 是否可覆盖 |
|------|------|------------|
| S级 | 强制止损 / 跌停 / 信念清仓 | ❌ |
| A级 | 仓位调整 / 分批止盈 | ⚠️ |
| B级 | 技术止损 / 时间退出 | ⚠️ |

---

### 4️⃣ 信念值系统（Conviction）

| 信号 | 变化 |
|------|------|
| 放量突破 | +20 |
| 板块加强 | +15 |
| 量能萎缩 | -15 |
| 跌破5日线 | -25 |

```
信念值 < 30 → 强制卖出
```

---

## 📡 API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/all | GET | 全量数据 |
| /api/analysis/start | POST | 启动分析 |
| /api/analysis/stop | POST | 停止分析 |
| /api/ai/config | POST | 更新AI配置 |
| /api/history | GET | 交易记录 |

---

## 🛠️ 支持模型

- GPT-4o / o1 / o3
- DeepSeek 系列
- Qwen 系列
- GLM-4
- Kimi
- 本地 Ollama

---

## 💾 数据存储

| 文件 | 说明 |
|------|------|
| portfolio.json | 账户状态 |
| trading_history.db | SQLite交易记录 |
| pnl_history.json | 收益曲线 |
| ai_trade.log | 系统日志 |

---

## ⚠️ 风险声明

本项目仅用于：

- 学习
- 研究
- 策略验证

不构成任何投资建议。

交易有风险，使用需自担责任。

---

## ⭐ 支持项目

如果觉得有帮助，可以点个 Star ⭐
