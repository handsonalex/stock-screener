-- ============================================================
-- AI选股平台 - PostgreSQL 数据库设计
-- 版本: v1.0
-- 设计师: AI量化架构师
-- 说明: 适用于A股短线强势股策略
-- ============================================================

-- ============================================================
-- 0. 扩展
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. 基础信息模块
-- ============================================================

-- ------------------------------------------------------------
-- 1.1 股票基本信息表
-- ------------------------------------------------------------
CREATE TABLE stocks (
    id              BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(10)     NOT NULL,                           -- 股票代码，如 600519
    stock_name      VARCHAR(50)     NOT NULL,                           -- 股票简称
    full_name       VARCHAR(100),                                       -- 股票全称
    exchange        VARCHAR(10)     NOT NULL,                           -- 交易所：SSE上交所/SZSE深交所/BSE北交所
    market          VARCHAR(20)     NOT NULL,                           -- 市场：主板/创业板/科创板/北交所
    industry        VARCHAR(50),                                        -- 所属行业
    listing_date    DATE,                                               -- 上市日期
    total_shares    NUMERIC(16,4),                                      -- 总股本（万股）
    float_shares    NUMERIC(16,4),                                      -- 流通股本（万股）
    total_market_cap NUMERIC(16,2),                                     -- 总市值（万元）
    float_market_cap NUMERIC(16,2),                                     -- 流通市值（万元）
    status          VARCHAR(10)     NOT NULL DEFAULT 'active',          -- 状态：active停牌/delisted退市/st暂停上市
    is_st           BOOLEAN         NOT NULL DEFAULT FALSE,             -- 是否ST股
    is_new          BOOLEAN         NOT NULL DEFAULT FALSE,             -- 是否次新股（上市不足60天）
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_stocks_code UNIQUE (stock_code)
);

COMMENT ON TABLE stocks IS '股票基本信息表 - 存储A股所有股票基础资料';
COMMENT ON COLUMN stocks.stock_code IS '股票代码，6位数字';
COMMENT ON COLUMN stocks.stock_name IS '股票简称，如 贵州茅台';
COMMENT ON COLUMN stocks.exchange IS '交易所：SSE上交所/SZSE深交所/BSE北交所';
COMMENT ON COLUMN stocks.market IS '市场板块：主板/创业板/科创板/北交所';
COMMENT ON COLUMN stocks.industry IS '所属申万行业分类';
COMMENT ON COLUMN stocks.total_shares IS '总股本，单位万股';
COMMENT ON COLUMN stocks.float_shares IS '流通股本，单位万股';
COMMENT ON COLUMN stocks.total_market_cap IS '总市值，单位万元';
COMMENT ON COLUMN stocks.float_market_cap IS '流通市值，单位万元';
COMMENT ON COLUMN stocks.status IS '股票状态：active正常/delisted退市/st暂停上市';
COMMENT ON COLUMN stocks.is_st IS '是否ST/*ST股票，用于过滤';
COMMENT ON COLUMN stocks.is_new IS '是否次新股，上市不足60天';

CREATE INDEX idx_stocks_exchange ON stocks(exchange);
CREATE INDEX idx_stocks_market ON stocks(market);
CREATE INDEX idx_stocks_industry ON stocks(industry);
CREATE INDEX idx_stocks_status ON stocks(status);
CREATE INDEX idx_stocks_is_st ON stocks(is_st);

-- ------------------------------------------------------------
-- 1.2 概念板块表
-- ------------------------------------------------------------
CREATE TABLE concept_sectors (
    id              BIGSERIAL       PRIMARY KEY,
    sector_code     VARCHAR(20)     NOT NULL,                           -- 板块代码
    sector_name     VARCHAR(50)     NOT NULL,                           -- 板块名称
    sector_type     VARCHAR(20)     NOT NULL,                           -- 板块类型：concept概念/industry行业/region地域
    parent_id       BIGINT          REFERENCES concept_sectors(id),     -- 父板块ID（支持层级）
    description     TEXT,                                               -- 板块描述
    stock_count     INT             DEFAULT 0,                          -- 成分股数量
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_concept_code UNIQUE (sector_code)
);

COMMENT ON TABLE concept_sectors IS '概念板块表 - 存储概念/行业/地域板块信息';
COMMENT ON COLUMN concept_sectors.sector_code IS '板块代码，如 AI、新能源';
COMMENT ON COLUMN concept_sectors.sector_name IS '板块名称，如 人工智能、新能源汽车';
COMMENT ON COLUMN concept_sectors.sector_type IS '板块类型：concept概念/industry行业/region地域';
COMMENT ON COLUMN concept_sectors.parent_id IS '父板块ID，支持板块层级结构';
COMMENT ON COLUMN concept_sectors.stock_count IS '当前成分股数量';

CREATE INDEX idx_concept_type ON concept_sectors(sector_type);

-- ------------------------------------------------------------
-- 1.3 股票-概念关联表（多对多）
-- ------------------------------------------------------------
CREATE TABLE stock_concepts (
    id              BIGSERIAL       PRIMARY KEY,
    stock_id        BIGINT          NOT NULL REFERENCES stocks(id),
    sector_id       BIGINT          NOT NULL REFERENCES concept_sectors(id),
    weight          NUMERIC(8,4)    DEFAULT 1.0000,                     -- 概念权重/相关度
    is_primary      BOOLEAN         DEFAULT FALSE,                     -- 是否主营概念
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_stock_concept UNIQUE (stock_id, sector_id)
);

COMMENT ON TABLE stock_concepts IS '股票-概念关联表 - 记录股票所属的多个概念板块';
COMMENT ON COLUMN stock_concepts.stock_id IS '股票ID';
COMMENT ON COLUMN stock_concepts.sector_id IS '概念板块ID';
COMMENT ON COLUMN stock_concepts.weight IS '概念权重，0-1，表示股票与概念的相关度';
COMMENT ON COLUMN stock_concepts.is_primary IS '是否主营概念';

CREATE INDEX idx_stock_concepts_stock ON stock_concepts(stock_id);
CREATE INDEX idx_stock_concepts_sector ON stock_concepts(sector_id);


-- ============================================================
-- 2. 日线行情模块
-- ============================================================

-- ------------------------------------------------------------
-- 2.1 日线行情表
-- ------------------------------------------------------------
CREATE TABLE daily_quotes (
    id                      BIGSERIAL       PRIMARY KEY,
    stock_id                BIGINT          NOT NULL REFERENCES stocks(id),
    trade_date              DATE            NOT NULL,                           -- 交易日期
    
    -- OHLCV 基础数据
    open_price              NUMERIC(10,2)   NOT NULL,                          -- 开盘价
    high_price              NUMERIC(10,2)   NOT NULL,                          -- 最高价
    low_price               NUMERIC(10,2)   NOT NULL,                          -- 最低价
    close_price             NUMERIC(10,2)   NOT NULL,                          -- 收盘价
    prev_close              NUMERIC(10,2),                                     -- 昨收价
    volume                  BIGINT          NOT NULL,                          -- 成交量（股）
    amount                  NUMERIC(18,2),                                     -- 成交额（元）
    
    -- A股特有字段
    turnover_rate           NUMERIC(8,4),                                      -- 换手率（%）
    turnover_ratio          NUMERIC(8,4),                                      -- 量比
    amplitude               NUMERIC(8,4),                                      -- 振幅（%）
    change_amount           NUMERIC(10,2),                                     -- 涨跌额
    change_pct              NUMERIC(8,4),                                      -- 涨跌幅（%）
    
    -- 涨停相关
    is_limit_up             BOOLEAN         NOT NULL DEFAULT FALSE,            -- 是否涨停
    is_limit_down           BOOLEAN         NOT NULL DEFAULT FALSE,            -- 是否跌停
    limit_up_price          NUMERIC(10,2),                                     -- 涨停价
    limit_down_price        NUMERIC(10,2),                                     -- 跌停价
    consecutive_limit_up_days INT           NOT NULL DEFAULT 0,                -- 连板高度（连续涨停天数）
    limit_up_type           VARCHAR(20),                                       -- 涨停类型：一字板/T字板/实体板/烂板
    
    -- 成交量分析
    volume_ratio            NUMERIC(8,4),                                      -- 量比（当日成交量/过去5日均量）
    volume_change_pct       NUMERIC(8,4),                                      -- 成交量变化率（%）
    
    -- 均线数据
    ma5                     NUMERIC(10,2),                                     -- 5日均线
    ma10                    NUMERIC(10,2),                                     -- 10日均线
    ma20                    NUMERIC(10,2),                                     -- 20日均线
    ma60                    NUMERIC(10,2),                                     -- 60日均线
    
    -- 元数据
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_daily_quote UNIQUE (stock_id, trade_date)
);

COMMENT ON TABLE daily_quotes IS '日线行情表 - 存储A股每日OHLCV及衍生数据';
COMMENT ON COLUMN daily_quotes.stock_id IS '股票ID，关联stocks表';
COMMENT ON COLUMN daily_quotes.trade_date IS '交易日期';
COMMENT ON COLUMN daily_quotes.open_price IS '开盘价（元）';
COMMENT ON COLUMN daily_quotes.high_price IS '最高价（元）';
COMMENT ON COLUMN daily_quotes.low_price IS '最低价（元）';
COMMENT ON COLUMN daily_quotes.close_price IS '收盘价（元）';
COMMENT ON COLUMN daily_quotes.prev_close IS '昨收价（元）';
COMMENT ON COLUMN daily_quotes.volume IS '成交量（股）';
COMMENT ON COLUMN daily_quotes.amount IS '成交额（元）';
COMMENT ON COLUMN daily_quotes.turnover_rate IS '换手率（%），=成交量/流通股本*100';
COMMENT ON COLUMN daily_quotes.turnover_ratio IS '量比，=当日成交量/过去5日均量';
COMMENT ON COLUMN daily_quotes.amplitude IS '振幅（%），=(最高-最低)/昨收*100';
COMMENT ON COLUMN daily_quotes.change_amount IS '涨跌额，=当日收盘-前日收盘';
COMMENT ON COLUMN daily_quotes.change_pct IS '涨跌幅（%）';
COMMENT ON COLUMN daily_quotes.is_limit_up IS '是否涨停，涨跌幅达到当日涨停限制';
COMMENT ON COLUMN daily_quotes.is_limit_down IS '是否跌停';
COMMENT ON COLUMN daily_quotes.limit_up_price IS '涨停价（元）';
COMMENT ON COLUMN daily_quotes.limit_down_price IS '跌停价（元）';
COMMENT ON COLUMN daily_quotes.consecutive_limit_up_days IS '连板高度：连续涨停的天数，0表示未涨停';
COMMENT ON COLUMN daily_quotes.limit_up_type IS '涨停类型：一字板开盘即涨停/T字板盘中开板又封/实体板自然涨停/烂板反复开板';
COMMENT ON COLUMN daily_quotes.volume_ratio IS '量比：当日成交量/过去5日平均成交量';
COMMENT ON COLUMN daily_quotes.volume_change_pct IS '成交量变化率（%）：与前一日成交量对比';
COMMENT ON COLUMN daily_quotes.ma5 IS '5日移动平均线';
COMMENT ON COLUMN daily_quotes.ma10 IS '10日移动平均线';
COMMENT ON COLUMN daily_quotes.ma20 IS '20日移动平均线';
COMMENT ON COLUMN daily_quotes.ma60 IS '60日移动平均线';

-- 核心查询索引
CREATE INDEX idx_daily_quotes_date ON daily_quotes(trade_date);
CREATE INDEX idx_daily_quotes_stock_date ON daily_quotes(stock_id, trade_date DESC);
CREATE INDEX idx_daily_quotes_limit_up ON daily_quotes(trade_date, is_limit_up) WHERE is_limit_up = TRUE;
CREATE INDEX idx_daily_quotes_consecutive_limit ON daily_quotes(consecutive_limit_up_days) WHERE consecutive_limit_up_days >= 2;
CREATE INDEX idx_daily_quotes_change_pct ON daily_quotes(trade_date, change_pct DESC);
CREATE INDEX idx_daily_quotes_volume_ratio ON daily_quotes(trade_date, volume_ratio DESC) WHERE volume_ratio > 2;


-- ============================================================
-- 3. AI分析结果模块
-- ============================================================

-- ------------------------------------------------------------
-- 3.1 AI选股信号表
-- ------------------------------------------------------------
CREATE TABLE ai_signals (
    id                      BIGSERIAL       PRIMARY KEY,
    signal_date             DATE            NOT NULL,                           -- 信号日期（产生信号的交易日）
    stock_id                BIGINT          NOT NULL REFERENCES stocks(id),
    stock_code              VARCHAR(10)     NOT NULL,                          -- 股票代码（冗余，方便查询）
    stock_name              VARCHAR(50),                                       -- 股票简称（冗余）
    
    -- 策略信息
    strategy_name           VARCHAR(50)     NOT NULL,                          -- 策略名称，如 均线多头排列
    strategy_type           VARCHAR(20)     NOT NULL,                          -- 策略类型：preset预设/custom自定义
    signal_type             VARCHAR(10)     NOT NULL,                          -- 信号类型：buy买入/sell卖出/hold观望
    
    -- AI评分
    confidence              NUMERIC(5,4)    NOT NULL,                          -- AI置信度，0-1
    score                   INT             NOT NULL,                          -- 综合评分，0-100
    reason                  TEXT,                                               -- 选股理由/触发条件描述
    
    -- 触发条件明细（JSON存储，便于扩展）
    trigger_conditions      JSONB,                                             -- 触发的条件详情
    
    -- 次日预期操作
    expected_action         VARCHAR(20)     NOT NULL,                          -- 预期操作：buy开盘买入/buy_dip低吸/sell开盘卖出/hold持有/cut止损
    expected_action_price   NUMERIC(10,2),                                     -- 预期操作价格
    stop_loss_price         NUMERIC(10,2),                                     -- 建议止损价
    take_profit_price       NUMERIC(10,2),                                     -- 建议止盈价
    
    -- 结果反馈（T+1后回填）
    actual_result           VARCHAR(20),                                       -- 实际结果：hit命中/miss未命中/pending待验证
    actual_return_pct       NUMERIC(8,4),                                      -- 实际收益率（%），次日收盘价计算
    
    -- 元数据
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ai_signals IS 'AI选股信号表 - 存储每日AI策略选股结果及后续跟踪';
COMMENT ON COLUMN ai_signals.signal_date IS '信号产生的交易日';
COMMENT ON COLUMN ai_signals.stock_id IS '股票ID';
COMMENT ON COLUMN ai_signals.stock_code IS '股票代码（冗余字段）';
COMMENT ON COLUMN ai_signals.stock_name IS '股票简称（冗余字段）';
COMMENT ON COLUMN ai_signals.strategy_name IS '触发的策略名称：均线多头排列/放量突破/缩量回踩/涨停板战法/涨幅榜情绪';
COMMENT ON COLUMN ai_signals.strategy_type IS '策略类型：preset系统预设/custom用户自定义';
COMMENT ON COLUMN ai_signals.signal_type IS '信号类型：buy买入/sell卖出/hold观望';
COMMENT ON COLUMN ai_signals.confidence IS 'AI模型置信度，范围0-1，越高表示AI越确定';
COMMENT ON COLUMN ai_signals.score IS '综合评分0-100，综合多个维度计算';
COMMENT ON COLUMN ai_signals.reason IS '选股理由，自然语言描述触发原因';
COMMENT ON COLUMN ai_signals.trigger_conditions IS '触发条件详情，JSON格式存储各条件命中情况';
COMMENT ON COLUMN ai_signals.expected_action IS '次日预期操作：buy开盘买入/buy_dip盘中低吸/sell开盘卖出/hold继续持有/cut止损离场';
COMMENT ON COLUMN ai_signals.expected_action_price IS '建议操作价格';
COMMENT ON COLUMN ai_signals.stop_loss_price IS '建议止损价，跌破此价应止损';
COMMENT ON COLUMN ai_signals.take_profit_price IS '建议止盈价，达到此价可考虑止盈';
COMMENT ON COLUMN ai_signals.actual_result IS '实际结果回填：hit信号有效/miss信号无效/pending待验证';
COMMENT ON COLUMN ai_signals.actual_return_pct IS '实际收益率，=次日收盘价/信号日收盘价-1';

CREATE INDEX idx_ai_signals_date ON ai_signals(signal_date DESC);
CREATE INDEX idx_ai_signals_stock ON ai_signals(stock_id);
CREATE INDEX idx_ai_signals_date_stock ON ai_signals(signal_date DESC, stock_id);
CREATE INDEX idx_ai_signals_strategy ON ai_signals(strategy_name);
CREATE INDEX idx_ai_signals_score ON ai_signals(signal_date DESC, score DESC);
CREATE INDEX idx_ai_signals_action ON ai_signals(expected_action);
CREATE INDEX idx_ai_signals_pending ON ai_signals(actual_result) WHERE actual_result = 'pending' OR actual_result IS NULL;


-- ============================================================
-- 4. 辅助视图（便于查询）
-- ============================================================

-- 今日信号视图
CREATE OR REPLACE VIEW v_today_signals AS
SELECT 
    s.stock_code,
    s.stock_name,
    s.exchange,
    d.trade_date,
    d.close_price,
    d.change_pct,
    d.turnover_rate,
    d.consecutive_limit_up_days,
    a.strategy_name,
    a.confidence,
    a.score,
    a.reason,
    a.expected_action,
    a.stop_loss_price,
    a.take_profit_price
FROM ai_signals a
JOIN stocks s ON a.stock_id = s.id
LEFT JOIN daily_quotes d ON d.stock_id = a.stock_id AND d.trade_date = a.signal_date
WHERE a.signal_date = CURRENT_DATE
ORDER BY a.score DESC;

COMMENT ON VIEW v_today_signals IS '今日AI选股信号视图，关联股票和行情数据';

-- 连板股追踪视图
CREATE OR REPLACE VIEW v_consecutive_limit_up AS
SELECT 
    s.stock_code,
    s.stock_name,
    d.trade_date,
    d.close_price,
    d.consecutive_limit_up_days,
    d.limit_up_type,
    d.turnover_rate,
    d.volume_ratio,
    STRING_AGG(c.sector_name, ', ' ORDER BY c.sector_name) AS concepts
FROM daily_quotes d
JOIN stocks s ON d.stock_id = s.id
LEFT JOIN stock_concepts sc ON sc.stock_id = s.id
LEFT JOIN concept_sectors c ON sc.sector_id = c.id
WHERE d.consecutive_limit_up_days >= 2
  AND d.trade_date = (SELECT MAX(trade_date) FROM daily_quotes)
GROUP BY s.id, s.stock_code, s.stock_name, d.id, d.trade_date, d.close_price, 
         d.consecutive_limit_up_days, d.limit_up_type, d.turnover_rate, d.volume_ratio
ORDER BY d.consecutive_limit_up_days DESC;

COMMENT ON VIEW v_consecutive_limit_up IS '连板股追踪视图，显示当前所有连板股票及所属概念';


-- ============================================================
-- 5. 初始化数据
-- ============================================================

-- 插入默认概念板块（示例）
INSERT INTO concept_sectors (sector_code, sector_name, sector_type, description) VALUES
    ('AI', '人工智能', 'concept', '人工智能相关产业链'),
    ('NEWENERGY', '新能源', 'concept', '新能源汽车、光伏、储能'),
    ('CHIP', '芯片半导体', 'concept', '半导体芯片产业链'),
    ('ROBOT', '机器人', 'concept', '工业机器人、人形机器人'),
    ('MILITARY', '军工', 'concept', '国防军工相关'),
    ('CLOUD', '云计算', 'concept', '云计算、大数据'),
    ('PHARMA', '医药生物', 'concept', '医药生物相关'),
    ('FINANCE', '大金融', 'concept', '银行、券商、保险')
ON CONFLICT (sector_code) DO NOTHING;

-- 插入默认策略（参考）
COMMENT ON TABLE ai_signals IS 'v1.0 - 2026-03-24 - 初始版本';
