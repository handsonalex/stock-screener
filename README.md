# AI 智能选股平台

> 基于 A 股市场的实时策略选股系统，支持预设/自定义策略，Web 面板展示，PostgreSQL 数据持久化。

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AI 智能选股平台架构                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐           │
│    │   新浪财经   │      │  东方财富    │      │  其他数据源  │           │
│    │    API      │      │    API      │      │    API      │           │
│    └──────┬──────┘      └──────┬──────┘      └──────┬──────┘           │
│           │                    │                    │                   │
│           └────────────────────┼────────────────────┘                   │
│                                ▼                                        │
│                    ┌───────────────────────┐                           │
│                    │   data/fetcher.py     │                           │
│                    │   数据获取层          │                           │
│                    └───────────┬───────────┘                           │
│                                │                                        │
│                                ▼                                        │
│                    ┌───────────────────────┐                           │
│                    │  strategies/engine.py │                           │
│                    │   策略引擎            │                           │
│                    │  ┌─────────────────┐  │                           │
│                    │  │ 预设策略 (5个)  │  │                           │
│                    │  │ - 均线多头排列  │  │                           │
│                    │  │ - 放量突破      │  │                           │
│                    │  │ - 缩量回踩      │  │                           │
│                    │  │ - 涨停板战法    │  │                           │
│                    │  │ - 涨幅榜情绪    │  │                           │
│                    │  └─────────────────┘  │                           │
│                    │  ┌─────────────────┐  │                           │
│                    │  │ 自定义策略      │  │                           │
│                    │  │ (JSON配置)     │  │                           │
│                    │  └─────────────────┘  │                           │
│                    └───────────┬───────────┘                           │
│                                │                                        │
│              ┌─────────────────┼─────────────────┐                     │
│              ▼                 ▼                  ▼                     │
│   ┌─────────────────┐  ┌─────────────┐  ┌─────────────────┐           │
│   │   PostgreSQL    │  │  Web 面板   │  │   飞书推送      │           │
│   │   (数据持久化)  │  │  (Vue3)     │  │   (Webhook)     │           │
│   └─────────────────┘  └─────────────┘  └─────────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
stock-screener/
├── db/                         # 数据库相关
│   └── init.sql                # PostgreSQL DDL 建表语句
├── data/                       # 数据获取层
│   └── fetcher.py              # 外部 API 封装（新浪财经）
├── strategies/                 # 策略引擎
│   ├── __init__.py
│   └── engine.py               # 预设策略 + 自定义策略加载
├── notifier/                   # 消息推送（预留）
├── templates/                  # Web 前端
│   └── index.html              # Vue3 单页应用
├── static/                     # 静态资源
├── docs/                       # 文档
│   └── DATABASE.md             # 数据库设计文档
├── config.json                 # 策略配置文件
├── docker-compose.yml          # PostgreSQL Docker 部署
├── screener.py                 # 主程序（扫描调度）
├── web_server.py               # Flask Web 服务器
├── start.sh                    # 启动脚本
└── README.md                   # 本文件
```

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Docker (用于 PostgreSQL)
- Linux / macOS / WSL2

### 2. 部署数据库

```bash
# 启动 PostgreSQL
cd stock-screener
docker compose up -d

# 验证数据库
docker exec stock-screener-db psql -U stock_user -d stock_screener -c "\dt"
```

**数据库连接信息：**

| 项目 | 值 |
|------|-----|
| Host | localhost |
| Port | 5432 |
| Database | stock_screener |
| User | stock_user |
| Password | stock_pass_2024 |

### 3. 安装依赖 & 启动

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install flask requests psycopg2-binary

# 启动服务
python3 web_server.py
```

### 4. 访问 Web 面板

浏览器打开：`http://localhost:5000`

---

## ⚙️ 配置说明

### config.json 配置文件

```json
{
    "scan_interval": 300,           // 扫描间隔（秒）
    "strategies": {                 // 预设策略开关
        "ma_bullish": {"enabled": true},
        "volume_break": {"enabled": true},
        "pullback": {"enabled": true},
        "limit_up": {"enabled": true},
        "momentum": {"enabled": true}
    },
    "custom_strategies": [          // 自定义策略
        {
            "name": "我的强势股策略",
            "conditions": {
                "change_pct_min": 3,     // 涨幅下限
                "change_pct_max": 8,     // 涨幅上限
                "volume_ratio_min": 1.5, // 量比下限
                "turnover_min": 3,       // 换手率下限
                "above_ma20": true       // 在20日均线上方
            }
        }
    ],
    "filters": {                    // 股票过滤
        "min_price": 3,             // 最低价格
        "max_price": 100,           // 最高价格
        "exclude_st": true,         // 排除ST
        "exclude_new": true         // 排除次新股
    },
    "notify": {
        "min_score": 60             // 信号推送阈值（0-100）
    }
}
```

---

## 📊 预设策略说明

| 策略 | 逻辑 | 适用场景 |
|------|------|---------|
| **均线多头排列** | 5/10/20/60日均线多头排列，股价站上5日线 | 趋势跟踪 |
| **放量突破** | 量比>2，涨幅>3%，成交量创近5日新高 | 突破买入 |
| **缩量回踩** | 缩量回踩20日均线，量能萎缩至50%以下 | 回调买入 |
| **涨停板战法** | 今日涨停，近5日涨幅<30%，非ST | 连板接力 |
| **涨幅榜情绪** | 涨幅>5%，量比>1.5，换手率>5% | 情绪追涨 |

---

## 🗄️ 数据库设计

### 数据模型

```
┌──────────────┐       ┌─────────────────┐       ┌──────────────────┐
│    stocks    │       │ concept_sectors │       │   daily_quotes   │
│   股票表     │       │   概念板块表     │       │    日线行情表     │
├──────────────┤       ├─────────────────┤       ├──────────────────┤
│ stock_code   │       │ sector_code     │       │ trade_date       │
│ stock_name   │◀─────│ sector_name     │       │ open/high/low    │
│ exchange     │       │ sector_type     │       │ close/volume     │
│ market       │       └─────────────────┘       │ turnover_rate    │
│ is_st        │                │                │ is_limit_up      │
└──────┬───────┘                │                │ consecutive_days │
       │                        │                └────────┬─────────┘
       │    ┌───────────────────┘                         │
       │    │  stock_concepts                            │
       │    │  关联表                                     │
       │    └────────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐
│   ai_signals     │
│  AI选股信号表    │
├──────────────────┤
│ signal_date      │
│ strategy_name    │
│ confidence       │
│ score            │
│ expected_action  │
│ actual_result    │
└──────────────────┘
```

### 核心表说明

| 表名 | 说明 | 记录数 |
|------|------|--------|
| `stocks` | 股票基本信息 | ~5000 |
| `concept_sectors` | 概念/行业板块 | ~300 |
| `stock_concepts` | 股票-概念关联 | ~50000 |
| `daily_quotes` | 日线行情 | ~5000×交易日 |
| `ai_signals` | AI选股信号 | 每日扫描结果 |

---

## 🌐 API 接口

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 面板首页 |
| `/api/status` | GET | 扫描状态 |
| `/api/signals` | GET | 选股信号列表 |
| `/api/strategies` | GET | 策略列表 |
| `/api/scan` | POST | 手动触发扫描 |
| `/api/config` | GET/POST | 配置读写 |
| `/api/market` | GET | 大盘概况 |

---

## 📝 使用说明

### Web 面板操作

1. **查看信号** — 默认显示最新选股结果
2. **筛选过滤** — 按策略、代码、评分筛选
3. **手动扫描** — 点击"扫描"按钮立即执行
4. **策略管理** — 切换到"策略管理"Tab开关策略
5. **参数设置** — 切换到"参数设置"Tab调整配置

### 命令行操作

```bash
# 单次扫描（不启动Web）
python3 screener.py --once

# 后台持续扫描
python3 screener.py

# 查看日志
tail -f screener.log
```

---

## 🔧 二次开发

### 添加新策略

在 `strategies/engine.py` 中添加：

```python
class MyStrategy(Strategy):
    name = "我的策略"
    
    def check(self, stock_code: str, klines: list) -> Optional[Signal]:
        # 实现你的逻辑
        if 符合条件:
            return Signal(
                code=stock_code,
                strategy=self.name,
                score=80,
                reason="触发原因"
            )
        return None
```

### 连接飞书推送

在 `config.json` 添加 Webhook：

```json
{
    "notify": {
        "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "min_score": 60
    }
}
```

---

## 📋 开发计划

- [ ] 飞书机器人推送
- [ ] 选股历史回看
- [ ] 策略回测功能
- [ ] 多数据源冗余
- [ ] 实时行情 WebSocket
- [ ] 移动端适配

---

## 📄 许可证

MIT License

---

## 📞 联系方式

- GitHub: [@handsonalex](https://github.com/handsonalex)
- 项目地址: https://github.com/handsonalex/stock-screener
