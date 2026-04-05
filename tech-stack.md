# Tech Stack — Polymarket 天气交易 Bot

> 胶水编程：优先复用成熟轮子，只写必要的胶水代码

---

## 语言 & 运行时

| 选择 | 理由 |
|------|------|
| **Python 3.11+** | py_clob_client 官方 SDK 原生支持；科学计算生态最强 |

---

## 核心依赖（胶水轮子）

### 🌤️ 天气数据层

| 库 | 版本 | 用途 | 来源 |
|----|------|------|------|
| `openmeteo-requests` | latest | Open-Meteo API Python 客户端，获取 GFS/ECMWF/UKMO 集合预报 | [GitHub](https://github.com/open-meteo/python-requests) |
| `requests` / `aiohttp` | - | HTTP 请求（历史数据等） | PyPI |
| `numpy` | ≥1.24 | 数值计算、数组操作 | PyPI |
| `scipy` | ≥1.11 | 正态 CDF 概率计算 (`scipy.stats.norm`)、贝叶斯 | PyPI |

**免费 API 端点（无需 API Key）：**
- `https://api.open-meteo.com/v1/forecast` — 多模型预报
- `https://api.open-meteo.com/v1/ensemble` — GFS 31成员集合预报
- `https://api.open-meteo.com/v1/gfs` — GFS 专用端点

### 📊 Polymarket 交易层

| 库 | 用途 | 来源 |
|----|------|------|
| `py_clob_client` | Polymarket CLOB 官方 Python SDK（下单、查价、认证） | [GitHub](https://github.com/Polymarket/py-clob-client) |
| `websockets` | WebSocket 实时价格推送 | PyPI |
| `eth-account` / `web3` | Polygon 钱包签名、USDC 授权 | PyPI |

**API 端点：**
- Gamma API: `https://gamma-api.polymarket.com` — 市场发现/搜索
- CLOB API: `https://clob.polymarket.com` — 交易操作
- WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market` — 实时价格

### 🧠 决策 & 数学层

| 库 | 用途 |
|----|------|
| `numpy` | 概率分布计算 |
| `scipy.stats` | 正态 CDF、贝叶斯更新 |
| 自写 `kelly.py` | Kelly Criterion 仓位计算（Quarter-Kelly） |

### ⏰ 调度层

| 库 | 用途 | 理由 |
|----|------|------|
| `APScheduler` | 定时任务（每6小时触发模型更新扫描） | 轻量，无需外部服务 |

### 💾 存储层

| 选择 | 用途 | 理由 |
|------|------|------|
| **SQLite** | 交易记录、市场快照、历史信号 | 轻量、零配置、单文件 |
| **JSON 文件** | 配置、memory-bank | 人类可读 |

### 📝 日志 & 工具

| 库 | 用途 |
|----|------|
| `logging` + `RotatingFileHandler` | 日志轮转 |
| `python-dotenv` | .env 环境变量管理 |
| `pydantic` | 配置/数据验证 |

---

## 可复用开源项目（胶水来源）

| 项目 | 可复用部分 | 复用方式 |
|------|-----------|---------|
| [suislanchez/polymarket-kalshi-weather-bot](https://github.com/suislanchez/polymarket-kalshi-weather-bot) | GFS ensemble 解析逻辑、Kelly sizing、信号校准 | 学习架构思路，不直接复制 |
| [alteregoeth-ai/weatherbot](https://github.com/alteregoeth-ai/weatherbot) | 20城市市场发现、EV 过滤逻辑 | 参考城市配置和市场扫描 |
| [hcharper/polyBot-Weather](https://github.com/hcharper/polyBot-Weather) | 3策略系统框架、零售环境优化 | 参考策略组合模式 |
| [Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) | 交易客户端 | **直接使用**，不重造 |
| [open-meteo/python-requests](https://github.com/open-meteo/python-requests) | 天气 API 客户端 | **直接使用**，不重造 |

---

## 不使用的技术（及理由）

| 技术 | 不用的理由 |
|------|-----------|
| Redis / PostgreSQL | 对本项目过重，SQLite 足够 |
| Docker | 增加复杂度，直接跑 Python 即可 |
| React Dashboard | Phase 3 再考虑，先聚焦核心交易逻辑 |
| JavaScript/TypeScript | py_clob_client 是 Python，不需要 JS |
| 付费天气 API | Open-Meteo 免费且够用 |

---

## 项目结构

```
polymarket-weather-bot/
├── memory-bank/                    # Vibe Coding 记忆库
├── src/
│   ├── weather/                    # 模块1: 天气数据
│   │   ├── __init__.py
│   │   ├── open_meteo_client.py    # Open-Meteo API 封装
│   │   ├── probability.py          # 概率分布 + 贝叶斯融合
│   │   └── historical.py           # 历史温度基准
│   ├── market/                     # 模块2: 市场监控
│   │   ├── __init__.py
│   │   ├── gamma_client.py         # Gamma API 市场发现
│   │   ├── clob_client.py          # CLOB 价格查询
│   │   └── ws_stream.py            # WebSocket 实时流
│   ├── decision/                   # 模块3: 决策引擎
│   │   ├── __init__.py
│   │   ├── edge_calculator.py      # Edge 计算
│   │   ├── kelly_sizer.py          # Kelly Criterion
│   │   └── signal_generator.py     # 信号生成
│   ├── execution/                  # 模块4: 交易执行
│   │   ├── __init__.py
│   │   ├── trader.py               # 下单执行
│   │   ├── position_manager.py     # 仓位管理
│   │   └── auth.py                 # API 认证
│   ├── risk/                       # 模块5: 风控
│   │   ├── __init__.py
│   │   └── risk_manager.py         # 风控规则
│   ├── config/                     # 配置
│   │   ├── __init__.py
│   │   ├── settings.py             # 全局设置
│   │   └── cities.py               # 城市列表
│   └── utils/                      # 工具
│       ├── __init__.py
│       ├── logger.py               # 日志
│       └── db.py                   # SQLite
├── tests/                          # 测试
├── data/                           # 运行时数据
├── logs/                           # 日志文件
├── main.py                         # 入口
├── requirements.txt
├── .env.example
└── program-design-document.md
```

---

## requirements.txt（初步）

```
# 天气数据
openmeteo-requests>=1.1.0
requests>=2.31.0

# Polymarket 交易
py_clob_client>=0.0.0  # 最新版
websockets>=12.0

# 数学 & 决策
numpy>=1.24.0
scipy>=1.11.0

# 链上交互
eth-account>=0.10.0
web3>=6.0.0

# 调度
APScheduler>=3.10.0

# 工具
python-dotenv>=1.0.0
pydantic>=2.0.0
```
