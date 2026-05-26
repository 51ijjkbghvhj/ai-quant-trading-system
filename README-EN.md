<div align="right">

English | [中文](./README-CN.md)

</div>

<div align="center">

# 🚀 AI Quant Trader

### AI-Driven A-Share Quant Trading System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg"/>
  <img src="https://img.shields.io/badge/AI-GPT%20%7C%20DeepSeek%20%7C%20Qwen-green"/>
  <img src="https://img.shields.io/badge/License-MIT-orange"/>
  <img src="https://img.shields.io/badge/Status-Active-success"/>
</p>

> An AI-powered short-term trading framework with dynamic position sizing, conviction-based execution, and multi-layer risk control.

</div>

---

# ✨ Features

- 🧠 AI-driven trading decisions
- ⚡ Multi-model support
- 🛡️ Triple-layer risk engine
- 📈 Dynamic position sizing
- 🔄 Event-driven architecture
- 📊 Real-time dashboard
- 💾 SQLite local database
- 🎯 Conviction-based trading
- 🔥 Sector leader detection
- 📉 Auto stop-loss / take-profit

---

# 🧠 Core Principles

## Cognitive-Execution Separation

AI can ONLY select stocks from the tradable candidate pool.

```text
Layer 1: Full Market Observation
- Sector leaders
- Capital flow
- Market themes

Layer 2: Tradable Candidate Pool
- Budget constrained
- Risk filtered
- Executable only
```

---

## Lot-Based Position System

The system uses LOTS instead of direct cash allocation.

```python
lots = budget // (price * 100)
shares = lots * 100
```

---

## Risk Control Override

S-Level rules cannot be bypassed.

Includes:

- T+1 restriction
- Hard stop-loss
- Limit-down interception
- Forced sell on low conviction

---

## Dynamic Position Engine

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

# 🏗️ Architecture

```text
AI Quant Trader
│
├── Market Data Layer
├── AI Cognition Layer
├── Tradable Pool Filter
├── AI Execution Layer
├── Risk Control System
└── Dashboard Monitoring
```

---

# 🚀 Quick Start

# Requirements

- Python 3.9+
- pip
- Windows / Linux / macOS
- Recommended: virtualenv

---

# 📦 Installation

## 1. Clone Repository

```bash
git clone https://github.com/yourname/ai-quant-trader.git
cd ai-quant-trader
```

---

## 2. Create Virtual Environment

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

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# ⚙️ Configuration

## AI Config

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

## Research Model Config

```bash
cp ai_config_research.json.example ai_config_research.json
```

---

## Trading Config

```json
{
  "initial_cash": 100000,
  "max_single_position_pct": 0.25,
  "hard_stop_loss": -0.05
}
```

---

# ▶️ Run

## Start Trading Engine

```bash
python v3_main.py
```

---

## Start Dashboard

```bash
cd trading-dashboard
python server.py
```

Open browser:

```text
http://localhost:8080
```

---

# 📁 Project Structure

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

# 🎯 Core Systems

# Triple-Layer Risk Engine

| Level | Description |
|---|---|
| S | Hard stop-loss / T+1 restriction |
| A | Dynamic position scaling |
| B | Technical exits |

---

# Conviction System

| Signal | Change |
|---|---|
| Breakout | +20 |
| Sector Strength | +15 |
| Weak Volume | -15 |
| MA Breakdown | -25 |

Forced sell below conviction 30.

---

# 📡 API Endpoints

| Endpoint | Method |
|---|---|
| /api/all | GET |
| /api/analysis/start | POST |
| /api/analysis/stop | POST |
| /api/history | GET |

---

# 🤖 Supported Models

- GPT-4o / o1 / o3
- DeepSeek
- Qwen
- GLM-4
- Moonshot Kimi
- Ollama

---

# 💾 Data Storage

| File | Purpose |
|---|---|
| portfolio.json | Portfolio |
| trading_history.db | SQLite Database |
| pnl_history.json | PnL Curve |
| ai_trade.log | Logs |

---

# 🗺️ Roadmap

- [x] Multi-model support
- [x] Conviction system
- [x] Dashboard UI
- [x] Dynamic position engine
- [ ] Backtesting engine
- [ ] Live broker integration
- [ ] Multi-account support

---

# 📊 Dashboard Preview

```text
✔ Portfolio Monitoring
✔ AI Analysis Status
✔ Market Mood
✔ Conviction Tracking
✔ Trading History
✔ Real-time PnL
```

---

# ⚠️ Disclaimer

This project is for educational and research purposes only.

Trading involves risks.

Do NOT use directly in real-money trading without sufficient testing.

---

# 📜 License

MIT License

---

# ⭐ Support

If this project helps you, please give it a Star ⭐
