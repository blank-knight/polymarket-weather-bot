# Polymarket 天气交易策略研究报告

> 基于 Twitter/X、Reddit、Medium、GitHub 公开信息整理

---

## 📊 一、成功交易者案例分析

### 1. meropi（最成功的天气交易者）
- **收益**: 约 $30,000+ 利润
- **策略**: 全自动化 bot，监控最新模型输出，实时对比 Polymarket 价格
- **特点**: 
  - 小额下注（$1-$3）
  - 有时在 $0.01 买入，赔率高达 500x（长尾事件命中）
  - 完全自动化，无需人工干预
- **启示**: 不需要大资金，关键在于**频率和覆盖率**

### 2. NOAA 前开发者
- **策略**: 利用对天气模型的深度理解，在 GFS/ECMWF 更新后第一时间抢跑
- **入场价格**: $0.01-$0.10 区间
- **更新周期**: 每6小时（跟随模型更新）
- **启示**: **模型更新时间窗口**是最核心的 Edge 来源

---

## 🧠 二、已验证的核心策略

### 策略 1: 模型更新时间差套利（Model Update Lag Arbitrage）
**最赚钱的策略，也是我们的主策略**

```
原理:
1. GFS/ECMWF 每6小时发布新预报（00:00, 06:00, 12:00, 18:00 UTC）
2. 新预报出来后，模型概率可能大幅变化
3. Polymarket 人类交易者不会立刻看到/反应
4. Bot 在新模型发布后秒级读取 → 计算新概率 → 发现偏差 → 下单

关键参数:
- 更新频率: 每6小时
- 响应时间: 模型发布后 < 30秒
- 目标: 新模型使某个温度区间概率从 20% 跳到 70%，但市场还是 30% → 买入
```

### 策略 2: 长尾事件猎杀（Long Tail Sniper）
**meropi 的策略，低频高赔率**

```
原理:
1. 大多数交易者聚焦最可能的温度区间（50%+ 概率）
2. 低概率区间（5%以下）的定价经常失准
3. 天气模型偶尔会显示某个"不可能"的区间其实有 8-10% 概率
4. 市场定价 $0.01（1%隐含概率），但实际概率 8-10% → 正EV

示例:
- 市场定价: "纽约最高温 75-80°F" YES = $0.02
- GFS 预报: 该区间实际概率 10%
- Expected Value = 10% × $1 - $0.02 = +$0.08/share → 正EV
- 即使大多数时候亏 $0.02，偶尔命中赚 $0.98

关键: 需要大量市场覆盖来保证足够的命中频率
```

### 策略 3: 多模型融合加权（Multi-Model Consensus）
**降低模型误差的核心方法**

```
原理:
1. 单一模型（如只用 GFS）有系统性偏差
2. 融合多个模型可以显著提高准确率
3. 不同模型对不同地区/季节的准确率不同

权重方案（WeatherBot 验证的有效权重）:
- ECMWF: 0.35（最准确，权重最高）
- GFS: 0.25（覆盖广）
- UKMO: 0.20（英国气象局）
- NWS: 0.20（美国国家气象局）
- 离群值自动降权至 0.5x

输出: 加权共识温度 + 动态标准差
```

### 策略 4: 时间衰减收割（Time Decay Harvesting）
**临近结算时的高确定性策略**

```
原理:
1. 天气预报的准确率随时间接近而提高
2. 结算前12-24小时，预报已经非常准确
3. 但市场可能还没完全反映最终结果
4. 此时 Edge 很小但确定性极高

操作:
- 结算前 12h: 确认天气预报确定
- 如果市场仍有 5%+ 的偏差
- 大仓位吃确定性利润
- 止损设紧（因为确定性高，容忍的亏损小）
```

### 策略 5: 城市覆盖扩展（City Coverage Expansion）
**提高机会数量的关键**

```
原理:
1. 每个城市每天有多个温度区间市场
2. 覆盖更多城市 = 更多交易机会
3. 不同城市天气模型准确率不同，可以选择性参与

优先级排序:
- P0: 纽约、伦敦、芝加哥（流动性最高）
- P1: 巴黎、洛杉矶、迈阿密（流动性好）
- P2: 首尔、东京、悉尼（时区覆盖）
- P3: 更多国际城市

每个城市的机会:
- 6个温度区间 × 每日 × 2次模型更新 × N个城市 = 大量交易信号
```

---

## 🔑 三、关键参数经验值

### Edge 阈值
- **最小 Edge**: 5%（低于此不值得交易，手续费/滑点会吃掉利润）
- **理想 Edge**: 15-30%
- **超大 Edge**: 30%+（模型大幅修正时出现，要快速执行）

### Kelly Sizing
- **保守**: Quarter-Kelly（f*/4），最大单笔 15% bankroll
- **标准**: Half-Kelly（f*/2），最大单笔 25% bankroll
- **起始阶段**: 用 Quarter-Kelly，验证策略稳定后再加码

### 退出策略（WeatherBot 验证的有效参数）
- **止盈**: 60% Edge 被捕获
- **追踪止损**: 从峰值回撤 40%
- **止损**: -15%
- **时间衰减退出**: 结算前 2 小时
- **Edge 收敛退出**: 剩余 Edge < 2%

### 模型置信度
- **6小时预报**: σ = 0.8°C（非常准）
- **1天预报**: σ = 1.5°C（较准）
- **3天预报**: σ = 2.5°C（一般）
- **7天预报**: σ = 4.0°C（谨慎）
- **10天+预报**: σ = 5.5°C（仅用于长尾策略）

---

## 🔧 四、可复用的开源项目（胶水编程轮子）

### 必看项目

| 项目 | 星 | 核心价值 | 可复用部分 |
|------|-----|---------|-----------|
| [suislanchez/polymarket-kalshi-weather-bot](https://github.com/suislanchez/polymarket-kalshi-weather-bot) | - | GFS 31成员集合预报 + Kelly | GFS ensemble 解析、信号校准 |
| [alteregoeth-ai/weatherbot](https://github.com/alteregoeth-ai/weatherbot) | - | 20城市覆盖，纯 Python | 多城市市场发现、EV 过滤 |
| [hcharper/polyBot-Weather](https://github.com/hcharper/polyBot-Weather) | - | 3策略系统，Mac Mini 友好 | 策略组合框架 |
| [aarora4/Awesome-Prediction-Market-Tools](https://github.com/aarora4/Awesome-Prediction-Market-Tools) | - | 预测市场工具大全 | 工具/库索引 |

### 关键依赖库

| 库 | 用途 |
|-----|------|
| `py_clob_client` | Polymarket 官方 CLOB Python 客户端 |
| `polymarket-apis` | 统一 Polymarket API 客户端（Gamma + CLOB + Data + WebSocket） |
| Open-Meteo API | 免费天气数据（GFS + ECMWF + ICON 集合预报） |
| `scipy.stats.norm` | 正态CDF概率计算 |
| `numpy` | 数值计算 |

---

## 📝 五、策略优先级排序

| 优先级 | 策略 | 难度 | 预期收益 | 开发阶段 |
|--------|------|------|---------|---------|
| **P0** | 模型更新时间差套利 | 中 | 高 | Phase 1 |
| **P0** | 多模型融合加权 | 低 | 中 | Phase 1 |
| **P1** | 时间衰减收割 | 低 | 中 | Phase 2 |
| **P1** | Kelly Sizing | 低 | 关键风控 | Phase 1 |
| **P2** | 长尾事件猎杀 | 中 | 高（不稳定） | Phase 2 |
| **P2** | 城市覆盖扩展 | 低 | 线性增长 | Phase 2 |
| **P3** | 跨平台套利（Kalshi） | 高 | 中 | Phase 3 |

---

## 📚 六、参考资料

### 文章
- [People Are Making Millions on Polymarket Betting on the Weather](https://ezzekielnjuguna.medium.com/people-are-making-millions-on-polymarket-betting-on-the-weather-and-i-will-teach-you-how-24c9977b277c) (Medium, 2026-04)
- [Found The Weather Trading Bots Quietly Making $24,000](https://blog.devgenius.io/found-the-weather-trading-bots-quietly-making-24-000-on-polymarket-and-built-one-myself-for-free-120bd34d6f09) (Dev Genius, 2026-02)
- [How Polymarket Weather Markets Actually Work](https://dev.to/cryptodeploy/how-polymarket-weather-markets-actually-work-50nb) (DEV, 2026-04)
- [Beyond Simple Arbitrage: 4 Polymarket Strategies](https://medium.com/illumination/beyond-simple-arbitrage-4-polymarket-strategies-bots-actually-profit-from-in-2026-ddacc92c5b4f) (Medium, 2026-02)

### 工具
- [WeatherBot.finance](https://www.weatherbot.finance/) — 付费天气交易 bot（参考架构设计）
- [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api) — 免费集合预报 API
- [Polymarket Docs](https://docs.polymarket.com/) — 官方 API 文档

---

*本报告作为项目策略输入，将持续更新。决策引擎的设计将基于此报告中的策略。*
