# Implementation Plan — Polymarket 天气交易 Bot

> 分步实施计划。每步小而具体，包含验证测试。严禁包含代码。

---

## Phase 1: 基础设施（数据获取 + 市场连接）

### Step 1: 项目骨架 + 配置系统

**目标**: 搭建项目结构，配置系统可运行

**指令**:
- 创建 `src/` 下的所有模块目录和 `__init__.py`
- 创建 `src/config/settings.py`，从 `.env` 读取 Polymarket 私钥、API 端点等配置
- 创建 `src/config/cities.py`，定义目标城市列表（纽约、伦敦、芝加哥、巴黎、洛杉矶、迈阿密），包含经纬度、时区
- 创建 `src/utils/logger.py`，配置日志输出到 `logs/` 目录，按天轮转
- 创建 `src/utils/db.py`，初始化 SQLite 数据库，建表：`trades`、`market_snapshots`、`signals`、`forecasts`
- 创建 `.env.example` 模板
- 创建 `requirements.txt`
- 创建 `main.py` 骨架（先只初始化配置和日志）

**验证**:
- [ ] `pip install -r requirements.txt` 成功
- [ ] `python main.py` 输出初始化日志
- [ ] SQLite 数据库文件自动创建
- [ ] 所有 `__init__.py` 可正常 import

---

### Step 2: 天气数据引擎 — Open-Meteo 客户端

**目标**: 能获取多模型天气预报数据

**指令**:
- 阅读 `openmeteo-requests` 的 GitHub README 和 Ensemble API 文档
- 创建 `src/weather/open_meteo_client.py`
  - 实现 `get_forecast(city, models, forecast_days)` 方法
  - 支持 GFS、ECMWF、UKMO、NWS 四个模型
  - 支持集合预报（ensemble）获取 31 个 GFS 成员
  - 返回标准化的数据结构：城市、模型名、预报时间、温度列表
- 创建 `src/weather/historical.py`
  - 实现获取历史温度基准概率的方法
  - 使用 Open-Meteo 的历史 API 获取过去 10 年同日温度
  - 缓存到 SQLite 避免重复请求

**验证**:
- [ ] 能获取纽约未来 7 天的 GFS 预报
- [ ] 能获取纽约的 ECMWF 预报
- [ ] 能获取 GFS 31 成员集合预报
- [ ] 返回数据结构一致、字段完整
- [ ] 历史数据可缓存

---

### Step 3: 天气数据引擎 — 概率分布计算

**目标**: 将多模型预报融合为概率分布

**指令**:
- 创建 `src/weather/probability.py`
- 实现多模型加权融合：
  - 权重：ECMWF=0.35, GFS=0.25, UKMO=0.20, NWS=0.20
  - 离群值检测：某个模型偏离共识 > 2σ 时降权至 0.5x
  - 输出：加权共识温度 + 动态标准差
- 实现动态标准差计算：
  - 6h 预报: σ=0.8°C
  - 1d: σ=1.5°C
  - 3d: σ=2.5°C
  - 7d: σ=4.0°C
  - 10d+: σ=5.5°C
- 实现正态 CDF 概率计算：给定温度区间 [T1, T2]，计算 P(T1 ≤ T ≤ T2)
- 实现贝叶斯融合：将模型概率与历史基准概率融合
- 实现集合预报概率：从 31 个 GFS 成员中计算落入各温度区间的比例

**验证**:
- [ ] 给定纽约 4月6日预报 58°F，σ=1.5°F，计算 [55,60] 区间概率 ≈ 60%+
- [ ] 多模型融合后概率与单一模型不同
- [ ] 离群值降权正常工作
- [ ] 贝叶斯融合后概率更合理
- [ ] 集合预报概率与正态 CDF 概率交叉验证

---

### Step 4: 市场监控引擎 — Polymarket Gamma API

**目标**: 能自动发现天气市场

**指令**:
- 阅读 Polymarket Gamma API 文档
- 创建 `src/market/gamma_client.py`
- 实现市场发现：
  - 搜索所有 weather 分类的 events
  - 解析 event 结构：Event → Markets（温度区间）→ Outcomes（YES/NO）
  - 提取关键信息：城市名、日期、温度区间、token_id
- 实现市场过滤：
  - 只保留活跃市场（未结算、有流动性）
  - 按城市分组，方便后续对比
- 缓存市场列表到 SQLite

**验证**:
- [ ] 能搜索到当前所有天气市场
- [ ] 能正确解析 "New York City High Temperature - April 6, 2026" 格式
- [ ] 能提取各温度区间的 token_id
- [ ] 能按城市分组

---

### Step 5: 市场监控引擎 — CLOB 价格查询

**目标**: 能获取实时市场价格和订单簿

**指令**:
- 创建 `src/market/clob_client.py`
- 使用 `py_clob_client` 实现以下功能：
  - 查询指定 token 的当前 bid/ask 价格
  - 查询订单簿深度（前 5 档）
  - 查询最近成交记录
- 将市场价格转换为隐含概率：
  - YES 价格 = P_market（市场认为会发生的概率）
  - NO 价格 = 1 - P_market
- 实现市场快照：保存某时刻所有温度区间的价格到 SQLite

**验证**:
- [ ] 能获取纽约天气市场的 YES/NO 价格
- [ ] 价格与 Polymarket 网页一致
- [ ] 能获取订单簿深度
- [ ] 隐含概率计算正确（YES + NO ≈ $1.00）

---

## Phase 2: 决策 + 执行

### Step 6: 决策引擎 — Edge 计算

**目标**: 比较模型概率与市场价格，发现定价偏差

**指令**:
- 创建 `src/decision/edge_calculator.py`
- 实现核心比较逻辑：
  - 对每个温度区间市场，获取 P_model（模块3）和 P_market（模块5）
  - Edge = P_model - P_market
  - 正 Edge → 买入 YES（模型认为更可能发生）
  - 负 Edge → 买入 NO（模型认为更不可能发生）
- 实现 Edge 过滤：
  - 最小 |Edge| > 5%（低于此不值得交易）
  - 流动性检查：bid/ask spread < 5 cents
  - 最低交易量过滤
- 输出标准化的 Edge 列表，按 Edge 大小排序

**验证**:
- [ ] 对已知数据计算 Edge 正确
- [ ] 能过滤掉 Edge 太小的市场
- [ ] 能区分正/负 Edge 方向

---

### Step 7: 决策引擎 — Kelly Sizing

**目标**: 计算最优仓位大小

**指令**:
- 创建 `src/decision/kelly_sizer.py`
- 实现 Kelly Criterion：
  - f* = (p * b - q) / b
  - p = 模型概率, q = 1-p, b = 赔率（YES价格对应赔率）
- 实现 Quarter-Kelly 缩放（f*/4）
- 实现仓位上限：最大 15% bankroll
- 实现仓位下限：最小 $1
- bankroll 从数据库读取（初始资金 + 已实现盈亏）
- 输出：交易数量（股数）和预估成本

**验证**:
- [ ] Kelly 公式计算正确（手动验证 2-3 个案例）
- [ ] Quarter-Kelly 缩放正确
- [ ] 不超过 bankroll 15% 上限
- [ ] 最小 $1 下限

---

### Step 8: 决策引擎 — 信号生成器

**目标**: 综合所有因素生成最终交易信号

**指令**:
- 创建 `src/decision/signal_generator.py`
- 整合 Edge 计算和 Kelly Sizing
- 生成交易信号列表，每个信号包含：
  - market_id / token_id
  - 方向：BUY_YES / BUY_NO
  - 数量（股数）
  - 限价（当前 bid/ask 价格）
  - Edge 值
  - Kelly 比例
  - 模型置信度
- 实现信号排序：按 Edge × Kelly × 置信度 综合评分
- 将信号保存到 SQLite

**验证**:
- [ ] 信号包含所有必要字段
- [ ] 信号排序合理（高 Edge + 高置信度排前面）
- [ ] 信号保存到数据库

---

### Step 9: 风控模块

**目标**: 所有交易前必须通过风控检查

**指令**:
- 创建 `src/risk/risk_manager.py`
- 实现风控规则（每个规则一个方法，返回 True/False）：
  - `check_position_limit(signal)` → 单市场仓位 ≤ 15% bankroll
  - `check_total_exposure(signal)` → 总敞口 ≤ 50% bankroll
  - `check_daily_loss()` → 今日亏损 ≤ 10% bankroll
  - `check_min_liquidity(signal)` → 订单簿深度足够
  - `check_settlement_time(signal)` → 距结算 > 2 小时
- 实现综合检查：所有规则通过才允许交易
- 实现仓位追踪：从数据库读取当前所有持仓

**验证**:
- [ ] 超过仓位限制时拒绝交易
- [ ] 超过总敞口时拒绝交易
- [ ] 日亏损超限时暂停所有交易
- [ ] 流动性不足时拒绝
- [ ] 结算前 2h 不开新仓

---

### Step 10: 交易执行引擎

**目标**: 通过 Polymarket CLOB 自动下单

**指令**:
- 创建 `src/execution/auth.py`
  - 实现私钥管理（从 .env 读取）
  - 实现 API 密钥派生（py_clob_client 的 create_or_derive_api_creds）
  - 实现 USDC 授权检查
- 创建 `src/execution/trader.py`
  - 实现限价单下单（GTC）
  - 实现撤单
  - 实现订单状态查询
  - 实现批量下单（多个信号同时执行）
- 创建 `src/execution/position_manager.py`
  - 实现持仓查询
  - 实现平仓逻辑（止损/止盈/到期前平仓）
  - 实现结算结果记录
- 所有交易操作前调用风控检查

**验证**:
- [ ] API 认证成功
- [ ] 能查询当前余额
- [ ] 能提交限价单（先在极小金额测试）
- [ ] 能查询订单状态
- [ ] 能撤销订单
- [ ] 风控拦截正常工作

---

## Phase 3: 自动化运行

### Step 11: 主循环 + 调度器

**目标**: Bot 24/7 自动运行

**指令**:
- 在 `main.py` 中使用 APScheduler 设置定时任务：
  - 每 6 小时（00:00, 06:00, 12:00, 18:00 UTC）触发主交易循环
  - 每 1 小时触发仓位检查（止损/止盈/结算前平仓）
- 主交易循环流程：
  1. 获取最新天气模型数据
  2. 计算多模型融合概率
  3. 获取 Polymarket 天气市场价格
  4. 计算 Edge
  5. Kelly Sizing
  6. 生成信号
  7. 风控检查
  8. 执行交易
  9. 更新 memory-bank 和数据库
- 添加异常处理和自动恢复

**验证**:
- [ ] 调度器按计划触发
- [ ] 主循环完整执行无报错
- [ ] 异常时不会崩溃，能自动恢复
- [ ] 日志完整记录每个步骤

---

### Step 12: 模拟模式（Paper Trading）

**目标**: 不花真钱，先验证策略有效性

**指令**:
- 实现模拟交易模式：
  - 不实际下单，但记录"本应该下的单"
  - 跟踪模拟持仓和盈亏
  - 每日生成模拟交易报告
- 模式切换：通过配置文件控制 SIMULATION / LIVE
- 运行模拟模式 7 天，统计：
  - 信号数量
  - 命中率
  - 模拟盈亏
  - 最大回撤

**验证**:
- [ ] 模拟模式不下真单
- [ ] 模拟盈亏计算正确
- [ ] 每日报告自动生成
- [ ] 7 天后策略整体正收益

---

### Step 13: WebSocket 实时价格流

**目标**: 实时监控仓位和价格变化

**指令**:
- 创建 `src/market/ws_stream.py`
- 连接 `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- 订阅所有持仓相关的 token
- 实现实时止盈/止损：
  - 价格达到止盈目标（60% Edge 捕获）
  - 价格触发止损（-15%）
  - 价格回撤触发追踪止损（40% pullback）
  - Edge 收敛至 < 2% 时平仓

**验证**:
- [ ] WebSocket 连接稳定
- [ ] 价格推送实时更新
- [ ] 止盈/止损正确触发
- [ ] 断连自动重连

---

### Step 14: 城市扩展 + 策略迭代

**目标**: 扩大覆盖面，持续优化

**指令**:
- 添加更多城市到 cities.py（首尔、东京、悉尼等）
- 实现长尾事件猎杀策略：
  - 检测市场价格 ≤ $0.05 但模型概率 ≥ 5% 的机会
  - 小额分散下注
- 实现信号校准：根据历史交易结果，调整模型权重和参数
- 更新 memory-bank 中的策略文档

**验证**:
- [ ] 新城市市场能正常扫描
- [ ] 长尾策略能发现机会
- [ ] 校准后策略命中率提升

---

## 里程碑检查点

| 阶段 | 步骤 | 交付物 | 检查点 |
|------|------|--------|--------|
| Phase 1 | Step 1-5 | 数据基础设施 | 能获取天气数据 + 市场价格 |
| Phase 2 | Step 6-10 | 决策 + 执行 | 能发现信号 + 模拟下单 |
| Phase 3 | Step 11-14 | 自动化运行 | 7天模拟正收益 → 实盘 |
