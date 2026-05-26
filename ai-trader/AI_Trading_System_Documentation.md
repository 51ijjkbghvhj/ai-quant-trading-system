# AI 量化交易系统 - 完整技术文档 v9.0

## 1. 系统概述

这是一个基于双 AI 模型的 A 股量化交易系统，采用**事件驱动架构**。系统核心设计理念为：
1. **AI 是分析师，不是交易员**：AI 只提供建议和评分，不直接下单。
2. **风控才是裁决者**：所有交易信号必须通过 S/A/B 三级风控审核。
3. **情绪周期 > 技术指标**：系统关注资金行为和市场情绪，而非单纯数学预测。
4. **双脑分离架构**：交易 AI（实时盯盘）与研究 AI（深度复盘）独立运行、单向协同。

---

## 2. 系统架构全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据采集层 (Data Layer)                          │
│  腾讯 API (qt.gtimg.cn) 实时行情  │  新浪 API (finance.sina) 全市场列表      │
│  东方财富 API (eastmoney) 新闻    │  本地缓存 & 内存快照                      │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                           事件检测与压缩层                                    │
│  v3/market_structure.py  (板块聚合 → 龙头识别 → 情绪阶段判断)                │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          双 AI 分析引擎 (AI Engine)                           │
│  🟢 Model A (交易 AI): 90s/次，轻量 Prompt，输出 BUY/HOLD/SELL 信号          │
│  🔵 Model B (研究 AI): 30min/次，深度 Prompt，输出排雷/复盘/策略建议          │
│  v3/event_bus.py  (主循环、Prompt 构建、JSON 解析、信号分发)                  │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    动态仓位引擎 (Dynamic Position Engine)                      │
│  calc_dynamic_budget(): Score 核心 + Mood 微调 + Winrate 调节器              │
│  手数决策系统 | 单票硬顶 35% | 仓位调节器 0.4~1.1                            │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          风控引擎 (Risk Engine) - 最高优先级                   │
│  S 级 (绝对红线) → A 级 (策略控制) → B 级 (技术退出)                           │
│  v2/risk_engine.py  (一票否决权，可覆盖 AI 建议)                              │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          执行与记录层 (Execution Layer)                       │
│  v3/event_bus.py (execute_trade) → v2/db.py (SQLite) → portfolio.json       │
│  更新持仓、写入交易记录、同步收益曲线、记录 AI 日志                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心文件详解

### 3.1 事件总线与主循环 (`v3/event_bus.py`)
**职责**：系统核心调度器，负责数据流转、AI 调用、动态仓位计算、交易执行。
*   **`get_full_market_pool()`**: 获取全市场活跃股票池（缓存 30 分钟），包含持仓+关注池。
*   **`fetch_quotes()`**: 批量获取腾讯 API 实时行情，返回 `{symbol: {price, change_pct, ...}}`。
*   **`fetch_single_quote(symbol)`**: 单独获取非池中股票行情（支持全市场交易）。
*   **`calc_market_mood(market_data)`**: 🆕 动态情绪系数计算。基于 `up_ratio`、`涨停家数`、`跌停家数` 精确区分 10cm/20cm/30cm 涨停，返回 0.2~1.2 的环境系数。
*   **`calc_dynamic_budget(score, cash, recent_wr, has_positions)`**: 🆕 动态仓位计算核心函数（v9.0.3 重构版）。
*   **`main_loop(poll_interval=10)`**: 
    *   动态休眠机制，绝对防止重叠。
    *   每 90 秒运行 `run_cycle()`。
*   **`run_cycle(research_mode=False)`**: 
    *   **交易模式**：获取行情 → 压缩结构 → `call_trading_ai()` → 解析信号 → 动态仓位计算 → 风控审核 → 执行交易 → 更新日志。
    *   **研究模式**：调用 `call_research_ai()` → 输出排雷/复盘建议 → 存入数据库。
*   **`call_trading_ai(...)`**: 🟢 交易 AI 调用。输入**双层架构 Prompt**（市场全景层 + 可交易候选层），返回 `JSON`。
*   **`call_research_ai(...)`**: 🔵 研究 AI 调用。读取独立配置，输入深度数据（历史胜率/避坑记录/基本面），输出 JSON。
*   **`execute_trade(...)`**: 执行买卖。自动补全股票代码前缀，动态计算仓位，调用风控，更新 `portfolio.json`。

### 3.2 市场结构压缩层 (`v3/market_structure.py`)
**职责**：将 200+ 只股票原始数据压缩为"市场结构摘要"，供 AI 阅读。
*   **`build_market_structure(current_data)`**: 入口函数，返回 `market_stage`, `sentiment`, `limit_stats`, `sectors`, `dragons`。
*   **`_aggregate_sectors(...)`**: 板块聚合。通过关键词映射将股票归类，计算板块强度（上涨比/涨停数）。
*   **`_identify_dragons(...)`**: 龙头识别。基于涨幅、换手率、成交量加权评分，找出各板块最强股。
*   **`_judge_stage(...)`**: 阶段判断。根据上涨比、涨跌停数量，输出：高潮/升温/震荡偏多/震荡/震荡偏空/恐慌/低迷。

### 3.3 风控引擎 (`v2/risk_engine.py`)
**职责**：交易系统的"皇帝"，拥有最高决策权。
*   **`check_signal(signal, market_data, positions, ...)`**: 审核单个信号，返回 `RiskResult`。
*   **S 级规则（不可违反）**:
    *   `T+1 限制`：今日买入不可卖。
    *   `硬止损`：主板 -5%，创业板 -7%，科创板 -8%。
    *   `建仓保护期`：买入后 15 分钟内禁止卖。
    *   `冷静期`：卖出后 30 分钟内禁止买。
    *   `Conviction 强制卖出`：Conviction < 30 或 Thesis 已破坏时，强制允许卖出（覆盖保护期）。
    *   `跌停卖出拦截`：现价 <= 跌停价 * 1.01 时无法卖出，标记为 UNEXECUTABLE。
*   **A 级规则（策略控制）**:
    *   `动态仓位`：根据市场阶段限制仓位（50%~90%）。
    *   `EUPHORIA 模式`：高潮期分级限制（v9.0.4更新）：
        *   龙头股：评分≥65 允许交易
        *   非龙头(补涨)：评分≥75 允许试错
        *   评分不足：拦截，防止追高
    *   `分批止盈`：+10% 卖 1/3，+15% 卖 2/3，+20% 清仓。
*   **B 级规则（技术退出）**:
    *   `时间强制退出`：持仓≥7 天清仓。
    *   `技术破位`：跌破 5 日线 + 板块弱 + 缩量。
    *   `冲高回落`：最高涨 5% 现价<2%。
    *   `放量滞涨`：换手率>15% 且涨幅<1%。

### 3.4 仓位生命周期管理 (`v3/position_lifecycle.py`)
**职责**：管理每个持仓的状态机。
*   **状态流转**：`BUILDING (15min)` → `HOLDING` → `EXITING` → `COOLDOWN (30min)`。
*   **`PositionLifecycle.can_buy/sell()`**: 根据当前状态判断是否允许买卖。
*   **`Conviction (信念值)`**: 动态信念系统（0-100），根据市场反馈加减分。低于 30 允许卖，高于 60 允许买。
*   **`Thesis (交易逻辑)`**: 每笔买入携带 `entry_reason` 和 `invalid_conditions`，逻辑破坏才允许卖。

#### 🆕 3.4.1 Conviction 信念值计算 (v9.0.3.1 新增)

> ⚠️ **信号源说明**：Conviction 更新由 `run_cycle` 根据**实时行情数据自动计算**触发，不是 AI 输出。当前仅实现 4 个信号，其余为预留规则。

**初始值**：买入时 `conviction=60`

**已实现信号（4 个）**：

| 信号类型 | 变化量 | 触发条件 |
|:---|:---|:---|
| `volume_breakout` | +20 | 涨幅>3% 且 换手>5% |
| `sector_strength` | +15 | 涨幅>2% |
| `volume_decline` | -15 | 跌幅 且 换手<2% |
| `break_ma5` | -25 | 现价<成本*0.95 |

**预留信号（9 个，待实现）**：

| 信号类型 | 变化量 | 说明 |
|:---|:---|:---|
| `leader_acceleration` | +15 | 龙头加速 |
| `market_recovery` | +10 | 市场修复 |
| `positive_news` | +10 | 正面新闻 |
| `leader_crack` | -40 | 龙头炸板 |
| `break_ma10` | -30 | 跌破10日线 |
| `sector_weakness` | -20 | 板块退潮 |
| `negative_news` | -15 | 负面新闻 |
| `follower_buy` | -10 | 跟风股买入 |
| `leader_firmed` | +20 | 龙头确认（原定义，已合并到 volume_breakout） |

> **更新频率**：每轮 `run_cycle` 调用一次（约 90 秒）。每个信号在每个周期最多触发一次。

**持久化**：`conviction` 和 `state_entered_at` 存储在 `portfolio.json` 每个 batch 中，程序重启后可恢复。

**存储位置**：
- 内存：`PositionManager.positions[sym].conviction`
- 磁盘：`portfolio.json` → `positions[sym][batch].conviction`
- 数据库：`positions` 表 `conviction` 字段

**程序重启恢复流程**：
```
1. 读取 portfolio.json
   ↓
2. 恢复建仓保护期:
   遍历 positions → 每个 batch 检查 state_entered_at
   → 计算 elapsed = now - state_entered_at
   → 若 elapsed < 15min → 恢复 BUILDING 状态
   → 若 elapsed >= 15min → 恢复 HOLDING 状态
   → 同时恢复 conviction 和 thesis_status
   ↓
3. 恢复冷静期:
   读取 cooldown_positions 列表
   → 检查 sell_time + 30min
   → 若未过期 → 恢复 COOLDOWN 状态
   → 若已过期 → 删除该记录
   ↓
4. 两者互不冲突: positions 和 cooldown_positions 存储不同的股票
```

#### 🆕 3.4.1 加仓控制逻辑 (v9.0.3 更新)
**职责**：控制已持仓股票的加仓行为，防止过度集中风险。

**加仓条件检查流程**：
```
AI 推荐 BUY → 检查是否已持仓 →
    ├─ 未持仓 → 正常买入流程
    │
    └─ 已持仓 → 加仓条件检查
        ├─ 单票仓位 >= 15%? → 拒绝加仓
        ├─ 评分 < 85? → 拒绝加仓
        ├─ 现价 >= 涨停价*0.99? → 拒绝加仓
        └─ 全部满足 → 允许加仓（预算减半）
```

**加仓限制参数**：

| 条件 | 限制 | 说明 |
|:---|:---|:---|
| 单票仓位上限 | ≤ 15% | 防止过度集中风险。此15%为**加仓安全阈值**，严于风控的25%绝对上限，目的是为加仓留足安全边际。 |
| ~~T+1限制~~ | ~~今日不可加仓~~ | **已移除**：A股T+1仅限制卖出，不限制买入 |
| 评分要求 | ≥ 85 | 加仓要求更高置信度 |
| 加仓预算 | 原预算 × 50% | 加仓更保守 |

**代码位置**：`v3/event_bus.py` 第 1660-1700 行

### 3.5 AI 模型接口 (`v2/ai_model.py`)
**职责**：兼容所有 OpenAI 格式的 AI 提供商，支持推理模型的JSON提取。
*   **`call_mimo(prompt, system_prompt, json_mode=False)`**: 通用调用函数。支持自动 URL 路径补全。
    *   **JSON模式 (`json_mode=True`)**：使用 `_extract_json()` 函数，通过栈平衡算法精确提取最外层完整JSON对象。
    *   **搜索优先级**：content → reasoning_content → choice.content → text → delta
    *   **推理模型适配**：DeepSeek v4-pro 等模型把思考放入 `reasoning_content`，JSON放入 `content`。当 `content` 为空时，自动从 `reasoning_content` 中提取JSON。
    *   **容错机制**：找不到JSON时返回空字符串，而非返回自然语言思考过程。
*   **`_extract_json(text)`**: 🆕 从任意文本中提取最外层完整JSON对象。支持：
    *   直接JSON字符串
    *   包含Markdown代码块的JSON
    *   JSON前后有自然语言
    *   嵌套JSON对象（使用栈平衡匹配）
*   **`test_connection(...)`**: 测试连接并获取可用模型列表。
*   **`_load_config()`**: 从 `ai_config.json` 加载配置，支持热重载。

### 3.6 经验积累层 (`v3/experience_layer.py`)
**职责**：系统长期记忆的存储与读取。
*   **`commit_experience_cycle(...)`**: 交易后记录到数据库（交易、持仓、结果）。
*   **`update_thesis_stats(...)`**: 自动计算每种交易逻辑的胜率、盈亏比、最大回撤。
*   **`get_ai_context()`**: 供 AI 调用前读取，返回最近 3 天反思、高胜率策略、历史错误记录。

### 3.7 基本面排雷层 (`v3/fundamental_risk_layer.py`)
**职责**：异步扫描持仓和关注池的基本面风险，**不参与风控否决**。
*   **`_analysis_loop(...)`**: 后台静默运行，每 30 分钟扫描一次。
*   **`_analyze_stock_with_skill(...)`**: 调用 AI 生成风险标签（如"高质押"、"ST 风险"、"业绩预增"）。
*   **`get_tags(symbol)`**: 返回缓存的风险标签，供交易 AI 参考。

### 3.8 HTTP 服务器与 API (`trading-dashboard/server.py`)
**职责**：为前端提供数据接口和静态页面服务。
*   **`api()`**: 聚合所有数据（行情/持仓/AI 状态/研究模型）返回给前端。
*   **API 接口列表**:
    *   `GET /api/all` → 聚合数据（前端每 5s 轮询）
    *   `GET /api/analysis/status` → 运行状态 `{"running": bool}`
    *   `POST /api/analysis/start` → 启动分析循环
    *   `POST /api/analysis/stop` → 停止分析循环
    *   `POST /api/ai/config` → 保存交易 AI 配置
    *   `POST /api/ai/test` → 测试 AI 连接并获取模型列表
    *   `GET /api/history` → 数据库历史记录查询
    *   `GET /api/pnl_history` → 收益曲线数据

#### 🆕 3.8.1 后端修复记录 (v9.0.2)
| 修复项 | 说明 |
|:---|:---|
| `import shutil` | 添加缺失的 shutil 模块导入（用于 `save_json` 中的 `shutil.copy2`） |
| `do_POST` 方法 | 添加 `qs = urllib.parse.parse_qs(...)` 定义，修复 POST 请求中 query string 未定义的问题 |

---

## 4. AI 分析完整流程

### 4.1 交易 AI (90 秒/次)
```text
1. 获取实时行情 (fetch_quotes)
   ↓
2. 构建市场结构摘要 (build_market_structure)
   输出：阶段=高潮 | 涨停=100 | 上涨比=80% | 板块=[AI, 半导体] | 龙头=[XX 股份]
   ↓
3. 拼接双层架构 Prompt (call_trading_ai)
   System: "你是短线交易员。输出 JSON...规则：1.最多 3 个 candidate 2.涨停不买 3.T+1 锁定不能卖"
   User: 
   ┌─ 【第一层：全市场全景与观测锚点】
   │   (注：带👁️标的超出预算，仅作主线强度参考，不可推荐)
   │   龙头：XX 股份(+10.0%) 👁️仅观测 (超预算), YY 科技(+5.2%): 12.30 元
   ├─ 【第二层：可交易候选池 (仅买得起)】
   │   - 半导体: AA 电子(8.50 元), BB 微(15.20 元)
   │   - 新能源: CC 股份(10.10 元)
   ├─ 【当前持仓】隆华科技：现价 13.08 盈亏 -4.8%
   ├─ 【资金约束】单票预算上限：2979 元 (即股价需 <= 29.79 元)
   └─ 请严格遵循以下决策逻辑...
   ↓
4. 调用 AI 模型 (call_mimo)
   ↓
5. 解析 JSON 返回
   {
     "market_analysis": {"stage": "高潮", "trend": "情绪亢奋，警惕分化"},
     "position_analysis": [{"symbol": "sz300263", "action": "HOLD", "thesis_status": "VALID"}],
     "candidates": [{"symbol": "sz300174", "name": "元力股份", "score": 88, "action": "BUY", "thesis": "..."}]
   }
   ↓
6. 处理信号
   - 持仓分析：SELL + thesis_status="BROKEN" → 触发卖出
   - 候选信号：BUY + score≥60 → 进入动态仓位层
```

### 4.2 研究 AI (30 分钟/次)
```text
1. 触发条件：距上次运行满 1800 秒
   ↓
2. 读取深度数据
   - 历史交易胜率 (thesis_stats)
   - AI 历史犯错记录 (ai_mistakes)
   - 基本面风险标签 (fundamental_tags)
   ↓
3. 构建深度 Prompt (call_research_ai)
   ↓
4. 调用独立 AI 模型 (切换配置)
   ↓
5. 输出存入数据库
   {"risk_warnings": [...], "strategy_hint": "...", "lessons": "..."}
```

---

## 5. 🆕 双层 Prompt 架构 (认知-执行分离)

### 5.1 设计动机
传统单层 Prompt 存在一个致命缺陷：AI 看到全市场龙头后，会倾向于推荐那些**涨得好但买不起**的高价股，导致"无效信号"泛滥。双层架构通过**物理隔离**认知与执行范围解决这个问题。

### 5.2 架构实现

**第一层：全市场全景与观测锚点 (Cognition Layer)**
*   **内容**：展示所有板块龙头，但超出预算的标的会被标记为 `👁️仅观测 (超预算)`。
*   **作用**：让 AI 知道当前市场资金在攻击什么方向，保持对主线的敏感度。
*   **约束**：Prompt 中明确告知 AI "带👁️的不可推荐"。

**第二层：可交易候选池 (Execution Layer)**
*   **内容**：仅展示 `价格 <= max_price` 的强势股。
*   **计算**：`max_price = (总资产 × 15%) / 100`
*   **作用**：AI 的视线里只有买得起的股票，它别无选择，只能从中挑选。
*   **过滤**：在 Prompt 构建阶段即完成物理过滤，高价股根本不会出现在这一层。

### 5.3 Prompt 示例
```
【第一层：全市场全景与观测锚点】
(注：带👁️标的超出预算，仅作主线强度参考，不可推荐)
龙头：XX 股份(+19.9%) 👁️仅观测 (超预算), YY 科技(+5.2%): 12.30 元

【第二层：可交易候选池 (仅买得起)】
- 半导体: AA 电子(8.50 元), BB 微(15.20 元)
- 新能源: CC 股份(10.10 元)

【资金约束】单票预算上限：2979 元 (即股价需 <= 29.79 元)
请严格遵循以下决策逻辑：
1. 认知主线：参考【第一层】判断资金主攻方向。
2. 执行交易：必须且只能从【第二层】中挑选标的。
3. 宁缺毋滥：如果第二层没有符合逻辑的票，返回空信号 []。
```

### 5.4 AI 调用参数

| 参数 | 交易 AI | 研究 AI |
|:---|:---|:---|
| **temperature** | `0.3` (接近确定性输出) | `0.5` (适度多样性) |
| **max_tokens** | 800 | 512 |
| **模型** | 用户配置 (ai_config.json) | 独立配置 (ai_config_research.json) |

> temperature=0.3 确保交易决策的一致性，避免同一市场状态下两次分析结果差异巨大。

---

## 6. 🆕 动态仓位引擎 v2 (重构版)

### 6.1 核心架构：单核心 + 仓位调节器

**v9.0.3 架构变更**：从"多因子乘法仓位模型"改为"单核心 + 仓位调节器"。

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  Score (核心)│ → │  Mood (微调)  │ → │ Winrate (调节)│
│  决定基础仓位 │    │  ±20%裁剪     │    │  0.4~1.1      │
└─────────────┘    └──────────────┘    └──────────────┘
```

**核心原则**：
- **Score → 决定基础仓位**（主引擎，35%/15%/7%）
- **Mood → 小幅调整**（裁剪到 0.8~1.2，防止过度缩放）
- **Winrate → 仓位调节器**（0.4~1.1，连续缩放不归零，让小仓试错成为可能）

> ⚠️ 旧版问题：多因子乘法会导致"系统锁死"——胜率差 × 情绪差 × 基础仓位 = 几百元，无法交易。
> 新版解决：风控是"仓位调节器"，不是"系统停止器"。

### 6.2 基础档位 (微观信号强度)

> ⚠️ **术语说明**：本节"仓位比例"指**基础仓位比例**（占可用现金的百分比），不是持仓占总资产的比例。后者由风控引擎限制（普通 15%，龙头 20%，绝对上限 25%）。

| 信号强度 (Score) | 基础仓位比例 | 交易含义 |
|:---|:---|:---|
| **≥ 90** | 35% (单票硬顶) | 核心主线确认，逻辑清晰，盈亏比极佳。重仓出击。 |
| **80 ~ 89** | 15% | 标准机会，逻辑成立但有小瑕疵。正常配置。 |
| **70 ~ 79** | 7% | 试错仓。方向可能对，但需要盘中验证。小钱试探。 |
| **< 70** | 0% | 放弃。不确定性太高，不值得花钱买确定性。 |

### 6.3 环境系数 (宏观水位，动态计算)
系统实时扫描当前行情池的 `up_ratio`（上涨家数占比）和 `涨跌停家数`，精确区分 10cm/20cm/30cm 涨停：

| 市场环境特征 | 原始 Mood 值 | 裁剪后值 (仓位计算) | 逻辑 |
|:---|:---|:---|:---|
| **冰点/恐慌** (跌停≥30 或 上涨比≤20%) | `0.2` | `0.8` | 极度缩量，裁剪防止系统锁死 |
| **退潮** (上涨比≤40% 或 涨停≤15) | `0.6` | `0.8` | 赚钱效应差，裁剪防止饿死 |
| **升温** (上涨比≥50% 且 涨停≥40) | `1.2` | `1.2` | **唯一放大档**。赚钱效应扩散 |
| **高潮** (上涨比≥70% 或 涨停≥60) | `1.0` | `1.0` | 情绪过热，维持标准仓位 |
| **震荡/常态** | `0.9` | `0.9` | 偏保守基准 |

> ⚠️ **Mood 双重用途说明**：
> - `calc_market_mood()` 返回原始值 (0.2~1.2)，用于风控引擎判断市场阶段
> - `calc_dynamic_budget` 内裁剪到 [0.8, 1.2]，防止单票预算饿死
> - 风控引擎的总仓位限制（冰点 50%~高潮 90%）使用 market_stage 标签，独立于 Mood
> - 两者控制不同维度：单票预算 vs 总仓位，实际运行中风控做最终兜底

### 6.3.1 高潮期 (EUPHORIA) Conviction 调节

**设计原则**：高潮期盛极而衰，Conviction 应收敛而非膨胀。风控收紧的同时，信念系统也应同步衰减，避免"越涨越难卖"的矛盾。

| 规则 | 值 | 说明 |
|:---|:---|:---|
| 龙头 Conviction 乘数 | `0.8` | 高潮期龙头信号衰减，防止信念锁定 |
| 跟风 Conviction 乘数 | `0.5` | 高潮期跟风信号减半 |

> ⚠️ v9.0.3.1 之前此值为 2.0（加倍），已改为 0.8（衰减）。

### 6.4 状态修正 (仓位调节器)

**v9.0.3 变更**：从"连乘衰减"改为"连续缩放，不归零"。

| 胜率区间 | 仓位乘数 | 行为 |
|:---|:---|:---|
| **< 20%** | `0.4` | 低胜率：小仓试错（不断流） |
| **20% ~ 30%** | `0.7` | 恢复中 |
| **30% ~ 50%** | `0.9` | 接近正常 |
| **50% ~ 60%** | `1.0` | 正常 |
| **> 60%** | `1.1` | 连胜：适度放大 |

**空仓恢复**：空仓时 `pos_mult` 至少恢复到 `0.8`。
- 清仓代表"释放风险"，但不抹除历史
- 系统不会突然"满血复活"，而是从 0.8 起步，逐步恢复到 1.0+
- **优先级**：`pos_mult = max(pos_mult, 0.8)` 只在 `has_positions=False` 时触发
  - 胜率 10% + 空仓 → 0.4 → `max(0.4, 0.8)` = **0.8** (恢复到 0.8)
  - 胜率 70% + 空仓 → 1.1 → `max(1.1, 0.8)` = **1.1** (不被覆盖)
  - 胜率 50% + 持仓 → 1.0 → 不触发空仓恢复 = **1.0** (正常)

> ⚠️ 旧版问题：胜率 10% 时 state_factor=0.5，叠加 mood=0.6，预算只剩 30%，系统慢性死亡。
> 新版行为：胜率 10% 时 pos_mult=0.4，至少保留小仓试错能力，系统不会锁死。

### 6.5 手数决策系统 (Minimum Executable Position Guarantee)

**v9.0.3 变更**：从"强行补钱模型"改为"手数决策系统"。

```python
LOT = 100

# 1. 计算现金能买的最大手数（现金天花板）
max_lots = int(cash // (current_price * LOT))

if max_lots < 1:
    # 现金连 1 手都买不起，彻底放弃
    return "资金不足"

# 2. 基于动态预算计算目标手数（向下取整）
target_lots = int(buy_budget // (current_price * LOT))

# 3. 取交集：至少 1 手，不超过现金能买的最大数量
final_lots = max(1, min(max_lots, target_lots))
qty = final_lots * LOT
```

**核心区别**：

| 特性 | 旧版 (强行补钱) | 新版 (手数决策) |
|:---|:---|:---|
| 逻辑 | `max(budget, min_amount)` | `target_lots → final_lots` |
| 问题 | 预算被人为抬升，风险失真 | 不碰钱，只保证手数不为0 |
| 示例 | 405元 → 强行抬到2057元 | 405元 → target=0手 → final=1手 |

**设计原则**：
- 仓位系统的核心单位不是"钱"，而是"股数（lot）"
- A股硬约束：最小交易单位 = 100股
- 保证订单永远"可执行"（不是0），让订单有资格进入风控层

### 6.6 运行示例
假设手持现金 `18,100` 元。

**场景 A：低胜率 (10%) + Score 78**
*   基础：18,100 × 7% = 1,267 元
*   Mood：0.6 → 裁剪到 0.8
*   Winrate：10% → pos_mult = 0.4
*   预算：1,267 × 0.8 × 0.4 = **405 元**
*   手数：target_lots = int(405 / 20.57 / 100) = 0 → final_lots = max(1, 0) = **1手**
*   结果：100股 × 20.57 = 2,057 元（小仓试错）

**场景 B：连胜 (60%) + Score 92**
*   基础：18,100 × 35% = 6,335 元
*   Mood：1.0 → 裁剪到 1.0
*   Winrate：60% → pos_mult = 1.1
*   预算：6,335 × 1.0 × 1.1 = **6,968 元**
*   手数：target_lots = int(6,968 / 20.57 / 100) = 3 → final_lots = **3手**
*   结果：300股 × 20.57 = 6,171 元（重仓出击）

**场景 C：空仓 + 低胜率 (10%) + Score 90**
*   基础：18,100 × 35% = 6,335 元
*   Mood：0.8
*   Winrate：10% → pos_mult = 0.4 → 空仓恢复到 0.8
*   预算：6,335 × 0.8 × 0.8 = **4,054 元**
*   结果：空仓恢复不让系统锁死，保留重新开始的能力

---

## 7. 风控审核与交易执行流程

### 7.1 风控审核路径
```text
AI 信号：BUY sh600768 (score=75)
   ↓
[动态仓位计算] → 计算 buy_budget → 手数决策 → 确定 qty
   ↓
[S 级检查]
   ├─ T+1? → 今日买入不可卖
   ├─ 建仓保护期(15min)? → 但 Conviction<30 或 Thesis破坏 → 覆盖保护期，强制卖出
   ├─ Conviction≥30 且 Thesis未破坏? → 允许继续
   ├─ 跌停拦截? → 现价<=跌停价*1.01 → 标记UNEXECUTABLE
   └─ 全部通过
   ↓
[A 级检查] → 动态仓位 (当前 60% < 高潮 80% OK) → 单只限制 → EUPHORIA 检查 → 全部通过
   ↓
[B 级检查] → 持仓超时？ → 技术破位？ → 冲高回落？ → 放量滞涨？ → 全部通过
   ↓
✅ 风控通过 (approved=True, reason="风控通过 评分 75")
```

### 7.2 交易执行 (`execute_trade`)
```text
1. 获取实时价格 (market_data / fetch_single_quote)
   ↓
2. 读取信号 score，调用 calc_dynamic_budget() 计算预算
   ↓
3. 手数决策系统：target_lots → final_lots = max(1, min(max_lots, target_lots))
   ↓
4. 如果 qty >= 100:
   - 构建 Signal 对象 & MarketData 对象
   - 调用风控引擎 (check_signal)
   - 如果 approved=True → 创建 Thesis → 更新 portfolio.json → 记录数据库
   - 如果 approved=False → 记录拒绝原因 → 加入关注池
   ↓
5. 如果 qty < 100:
   - 拦截并记录："资金不足 (现价 xxx, 可用现金 xxx)"
```

---

## 8. 前端与后端交互

### 8.1 数据流
```
浏览器 (每 5 秒) 
   → GET /api/all 
   → server.py:api() 
   → 读取 market_data.json, portfolio.json, ai_config.json 
   → 实时获取持仓现价 (fetch_quotes_subset) 
   → 返回 JSON 
   → 前端 render() 刷新 UI
```

### 8.2 AI 分析控制
```
用户点击「启动分析」 
   → POST /api/analysis/start 
   → event_bus.py:start_analysis() 
   → 设置 _running=True 
   → 启动双线程 (交易 AI + 研究 AI)
   → 返回 {"status": "started"} 
   → 前端轮询 /api/analysis/status 更新按钮状态
```

---

## 9. 关键数据文件

| 文件路径 | 内容 | 更新频率 |
|----------|------|----------|
| `ai-trader/portfolio.json` | 资金/持仓/关注池/AI 日志/风控日志 | 每次循环后 |
| `trading-dashboard/market_data.json` | 实时行情/板块/情绪/新闻 | 每次循环后 |
| `ai-trader/ai_config.json` | 交易 AI 配置 | 用户手动保存 |
| `ai-trader/pnl_history.json` | 收益曲线数据 | 每次循环后 |
| `ai-trader/trading_history.db` | SQLite 数据库 (12 张表) | 交易/AI 分析后写入 |
| `ai-trader/ai_trade.log` | 系统运行日志 | 实时追加 |

**数据库表清单**（12 张）：
| 表名 | 用途 | 关键字段 |
|:---|:---|:---|
| `ai_analysis` | AI 分析记录 | timestamp, stage, signals_json |
| `trade_execution` | 交易执行记录 | type, symbol, price, qty, pnl |
| `positions` | 当前持仓 | symbol, status, avg_cost, qty, conviction |
| `thesis_outcomes` | 策略结果 | thesis_type, pnl, result, **quality_flag** |
| `thesis_stats` | 策略统计 | thesis_type, win_rate, profit_factor |
| `daily_reflection` | 每日复盘 | date, reflection_json |
| `ai_mistakes` | AI 错误记录 | timestamp, failure_reason |
| `pattern_memory` | 禁忌模式 | pattern_name, trigger_conditions |
| `market_daily` | 每日行情 | date, market_state, limit_up_count |
| `risk_control` | 风控日志 | symbol, action, result, reason |
| `feature_store` | 技术指标缓存 | symbol, timestamp, macd_dif, macd_dea |
| `sqlite_sequence` | SQLite 自增序列 | name, seq (系统表) |

---

## 10. 系统铁律

1. **AI 不直接交易**：AI 只输出 JSON 建议，必须过 `risk_engine.py`。
2. **认知与执行分离**：AI 只能从【第二层：可交易候选池】中选股，严禁越权推荐。
3. **手数决策系统**：核心单位是"股数（lot）"，不是"钱"。保证订单永远可执行（至少1手），再交给风控审核。
4. **风控一票否决**：S 级规则不可绕过，A 级规则可动态调整，B 级规则提供技术参考。
5. **研究 AI 不干预交易**：只输出标签/建议，存入数据库供参考，不直接触发买卖。
6. **持仓有生命周期**：从买入到卖出必须经过状态机流转，防止无序震荡。
7. **仓位调节器模型**：Score 决定基础仓位，Mood 微调 ±20%，Winrate 连续缩放 (0.4~1.1)，不归零。
8. **加仓受控**：已持仓股票加仓需满足：单票仓位≤15%、评分≥85、预算减半。**已移除T+1加仓限制**（A股T+1仅限制卖出）。
9. **JSON强制约束**：AI输出必须是合法JSON，所有思考过程放入JSON的 `reasoning` 字段。推理模型的思考内容从 `reasoning_content` 中自动提取。
10. **盘后交易支持**：科创板(688)/创业板(300/301/302)支持15:05-15:30盘后固定价格交易，主板仅支持连续竞价时段。

---

## 11. 🆕 更新日志 (v9.0)

### 11.0.1 v9.0.5 (2026-05-25 18:30)
**监控池清洗 + 情绪统计真实化 + UI 交互优化**

#### 🧪 全模块模拟测试
| 模块 | 测试项 | 结果 |
|:---|:---|:---|
| **市场情绪** | 真实涨跌家数计算 | ✅ 已从仅统计指数改为遍历全量个股，修复上涨/下跌显示为 0/5 的问题 |
| **监控池** | 脏数据过滤 | ✅ 后端自动剔除 `price=0` 及格式异常代码，限制返回 200 条，解决前端卡顿 |
| **关注池** | 代码验证逻辑 | ✅ 实现 6 位代码自动补全前缀，屏蔽中文名称搜索，确保零误操作 |
| **API 结构** | 响应完整性 | ✅ 验证 `api()` 函数返回结构正确，包含新增的 `up_ratio` 字段 |

#### 🎨 前端 UI 优化
| 组件 | 修改内容 |
|:---|:---|
| **关注池** | 1. 添加/删除逻辑重构，使用自定义 Toast/Confirm 弹窗<br>2. 布局与监控池对齐 (X 移至右侧)<br>3. 移除名称搜索，改为纯代码验证 |
| **监控池** | 1. 增加数据源清洗，解决下滑显示重复/无效数据的问题<br>2. 性能优化：仅渲染前 150 条，其余折叠 |

### 11.0 v9.0.4 (2026-05-25 下午)
**全模型JSON适配 + 系统级错误修复 + 盘后交易支持**

#### 🆕 全模型JSON适配引擎
| 修复项 | 详情描述 |
|:---|:---|
| **🧠 推理模型JSON提取** | 重构 `ai_model.py` 内容提取逻辑，适配所有OpenAI兼容格式模型：<br>• DeepSeek v4-pro/v4-flash、Qwen、GLM、GPT等全部兼容<br>• 推理模型把思考放入 `reasoning_content`，JSON放入 `content`<br>• 使用栈平衡算法精确提取最外层完整JSON对象<br>• JSON模式按优先级搜索：content → reasoning_content → choice.content → text → delta<br>• 找不到JSON时返回空字符串，而非返回自然语言思考过程 |
| **📝 System Prompt优化** | 针对推理模型优化提示词：<br>• max_tokens 提升至 32768，确保推理模型有足够空间输出JSON<br>• 要求"思考不超过100字"，避免token耗尽<br>• 强调"先构建JSON框架，再填充reasoning字段" |
| **🔧 日志实时输出** | 修复Windows控制台输出缓冲问题：<br>• v3_main.py 添加 `PYTHONUNBUFFERED=1` 环境变量<br>• sys.stdout 设置 line_buffering=True<br>• trade_log 函数增加强制刷新：sys.stdout.flush() + buffer.flush() |

#### 🔴 P0严重错误修复
| 修复项 | 详情描述 |
|:---|:---|
| **💥 卖出清仓后引用空列表** | `event_bus.py` 卖出逻辑：清仓前先保存原始批次信息，再执行清理。修复了清仓后访问 `batches[0]` 导致的 IndexError |
| **💥 name变量未定义** | `risk_engine.py` 涨跌停拦截中使用了未定义的 `name` 变量。修复为从 `signal.name` 获取 |

#### 🟡 P1中等错误修复
| 修复项 | 详情描述 |
|:---|:---|
| **🔄 executed_count重复初始化** | 移除 `run_cycle` 中第1914行的重复初始化，避免覆盖已统计的成交数 |
| **🎯 target_sym与sym不一致** | 买入逻辑统一使用已清洗的 `sym`，不再从 signal 重新解析 `target_sym`，防止持仓添加到错误代码下 |
| **🛑 双重except语句** | 移除 `execute_trade` 中永远不会执行的第二个 `except:` 块 |
| **💰 cash变量过期** | 风控检查前从 `portfolio` 实时获取 `cash`，避免使用函数开始时的旧值 |

#### 🟢 P2与其他修复
| 修复项 | 详情描述 |
|:---|:---|
| **🕐 盘后固定价格交易** | `is_trading_time()` 支持科创板(688)/创业板(300/301/302)的15:05-15:30盘后固定价格交易：<br>• 主板：09:15-11:30, 13:00-15:00<br>• 科创板/创业板：额外支持 15:05-15:30 |
| **📊 清仓逻辑修复** | 卖出时使用 `original_batches` 保存清仓前信息，用于冷静期记录 |
| **🔗 数据库连接安全** | `experience_layer.py` 的 `run_transaction` 增加空值检查，防止连接创建失败时崩溃 |
| **📂 sector_map加载回退** | `market_structure.py` 文件不存在时优雅降级，仅使用关键词匹配 |
| **🎯 高潮期限制优化** | `risk_engine.py` 高潮期买入限制从"完全禁止非龙头"改为分级限制：<br>• 龙头股 ≥65分 允许交易<br>• 非龙头(补涨) ≥75分 允许试错<br>• 评分不足才拦截 |
| **📝 Conviction更新统一** | 统一使用 `PositionLifecycle.update_conviction()` 方法，避免逻辑重复 |

### 11.1 v9.0.3.1 (2026-05-22 下午)
**实盘安全修复 + 文档补全 + 设计矛盾修复**

| 修复项 | 详情描述 |
|:---|:---|
| **🧠 Conviction 动态更新** | 在 `run_cycle` 中根据市场反馈实时调整信念值：<br>• 放量突破(涨幅>3%+换手>5%) → +20<br>• 板块加强(涨幅>2%) → +15<br>• 量能萎缩(跌幅+低换手) → -15<br>• 跌破5日线(现价<成本*0.95) → -25<br>• Conviction<30 → S级强制卖出，不再形同虚设 |
| **📋 Conviction 信号源明确** | 文档区分已实现信号(4个)和预留信号(9个)。信号源为系统根据实时行情自动计算，非AI输出 |
| **💾 保护期持久化** | 程序重启后保护期/冷静期不再丢失：<br>• portfolio.json 中每个 batch 新增 `state_entered_at`、`conviction`、`thesis_status`<br>• `sync_from_portfolio` 恢复状态和信念值<br>• 卖出后写入 `cooldown_positions`，30分钟后自动清理<br>• 文档补充完整恢复流程说明 |
| **📉 跌停卖出处理** | 连续跌停时不再反复尝试卖出：<br>• 跌停拦截时标记 `sell_blocked[sym]`，暂停后续卖出尝试<br>• 现价脱离跌停价后自动清除标记<br>• **新增**:连续3次尝试失败标记为 UNEXECUTABLE，停止重试 |
| **🔄 高潮期 Conviction 改为衰减** | 修复设计矛盾：高潮期 Conviction 乘数从 2.0（加倍）改为 0.8（衰减）。风控收紧的同时，信念系统同步衰减，避免"越涨越难卖" |
| **📊 Mood 双重用途说明** | 文档补充原始 Mood 值 vs 裁剪后值的对比表，解释仓位计算与风控引擎的不同用途 |
| **📖 术语统一** | 区分"基础仓位比例"(占现金)和"持仓占比上限"(占总资产)，消除 35% vs 25% 的混淆<br>• 3.4.1 加仓控制补充说明：15%为加仓安全阈值，严于风控的25%绝对上限 |
| **🌡️ AI 温度参数** | 文档补充交易 AI (temperature=0.3) 和研究 AI (temperature=0.5) 的调用参数 |
| **🗄️ 数据库表清单** | 补充 feature_store 和 sqlite_sequence，从 10 张 → 12 张 |
| **📐 has_positions 交互** | 文档补充空仓恢复的优先级说明：只在 has_positions=False 时触发，不覆盖高胜率值 |
| **📦 分批止盈跟踪** | 文档补充 FIFO 批次卖出机制、数据结构、盈亏计算方式 |
| **📝 风控规则列表对齐** | S级规则列表新增：Conviction 强制卖出、跌停卖出拦截。7.1 风控流程图更新 |

### v9.0.3 (2026-05-22)
**核心重构：仓位引擎 v2 + 手数决策系统 + Bug交易过滤**

| 修复项 | 详情描述 |
|:---|:---|
| **🔄 仓位引擎重构** | 从"多因子乘法模型"改为"单核心 + 仓位调节器"：<br>• Score → 决定基础仓位 (主引擎)<br>• Mood → 小幅调整 (裁剪到 0.8~1.2)<br>• Winrate → 仓位调节器 (0.4~1.1)，不归零<br>• **解决"系统锁死"问题**：胜率差 × 情绪差 × 基础仓位 = 几百元，无法交易 |
| **📊 手数决策系统** | 从"强行补钱模型"改为"手数决策"：<br>• 核心单位从"钱"改为"股数（lot）"<br>• `target_lots → final_lots = max(1, min(max_lots, target_lots))`<br>• 保证订单永远可执行（至少1手），再交给风控审核 |
| **🔓 移除T+1加仓限制** | A股T+1仅限制卖出，不限制买入。移除加仓时的T+1日期检查。加仓现在仅受：单票≤15%、评分≥85、预算减半 三个条件限制。 |
| **🧹 Bug交易过滤** | 胜率计算时过滤 Bug/测试/异常交易：<br>• 通过 reason 字段自动识别过滤<br>• thesis_outcomes 表新增 `quality_flag` 字段 (默认 'normal')<br>• 防止"脏历史"永久污染胜率计算 |
| **🔋 空仓恢复机制** | 空仓时 pos_mult 至少恢复到 0.8：<br>• 清仓代表"释放风险"，但不抹除历史<br>• 系统不会突然"满血复活"，而是从 0.8 起步 |

### v9.0.2 (2026-05-21)
**关键修复：数据一致性、加仓逻辑、风控日志修复**

| 修复项 | 详情描述 |
|:---|:---|
| **📊 数据库同步修复** | 修复 `execute_trade()` 中 positions 表同步缺失问题。BUY 时写入 `INSERT OR REPLACE`，SELL 时写入 `DELETE`，确保 portfolio.json 与数据库 positions 表实时同步。 |
| **🔒 加仓逻辑新增** | 新增完整的加仓控制逻辑：<br>• 单票仓位上限 15%<br>• T+1锁定（今日买入不可加仓）<br>• 评分要求 ≥85<br>• 加仓预算减半（更保守） |
| **🐛 风控日志修复** | 修复风控拒绝日志中 symbol 串台问题。将 `for sym, entry in positions.items()` 改为 `for pos_sym, entry`，避免遍历变量覆盖信号股票代码。 |
| **🖥️ 前端信号显示优化** | 修复 AI 引擎控制台显示"本次无信号"问题。当最新一轮无信号时，向上查找最近 4 条记录中第一条有信号的，并标注信号来源时间。 |
| **⚙️ 后端修复** | 修复 `server.py` 中两个问题：<br>• 添加 `import shutil`（之前缺失）<br>• `do_POST` 方法添加 `qs = urllib.parse.parse_qs(...)`（之前未定义） |
| **🧪 模拟测试验证** | 完成全流程模拟测试（买入→卖出→AI分析→风控→研究AI 4次→数据验证→清理），确认数据同步正确、无混乱问题。 |
| **📝 T+1规则说明** | 明确 T+1 限制的正确行为：AI 判断 BROKEN 但因 T+1 锁定只能 HOLD，次日解锁后才会生成 SELL 信号。 |

### v9.0.1 (2026-05-20 下午)
**关键修复：系统稳定性与数据一致性**

| 修复项 | 详情描述 |
|:---|:---|
| **🔧 幽灵代码移除** | 移除了 `event_bus.py` 中覆盖动态预算的旧逻辑 `min(cash * 0.1, 5000)`，确保仓位严格由动态引擎控制。 |
| **🛡️ 防抖机制 (Anti-Shake)** | 在 `execute_trade` 中增加 5 分钟冷却逻辑 (`last_buy_time` 检查)，彻底杜绝 AI 重复推荐导致的无限循环买入。 |
| **🧪 变量突变修复** | 修复了 `execute_trade` 内部 `sym` 变量被神秘修改为持仓列表最后一个 Key 的诡异 Bug，引入 `target_sym` 锁定信号源代码。 |
| **🧹 数据清洗** | 修复了 `portfolio.json` 中持仓数据混乱（如 `sz300174` 下的错误分组），确保 `positions` 字典键值唯一且对应正确的股票代码。 |
| **💰 资金对齐** | 修正了 `cash` 字段在测试和 Bug 期间产生的误差，通过公式 `Initial - Cost` 重新对齐账户余额。 |
| **📝 日志增强** | 替换了 `save_json` 中的静默失败 (`pass`)，现在文件保存失败会明确记录到 `trade_log`。 |
| **🧠 经验闭环修复** | 修复了研究 AI (Research AI) 结果“阅后即焚”的问题。新增 `save_daily_reflection`，将复盘建议写入数据库，交易 AI 次日起可见，真正实现双脑协同。 |
| **🐛 容错优化** | 修复 `fundamental_risk_layer.py` 处理空 API 响应时的崩溃问题；修复了 `calc_market_mood` 的情绪系数计算逻辑。 |

### v9.0.0 (2026-05-20 上午)
**核心架构：双层 Prompt + 动态仓位引擎**

| 模块 | 更新内容 |
|:---|:---|
| **架构** | 实现认知-执行分离的双层 Prompt 架构（市场全景层 vs 可交易候选层）。 |
| **引擎** | 实现 `calc_dynamic_budget`：基于 Score × 环境系数 × 状态的动态仓位计算。 |
| **风控** | 环境系数精确区分 10cm/20cm/30cm 涨停；高分票 (≥85) 保底放行机制。 |
| **逻辑** | 修复预算计算错误（从总资产 15% 改为现金动态计算）；修复 1 手兼容逻辑。 |

---

**文档版本**: v9.0.4  
**最后更新**: 2026-05-25 下午  
**架构核心**: 双层 Prompt 分离 + 手数决策系统 + 仓位调节器模型 + 三级硬风控 + Conviction 动态信念 + 全模型JSON适配

---

## 11.5 🆕 全模型JSON适配引擎 (v9.0.4 新增)

### 11.5.1 问题背景

推理模型（如 DeepSeek v4-pro）的API返回格式特殊：
- `content` 字段：正式输出（应为JSON）
- `reasoning_content` 字段：推理思考过程（自然语言）

当使用 `json_mode=True` 时，部分推理模型会把JSON放入 `content`，但思考过程占用大量token后，可能导致 `content` 为空，仅有 `reasoning_content` 中的自然语言思考。

### 11.5.2 解决方案

**`_extract_json(text)` 函数**：
```python
def _extract_json(text):
    # 1. 清除Markdown代码块标记
    if '```' in text:
        matches = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if matches:
            text = matches[0]
    
    # 2. 使用栈平衡匹配完整JSON对象
    start = text.find('{')
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start, len(text)):
        char = text[i]
        if char == '\\': escape_next = True; continue
        if char == '"' and not escape_next: in_string = not in_string; continue
        if in_string: continue
        if char == '{': depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0: return text[start:i+1]
    return None
```

**搜索优先级**：
1. `message.content` - 标准格式
2. `message.reasoning_content` - 推理模型格式
3. `choice.content` - 备用位置1
4. `choice.text` - 备用位置2
5. `delta.content` - 流式格式
6. `delta.reasoning_content` - 流式推理

**容错机制**：
- 找不到JSON时返回空字符串 `""`
- 调用方检查空字符串，走fallback逻辑
- 绝不返回自然语言思考过程

### 11.5.3 支持模型列表

| 模型 | content字段 | reasoning_content字段 | JSON提取方式 |
|:---|:---|:---|:---|
| GPT-4o/o1/o3 | ✅ JSON | ❌ 无 | 直接从content获取 |
| DeepSeek v4-flash | ✅ JSON | ❌ 无 | 直接从content获取 |
| DeepSeek v4-pro | ✅ JSON | ✅ 思考过程 | 优先content，空时从reasoning_content提取 |
| Qwen-Max/Plus | ✅ JSON | ❌ 无 | 直接从content获取 |
| GLM-4 | ✅ JSON | ❌ 无 | 直接从content获取 |
| Kimi (Moonshot) | ✅ JSON | ❌ 无 | 直接从content获取 |
| 本地Ollama | ✅ JSON | 取决于模型 | 统一提取逻辑 |

---

## 11.6 🆕 盘后固定价格交易 (v9.0.4 新增)

### 11.6.1 交易时间规则

| 板块 | 连续竞价 | 盘后固定价格 |
|:---|:---|:---|
| 主板 (60/00开头) | 09:30-11:30, 13:00-15:00 | ❌ 不支持 |
| 科创板 (688开头) | 09:30-11:30, 13:00-15:00 | ✅ 15:05-15:30 |
| 创业板 (300/301/302) | 09:30-11:30, 13:00-15:00 | ✅ 15:05-15:30 |

### 11.6.2 代码实现

```python
def is_trading_time(symbol=None):
    m = now.hour * 60 + now.minute
    # 正常交易时段
    normal_trading = (555 <= m <= 690) or (780 <= m <= 900)
    
    # 盘后固定价格 (仅科创板/创业板)
    after_hours_trading = False
    if 905 <= m <= 930 and symbol:
        sym_upper = symbol.upper()
        if (sym_upper.startswith('SH688') or 
            sym_upper.startswith('SZ300') or 
            sym_upper.startswith('SZ301') or 
            sym_upper.startswith('SZ302')):
            after_hours_trading = True
    
    return normal_trading or after_hours_trading
```

### 11.6.3 注意事项

- 盘后固定价格交易以**收盘价**成交，不支持限价委托
- 系统在盘后时段仅处理科创板/创业板股票的卖出信号
- 买入信号在盘后时段通常不执行（需以收盘价成交，无法控制成本）

---

## 12. 🧮 动态仓位引擎 v2 (重构版 Deep Dive)

动态仓位引擎 (`calc_dynamic_budget`) 是系统的核心决策组件，负责根据**信号质量**、**市场环境**和**账户状态**计算最优买入预算。

### 12.1 架构变更 (v9.0.3)

**旧版 (v9.0.0-v9.0.2)**：多因子乘法模型
```python
Final_Budget = Cash * min(Base_Pct * Mood_Factor * State_Factor, 0.35)
```
问题：胜率 10% × 情绪 0.2 × 基础 7% = 0.0014，18000元现金只剩 25元，系统锁死。

**新版 (v9.0.3+)**：单核心 + 仓位调节器
```python
base_pct = score_to_base_pct(score)  # Score 决定核心
mood = calc_market_mood()
mood = max(0.8, min(1.2, mood))      # 裁剪到 ±20%
pos_mult = winrate_to_multiplier(wr) # 仓位调节器

Final_Budget = Cash * min(base_pct * mood * pos_mult, 0.35)
```

### 12.2 核心参数详解

| 参数 | 说明 | 逻辑 | 示例 |
|:---|:---|:---|:---|
| **Base_Pct** | 基础仓位比例 | 基于 AI 评分 (Score) 分档：<br>• **≥90**: 35% (单票硬顶)<br>• **≥80**: 15%<br>• **≥70**: 7%<br>• **<70**: 0% (不操作) | Score 92 → 35%<br>Score 82 → 15% |
| **Mood_Factor** | 市场情绪系数 | 基于全市场广度动态计算，**裁剪到 [0.8, 1.2]**：<br>• 恐慌/冰点: 0.2 → 裁剪到 **0.8**<br>• 退潮: 0.6 → 裁剪到 **0.8**<br>• 震荡: 0.9 → **0.9**<br>• 升温: 1.2 → **1.2**<br>• 高潮: 1.0 → **1.0** | 大盘大跌 → 0.8<br>普涨行情 → 1.2 |
| **Pos_Multiplier** | 仓位调节器 | 基于近期胜率连续缩放，**不归零**：<br>• **WR < 0.2**: 0.4 (小仓试错)<br>• **0.2 ~ 0.3**: 0.7 (恢复中)<br>• **0.3 ~ 0.5**: 0.9 (接近正常)<br>• **0.5 ~ 0.6**: 1.0 (正常)<br>• **> 0.6**: 1.1 (连胜放大)<br>• **空仓时**: 至少 0.8 | 胜率 10% → 0.4<br>胜率 50% → 1.0 |

### 12.3 手数决策系统

**核心逻辑**：
```python
LOT = 100
max_lots = int(cash // (price * LOT))
if max_lots < 1: return 0  # 现金不够1手，彻底放弃
target_lots = int(buy_budget // (price * LOT))
final_lots = max(1, min(max_lots, target_lots))
qty = final_lots * LOT
```

**设计原则**：
1. 仓位系统的核心单位是"股数"，不是"钱"
2. 保证订单永远"可执行"（不是0），让订单有资格进入风控层
3. 预算是"想买多少"，手数系统保证"至少能买1手"

### 12.4 分批止盈与部分卖出跟踪

**A 级规则**：+10% 卖 1/3，+15% 卖 2/3，+20% 清仓。

**实现机制**：
- `portfolio.json` 中每个持仓使用**批次列表**（batches），支持部分卖出
- 卖出时 FIFO 扣除旧批次：`while rem > 0 and batches: ...`
- 部分卖出后，剩余批次的 `cost_price` 不变，`qty` 减少
- 盈亏计算：`(current_price - avg_cost) * sold_qty`，每次卖出单独计算

**数据结构**：
```json
"positions": {
  "sz300410": [
    {"qty": 100, "cost_price": 11.04, "buy_date": "2026-05-22"},
    {"qty": 200, "cost_price": 11.20, "buy_date": "2026-05-23"}
  ]
}
```

**状态持久化**：每个 batch 包含 `state_entered_at`、`conviction`、`thesis_status`，程序重启后可恢复保护期和信念值。

### 12.5 Bug交易过滤

胜率计算时自动过滤非正常交易：
```python
# 过滤关键词
skip_keywords = ['bug', '测试', 'error', '异常', 'api错误', '串台', '幻觉']
```

| 交易类型 | 是否计入胜率 |
|:---|:---|
| 正常交易 | ✅ 计入 |
| Bug 交易 | ❌ 不计入 |
| 测试单 | ❌ 不计入 |
| 数据异常 | ❌ 不计入 |
| API 错误 | ❌ 不计入 |

数据库表 `thesis_outcomes` 新增 `quality_flag` 字段（默认 'normal'），为将来更精细的交易分类留扩展空间。
