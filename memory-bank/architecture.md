# Architecture — Polymarket 天气交易 Bot

> 每个 Module / 文件的职责说明，随开发进展更新

## 系统架构

```
polymarket-weather-bot/
├── memory-bank/                    # 记忆库（单一真相源）
│   ├── program-design-document.md  # 本文件 - 程序设计文档
│   ├── tech-stack.md               # 技术栈
│   ├── implementation-plan.md      # 实施计划
│   ├── progress.md                 # 进度记录
│   ├── architecture.md             # 本文件 - 架构说明
│   ├── architecture.canvas         # Obsidian Canvas 架构图
│   ├── vibe-coding-core.md         # 元方法论核心定义
│   ├── g-updated-rules.md          # 生成器G迭代规则
│   └── p-history.md                # 提示词P迭代历史
├── src/
│   ├── weather/                    # 模块1: 天气数据引擎
│   │   ├── __init__.py
│   │   ├── open_meteo_client.py    # Open-Meteo API 客户端
│   │   ├── probability.py          # 概率分布计算（正态CDF、贝叶斯融合）
│   │   └── historical.py           # 历史数据加载（NOAA NCEI）
│   ├── market/                     # 模块2: 市场监控引擎
│   │   ├── __init__.py
│   │   ├── gamma_client.py         # Gamma API 市场发现
│   │   ├── clob_client.py          # CLOB API 价格查询
│   │   └── ws_stream.py            # WebSocket 实时价格流
│   ├── decision/                   # 模块3: 决策引擎
│   │   ├── __init__.py
│   │   ├── edge_calculator.py      # Edge 计算（模型概率 vs 市场价格）
│   │   ├── kelly_sizer.py          # Kelly Criterion 仓位计算
│   │   └── signal_generator.py     # 交易信号生成
│   ├── execution/                  # 模块4: 交易执行引擎
│   │   ├── __init__.py
│   │   ├── trader.py               # 交易执行（下单、撤单、查询）
│   │   ├── position_manager.py     # 仓位管理
│   │   └── auth.py                 # API 认证 & 钱包管理
│   ├── risk/                       # 模块5: 风控模块
│   │   ├── __init__.py
│   │   └── risk_manager.py         # 风控规则检查
│   ├── config/                     # 配置
│   │   ├── __init__.py
│   │   ├── settings.py             # 全局配置
│   │   └── cities.py               # 目标城市配置
│   └── utils/                      # 工具
│       ├── __init__.py
│       ├── logger.py               # 日志
│       └── db.py                   # SQLite 存储
├── tests/                          # 测试
├── main.py                         # 主入口
├── requirements.txt
└── .env.example
```

## 文件职责说明

### 模块1: 天气数据引擎 (`src/weather/`)
| 文件 | 职责 |
|------|------|
| `open_meteo_client.py` | 调用 Open-Meteo API，获取 GFS/ECMWF/UKMO/NWS 多模型预报 |
| `probability.py` | 将多模型预报融合为概率分布，正态CDF计算，贝叶斯融合历史基准 |
| `historical.py` | 加载 NOAA NCEI 10年历史温度数据，提供基准概率 |

### 模块2: 市场监控引擎 (`src/market/`)
| 文件 | 职责 |
|------|------|
| `gamma_client.py` | 通过 Gamma API 发现和过滤天气市场 |
| `clob_client.py` | 通过 CLOB API 查询价格、订单簿深度 |
| `ws_stream.py` | WebSocket 订阅实时价格更新 |

### 模块3: 决策引擎 (`src/decision/`)
| 文件 | 职责 |
|------|------|
| `edge_calculator.py` | 计算模型概率与市场价格的 Edge |
| `kelly_sizer.py` | Kelly Criterion 仓位大小计算（Quarter-Kelly） |
| `signal_generator.py` | 综合所有因素生成最终交易信号 |

### 模块4: 交易执行引擎 (`src/execution/`)
| 文件 | 职责 |
|------|------|
| `trader.py` | 提交限价单、管理订单状态 |
| `position_manager.py` | 持仓查询、平仓、结算处理 |
| `auth.py` | 钱包管理、API密钥派生、USDC授权 |

### 模块5: 风控 (`src/risk/`)
| 文件 | 职责 |
|------|------|
| `risk_manager.py` | 所有风控规则的检查和执行 |

---

*本文档将随开发进展持续更新。*
