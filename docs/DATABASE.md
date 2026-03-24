# AI选股平台 - 数据库设计文档

> 版本: v1.0 | 设计日期: 2026-03-24 | 作者: AI量化架构师

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI 选股平台数据架构                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ 基础信息模块 │    │ 日线行情模块 │    │ AI分析模块  │         │
│  ├─────────────┤    ├─────────────┤    ├─────────────┤         │
│  │ stocks      │───▶│ daily_quotes│───▶│ ai_signals  │         │
│  │ concepts    │    └─────────────┘    └─────────────┘         │
│  │ stock_conc. │                                             │
│  └─────────────┘                                             │
│                                                                 │
│  数据流向: 东方财富API → 日线表 → AI策略引擎 → 信号表           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、表结构详解

### 2.1 基础信息模块

#### stocks - 股票基本信息表

| 字段 | 类型 | 说明 | 备注 |
|------|------|------|------|
| id | BIGSERIAL | 主键 | 自增 |
| stock_code | VARCHAR(10) | 股票代码 | 如 600519，唯一索引 |
| stock_name | VARCHAR(50) | 股票简称 | 如 贵州茅台 |
| exchange | VARCHAR(10) | 交易所 | SSE/SZSE/BSE |
| market | VARCHAR(20) | 市场板块 | 主板/创业板/科创板/北交所 |
| industry | VARCHAR(50) | 所属行业 | 申万行业分类 |
| listing_date | DATE | 上市日期 | |
| total_shares | NUMERIC(16,4) | 总股本 | 单位：万股 |
| float_shares | NUMERIC(16,4) | 流通股本 | 单位：万股 |
| total_market_cap | NUMERIC(16,2) | 总市值 | 单位：万元 |
| float_market_cap | NUMERIC(16,2) | 流通市值 | 单位：万元 |
| status | VARCHAR(10) | 状态 | active/delisted/st |
| is_st | BOOLEAN | 是否ST | 用于过滤 |
| is_new | BOOLEAN | 是否次新股 | 上市<60天 |

#### concept_sectors - 概念板块表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| sector_code | VARCHAR(20) | 板块代码，如 AI、NEWENERGY |
| sector_name | VARCHAR(50) | 板块名称，如 人工智能 |
| sector_type | VARCHAR(20) | 类型：concept/industry/region |
| parent_id | BIGINT | 父板块ID，支持层级 |
| stock_count | INT | 成分股数量 |

#### stock_concepts - 股票-概念关联表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| stock_id | BIGINT | 股票ID |
| sector_id | BIGINT | 概念ID |
| weight | NUMERIC(8,4) | 概念权重 0-1 |
| is_primary | BOOLEAN | 是否主营概念 |

**设计说明**: 多对多关联，一个股票可属于多个概念，一个概念包含多只股票。

---

### 2.2 日线行情模块

#### daily_quotes - 日线行情表

| 分类 | 字段 | 类型 | 说明 |
|------|------|------|------|
| **基础** | trade_date | DATE | 交易日期 |
| | open_price | NUMERIC(10,2) | 开盘价 |
| | high_price | NUMERIC(10,2) | 最高价 |
| | low_price | NUMERIC(10,2) | 最低价 |
| | close_price | NUMERIC(10,2) | 收盘价 |
| | prev_close | NUMERIC(10,2) | 昨收价 |
| | volume | BIGINT | 成交量(股) |
| | amount | NUMERIC(18,2) | 成交额(元) |
| **A股特有** | turnover_rate | NUMERIC(8,4) | 换手率(%) |
| | turnover_ratio | NUMERIC(8,4) | 量比 |
| | amplitude | NUMERIC(8,4) | 振幅(%) |
| | change_pct | NUMERIC(8,4) | 涨跌幅(%) |
| **涨停** | is_limit_up | BOOLEAN | 是否涨停 |
| | is_limit_down | BOOLEAN | 是否跌停 |
| | consecutive_limit_up_days | INT | 连板高度 |
| | limit_up_type | VARCHAR(20) | 涨停类型 |
| **均线** | ma5/ma10/ma20/ma60 | NUMERIC(10,2) | 移动均线 |

**涨停类型说明**:
- `一字板`: 开盘即涨停，全天未开板
- `T字板`: 涨停开盘，盘中开板后回封
- `实体板`: 盘中自然涨停
- `烂板`: 反复开板封板

---

### 2.3 AI分析模块

#### ai_signals - AI选股信号表

| 分类 | 字段 | 类型 | 说明 |
|------|------|------|------|
| **基础** | signal_date | DATE | 信号日期 |
| | stock_code | VARCHAR(10) | 股票代码 |
| | stock_name | VARCHAR(50) | 股票简称 |
| **策略** | strategy_name | VARCHAR(50) | 策略名称 |
| | strategy_type | VARCHAR(20) | preset/custom |
| | signal_type | VARCHAR(10) | buy/sell/hold |
| **评分** | confidence | NUMERIC(5,4) | AI置信度 0-1 |
| | score | INT | 综合评分 0-100 |
| | reason | TEXT | 选股理由 |
| | trigger_conditions | JSONB | 触发条件详情 |
| **操作** | expected_action | VARCHAR(20) | 预期操作 |
| | expected_action_price | NUMERIC(10,2) | 操作价格 |
| | stop_loss_price | NUMERIC(10,2) | 止损价 |
| | take_profit_price | NUMERIC(10,2) | 止盈价 |
| **反馈** | actual_result | VARCHAR(20) | hit/miss/pending |
| | actual_return_pct | NUMERIC(8,4) | 实际收益率 |

**预期操作类型**:
| 值 | 含义 |
|----|------|
| buy | 开盘买入 |
| buy_dip | 盘中低吸 |
| sell | 开盘卖出 |
| hold | 继续持有 |
| cut | 止损离场 |

---

## 三、索引设计

### 3.1 主要索引

```sql
-- 日线表核心索引
CREATE INDEX idx_daily_quotes_date ON daily_quotes(trade_date);
CREATE INDEX idx_daily_quotes_stock_date ON daily_quotes(stock_id, trade_date DESC);
CREATE INDEX idx_daily_quotes_limit_up ON daily_quotes(trade_date, is_limit_up) WHERE is_limit_up = TRUE;
CREATE INDEX idx_daily_quotes_consecutive_limit ON daily_quotes(consecutive_limit_up_days) WHERE consecutive_limit_up_days >= 2;

-- AI信号表核心索引
CREATE INDEX idx_ai_signals_date ON ai_signals(signal_date DESC);
CREATE INDEX idx_ai_signals_date_stock ON ai_signals(signal_date DESC, stock_id);
CREATE INDEX idx_ai_signals_score ON ai_signals(signal_date DESC, score DESC);
CREATE INDEX idx_ai_signals_pending ON ai_signals(actual_result) WHERE actual_result IS NULL;
```

### 3.2 索引设计原则

| 原则 | 说明 |
|------|------|
| **复合索引优先** | 日线查询通常是"某股票+某段时间" |
| **部分索引** | 涨停/连板数据量少，用WHERE过滤加速 |
| **降序索引** | 最新数据最常用，DESC排序 |
| **覆盖索引** | 高频查询避免回表 |

---

## 四、性能优化建议

### 4.1 表分区

日线数据量大，建议按年分区：

```sql
CREATE TABLE daily_quotes (
    ...
) PARTITION BY RANGE (trade_date);

CREATE TABLE daily_quotes_2025 PARTITION OF daily_quotes
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE daily_quotes_2026 PARTITION OF daily_quotes
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
```

### 4.2 连接池

推荐使用 PgBouncer，配置：
- `max_connections=100`
- `pool_mode=transaction`

### 4.3 查询优化

```sql
-- ✅ 好：利用复合索引
SELECT * FROM daily_quotes 
WHERE stock_id = 1 AND trade_date >= '2026-03-01'
ORDER BY trade_date DESC;

-- ❌ 差：全表扫描
SELECT * FROM daily_quotes 
WHERE close_price > 50 AND trade_date = '2026-03-24';
```

---

## 五、Docker部署

### 5.1 快速启动

```bash
cd /root/code/stock-screener
docker-compose up -d
```

### 5.2 连接信息

| 项目 | 值 |
|------|------|
| Host | localhost |
| Port | 5432 |
| Database | stock_screener |
| User | stock_user |
| Password | stock_pass_2024 |

### 5.3 数据备份

```bash
# 备份
docker exec stock-screener-db pg_dump -U stock_user stock_screener > backup.sql

# 恢复
docker exec -i stock-screener-db psql -U stock_user stock_screener < backup.sql
```

---

## 六、ER图

```
┌──────────────┐       ┌─────────────────┐       ┌──────────────────┐
│    stocks    │       │  concept_sectors │       │   daily_quotes   │
├──────────────┤       ├─────────────────┤       ├──────────────────┤
│ PK id        │       │ PK id           │       │ PK id            │
│    stock_code│◀─────│    sector_code  │       │ FK stock_id      │
│    stock_name│       │    sector_name  │       │    trade_date    │
│    exchange  │       │    sector_type  │       │    open/high/low │
│    market    │       │    parent_id    │       │    close/volume  │
│    industry  │       └────────┬────────┘       │    turnover_rate │
│    is_st     │                │                │    is_limit_up   │
└──────┬───────┘                │                │    consecutive_  │
       │                        │                │    limit_up_days │
       │    ┌───────────────────┴──┐             └────────┬─────────┘
       │    │   stock_concepts     │                      │
       │    ├──────────────────────┤                      │
       │    │ PK id                │                      │
       └────│ FK stock_id          │                      │
            │ FK sector_id ────────┘                      │
            │    weight                                   │
            │    is_primary                               │
            └─────────────────────────────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │   ai_signals     │
                              ├──────────────────┤
                              │ PK id            │
                              │    signal_date   │
                              │ FK stock_id      │
                              │    strategy_name │
                              │    confidence    │
                              │    score         │
                              │    reason        │
                              │    expected_     │
                              │    action        │
                              │    actual_result │
                              └──────────────────┘
```

---

## 七、变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-03-24 | v1.0 | 初始版本，完成基础设计 |
