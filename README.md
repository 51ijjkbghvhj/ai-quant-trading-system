# 🤖 AI Quant Trader - 双AI驱动的A股量化交易系统

> **核心设计理念：AI是分析师，不是交易员。风控才是裁决者。**

基于双AI模型的A股量化交易系统，采用**事件驱动架构**和**三层风控体系**。交易AI每90秒实时盯盘，研究AI每30分钟深度复盘，两者独立运行、单向协同。

---

## 📊 系统亮点

| 特性 | 说明 |
|:---|:---|
| 🧠 **双脑分离** | 交易AI（实时盯盘）+ 研究AI（深度复盘），互不干扰 |
| 🛡️ **三级风控** | S级绝对红线 → A级策略控制 → B级技术退出，一票否决 |
| 📦 **手数决策系统** | 核心单位是“股数”而非“钱”，保证订单可执行 |
| 🎯 **动态仓位引擎** | Score决定基础仓位，Mood微调，Winrate连续缩放(0.4~1.1) |
| 💪 **Conviction信念系统** | 根据市场反馈动态调整持仓信心，<30强制卖出 |
| 🌊 **情绪周期优先** | 关注资金行为和市场情绪，而非单纯数学预测 |
| 🔌 **全模型兼容** | 支持GPT、DeepSeek、Qwen、GLM、Kimi等所有OpenAI格式模型 |

---

## 🏗️ 系统架构
数据采集层 (腾讯/新浪/东方财富API)
↓
事件检测与压缩层 (板块聚合 → 龙头识别 → 情绪判断)
↓
双AI分析引擎 (交易AI 90s/次 + 研究AI 30min/次)
↓
动态仓位引擎 (Score + Mood + Winrate 三因子)
↓
风控引擎 (S/A/B 三级审核，最高优先级)
↓
执行与记录层 (SQLite + JSON持久化)

### 核心原则

- **认知与执行分离**：AI只能从【可交易候选池】中选股
- **手数决策系统**：核心单位是“股数(lot)”，不是“钱”
- **风控一票否决**：S级规则不可绕过，可覆盖AI建议
- **仓位调节器模型**：连续缩放不归零，小仓试错永不锁死

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- 虚拟环境 (推荐)

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourname/ai-quant-trader.git
cd ai-quant-trader

# 安装依赖
pip install -r requirements.txt

###配置

1.复制配置文件模板
  cp ai_config.json.example ai_config.json
  cp ai_config_research.json.example ai_config_research.json

2.编辑 AI 配置 (ai_config.json)
  {
  "base_url": "https://api.openai.com/v1",
  "api_key": "your-api-key",
  "model": "gpt-4o",
  "temperature": 0.3
  }
3.编辑交易配置 (config.json)
  {
  "initial_cash": 100000,
  "max_single_position_pct": 0.25,
  "hard_stop_loss": -0.05
  }

###运行

# 启动主程序
python v3_main.py

# 启动Web仪表盘 (另开终端)
cd trading-dashboard
python server.py

# 浏览器访问 http://localhost:8080

📁 项目结构

ai-quant-trader/
├── v3/
│   ├── event_bus.py           # 核心调度器、主循环
│   ├── market_structure.py    # 市场结构压缩、板块聚合
│   ├── position_lifecycle.py  # 持仓生命周期管理
│   └── experience_layer.py    # 经验积累、策略胜率统计
├── v2/
│   ├── risk_engine.py         # 三级风控引擎 (最高优先级)
│   ├── ai_model.py            # 全模型JSON适配层
│   └── db.py                  # SQLite数据库操作
├── trading-dashboard/
│   ├── server.py              # HTTP API服务
│   ├── static/                # 前端页面
│   └── index.html             # 仪表盘UI
├── ai_config.json             # 交易AI配置
├── portfolio.json             # 持仓/资金状态
├── requirements.txt
└── README.md


🎯 核心机制详解
1. 双层Prompt架构 (认知-执行分离)
【第一层：全市场全景】仅观测，不可推荐
   ├── 板块龙头：XX股份(+10%) 👁️超预算
   └── 资金主线：AI算力、半导体
   
【第二层：可交易候选池】只能从这里选
   ├── AA电子(8.50元) ← 预算内
   └── BB科技(15.20元) ← 预算内

【资金约束】单票预算上限：2979元 (股价需 ≤ 29.79元)
2. 动态仓位引擎 v2
# 单核心 + 仓位调节器模型
base_pct = score_to_base_pct(score)  # ≥90:35%, ≥80:15%, ≥70:7%
mood = clamp(calc_market_mood(), 0.8, 1.2)   # 裁剪到±20%
pos_mult = winrate_to_multiplier(wr)         # 0.4~1.1 连续缩放

budget = cash * min(base_pct * mood * pos_mult, 0.35)
3. 三级风控体系
级别	规则	不可绕过
S级	T+1限制、硬止损(-5%/-7%/-8%)、跌停拦截、Conviction<30强制卖	✅
A级	动态仓位、高潮期分级限制(龙头65/跟风75)、分批止盈	❌
B级	时间强制退出(7天)、技术破位、冲高回落、放量滞涨	❌
4. Conviction信念系统
信号	变化	触发条件
放量突破	+20	涨幅>3% 且 换手>5%
板块加强	+15	涨幅>2%
量能萎缩	-15	跌幅 且 换手<2%
跌破5日线	-25	现价 < 成本×0.95
初始值60，<30触发S级强制卖出

📡 API接口
端点	方法	说明
/api/all	GET	聚合数据(行情/持仓/AI状态)
/api/analysis/status	GET	分析运行状态
/api/analysis/start	POST	启动分析循环
/api/analysis/stop	POST	停止分析循环
/api/ai/config	POST	保存AI配置
/api/history	GET	历史交易记录
🛠️ 支持的模型
模型	兼容性	备注
GPT-4o / o1 / o3	✅ 完全兼容	原生JSON模式
DeepSeek v4-pro	✅ 完全兼容	自动提取reasoning_content
DeepSeek v4-flash	✅ 完全兼容	
Qwen-Max/Plus	✅ 完全兼容	
GLM-4	✅ 完全兼容	
Kimi (Moonshot)	✅ 完全兼容	
本地Ollama	✅ 完全兼容	
📊 数据存储
文件	内容	更新频率
portfolio.json	持仓/资金/信念值	每次交易后
trading_history.db	SQLite数据库(12张表)	实时
pnl_history.json	收益曲线	每次循环后
ai_trade.log	系统日志	实时
⚠️ 重要提示
AI不直接交易 - 所有信号必须通过风控引擎审核

认知与执行分离 - AI只能从可交易候选池中选股

风控一票否决 - S级规则不可绕过

手数决策系统 - 核心单位是“股数”，不是“钱”

本系统仅供学习和研究使用 - 实盘交易风险自负

🗺️ 路线图
双AI分离架构 (交易+研究)

三级风控体系

动态仓位引擎 v2

Conviction信念系统

全模型JSON适配

盘后固定价格交易

回测引擎

⭐ 如果这个项目对你有帮助，欢迎Star支持！
