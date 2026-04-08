# Polymarket 天气交易 Bot — 常用命令手册

## 📊 查看盈亏

```bash
# 进入项目目录
cd ~/clawd/polymarket-weather-bot

# 显示交易汇总（最简单）
./venv/bin/python main.py --summary

# 查看所有交易记录
sqlite3 -header -column data/weather_bot.db "SELECT * FROM trades ORDER BY id DESC LIMIT 20"

# 查看已结算交易
sqlite3 -header -column data/weather_bot.db "SELECT * FROM trades WHERE status='settled' ORDER BY id DESC"

# 查看未结算交易
sqlite3 -header -column data/weather_bot.db "SELECT * FROM trades WHERE status='open'"

# 盈亏统计
sqlite3 -header -column data/weather_bot.db "
SELECT 
  COUNT(*) as 总交易数,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as 盈利次数,
  SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as 亏损次数,
  ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as 胜率,
  ROUND(COALESCE(SUM(pnl), 0), 2) as 总盈亏
FROM trades WHERE status='settled'
"
```

---

## 📝 查看信号

```bash
# 最近10条信号
sqlite3 -header -column data/weather_bot.db "SELECT * FROM signals ORDER BY id DESC LIMIT 10"

# 有效信号（未被过滤的）
sqlite3 -header -column data/weather_bot.db "SELECT * FROM signals WHERE filtered=0 ORDER BY id DESC"

# 按城市查看信号
sqlite3 -header -column data/weather_bot.db "SELECT * FROM signals WHERE city='New York' ORDER BY id DESC LIMIT 10"

# 统计信号
sqlite3 -header -column data/weather_bot.db "
SELECT 
  COUNT(*) as 总信号,
  SUM(CASE WHEN filtered=0 THEN 1 ELSE 0 END) as 有效,
  SUM(CASE WHEN filtered=1 THEN 1 ELSE 0 END) as 被过滤
FROM signals
"
```

---

## 🌡️ 查看天气数据

```bash
# 最近获取的天气预报
sqlite3 -header -column data/weather_bot.db "SELECT * FROM forecasts ORDER BY id DESC LIMIT 10"

# 某个城市的预报
sqlite3 -header -column data/weather_bot.db "SELECT * FROM forecasts WHERE city='New York' ORDER BY id DESC LIMIT 5"
```

---

## 📋 查看市场

```bash
# 所有已发现的市场
sqlite3 -header -column data/weather_bot.db "SELECT * FROM markets ORDER BY id DESC LIMIT 10"

# 按城市查看
sqlite3 -header -column data/weather_bot.db "SELECT * FROM markets WHERE city='Chicago' ORDER BY id DESC"

# 已结算市场
sqlite3 -header -column data/weather_bot.db "SELECT * FROM markets WHERE settled=1 ORDER BY id DESC"
```

---

## 💰 查看 Edge & 概率

```bash
# 所有计算过的 Edge
sqlite3 -header -column data/weather_bot.db "SELECT * FROM edges ORDER BY id DESC LIMIT 20"

# Edge > 5% 的机会
sqlite3 -header -column data/weather_bot.db "SELECT * FROM edges WHERE edge > 0.05 ORDER BY edge DESC"
```

---

## 📄 查看日志

```bash
# 实时查看日志（Ctrl+C 退出）
tail -f logs/weather_bot.log

# 最近50行
tail -50 logs/weather_bot.log

# 查看交易相关日志
grep "交易\|信号\|Edge\|下单" logs/weather_bot.log | tail -30

# 查看错误
grep "ERROR" logs/weather_bot.log | tail -20

# 查看某个城市的日志
grep "New York" logs/weather_bot.log | tail -20
```

---

## 🔄 运行 Bot

```bash
cd ~/clawd/polymarket-weather-bot

# 单次扫描（推荐先跑这个看效果）
./venv/bin/python main.py --once

# 启动 24/7 调度器（每6小时自动扫描）
nohup ./venv/bin/python main.py --scheduler >> logs/weather_bot.log 2>&1 &

# 查看是否在运行
ps aux | grep "main.py" | grep -v grep

# 停止
pkill -f "main.py"
```

---

## 🧪 测试

```bash
cd ~/clawd/polymarket-weather-bot

# 单元测试
./venv/bin/python tests/test_step2.py       # 天气数据获取（GFS/ECMWF/UKMO）
./venv/bin/python tests/test_step4.py       # Gamma API 市场发现
./venv/bin/python tests/test_step5.py       # CLOB 价格查询
./venv/bin/python tests/test_step678.py     # Edge + Kelly + 信号生成
./venv/bin/python tests/test_step910.py     # 风控 + 交易执行
./venv/bin/python tests/test_step11.py      # 主循环调度
./venv/bin/python tests/test_step12_backtest.py  # 回测

# 跑全部测试
for f in tests/test_step*.py; do echo "=== $f ===" && ./venv/bin/python "$f" 2>&1 | tail -5; done
```

---

## 🗄️ 数据库操作

```bash
# 交互式进入数据库
sqlite3 data/weather_bot.db

# 查看所有表
sqlite3 data/weather_bot.db ".tables"

# 查看表结构
sqlite3 data/weather_bot.db ".schema trades"
sqlite3 data/weather_bot.db ".schema signals"

# 清空所有数据（谨慎！）
sqlite3 data/weather_bot.db "DELETE FROM trades; DELETE FROM signals; DELETE FROM markets; DELETE FROM edges; DELETE FROM forecasts;"

# 数据库文件大小
ls -lh data/weather_bot.db
```

---

## 📐 查看配置

```bash
# 目标城市列表
cat src/config/cities.py

# 全局配置（Edge阈值、Kelly系数等）
cat src/config/settings.py

# 环境变量（钱包私钥等）
cat .env
```

---

## 字段说明

### trades 表
| 字段 | 含义 |
|---|---|
| id | 交易编号 |
| market_slug | 市场标识 |
| city | 城市名 |
| date | 预测日期 |
| side | 买的方向（YES/NO） |
| temperature_range | 温度区间 |
| shares | 股数 |
| price | 买入价（0-1） |
| cost_usd | 花了多少钱 |
| status | open=未结算 / settled=已结算 |
| pnl | 盈亏（正=赚，负=亏） |
| created_at | 下单时间 |

### signals 表
| 字段 | 含义 |
|---|---|
| city | 城市 |
| date | 预测日期 |
| temperature_range | 温度区间 |
| direction | YES/NO |
| our_prob | 我们的预测概率 |
| market_prob | 市场隐含概率 |
| edge | 优势大小 |
| confidence | 置信度 |
| filtered | 1=被过滤 / 0=有效 |

### edges 表
| 字段 | 含义 |
|---|---|
| city | 城市 |
| date | 日期 |
| range_label | 温度区间 |
| our_prob | 模型预测概率 |
| market_prob | 市场价格隐含概率 |
| edge | = our_prob - market_prob |
| kelly_fraction | Kelly 建议仓位比例 |

### forecasts 表
| 字段 | 含义 |
|---|---|
| city | 城市 |
| model | 天气模型（gfs/ecmwf/ukmo） |
| forecast_date | 预测日期 |
| temperature_f | 预测温度（°F） |
| fetched_at | 获取时间 |
