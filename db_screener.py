"""
数据库驱动的选股扫描器 - 直接用 daily_quotes 数据做策略分析
秒出结果，无需实时抓取
"""
import psycopg2
import pandas as pd
from datetime import date

DB_CONFIG = dict(host="127.0.0.1", port=5432, database="stock_screener", user="stock_user", password="stock_pass_2024")

def get_latest_date():
    """获取最新交易日"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT MAX(trade_date) FROM daily_quotes")
    d = cur.fetchone()[0]
    conn.close()
    return d

def get_trade_dates(n=10):
    """获取最近N个交易日"""
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT DISTINCT trade_date FROM daily_quotes ORDER BY trade_date DESC LIMIT %s", conn, params=[n])
    conn.close()
    return df['trade_date'].tolist()

def scan_strategy(df, strategy_name, params=None):
    """对DataFrame执行策略筛选，params为策略参数"""
    signals = []
    p = params or {}
    
    if strategy_name == "涨幅榜":
        pct_min = p.get('change_pct_min', 5)
        vol_min = p.get('volume_ratio_min', 1.5)
        subset = df[(df['change_pct'] > pct_min) & (df['volume_ratio'] > vol_min) & (~df['is_st'])].head(50)
        for _, r in subset.iterrows():
            score = min(95, int(r['change_pct'] * 5 + r['volume_ratio'] * 10))
            reason = f"涨幅{r['change_pct']:.1f}%，量比{r['volume_ratio']:.2f}，换手率{r['turnover_rate']:.1f}%"
            signals.append(_make_signal(r, "涨幅榜", reason, score))
    
    elif strategy_name == "涨停板战法":
        subset = df[df['is_limit_up'] & (~df['is_st'])]
        for _, r in subset.iterrows():
            score = 90 if r['consecutive_limit_up_days'] >= 2 else 75
            extra = f"，{r['consecutive_limit_up_days']}连板" if r['consecutive_limit_up_days'] > 1 else ""
            reason = f"涨停{extra}，量比{r['volume_ratio']:.2f}"
            signals.append(_make_signal(r, "涨停板战法", reason, score))
    
    elif strategy_name == "放量突破":
        vol_min = p.get('volume_ratio_min', 2)
        pct_min = p.get('change_pct_min', 3)
        turnover_min = p.get('turnover_min', 3)
        subset = df[(df['volume_ratio'] > vol_min) & (df['change_pct'] > pct_min) & (df['turnover_rate'] > turnover_min) & (~df['is_st'])].head(50)
        for _, r in subset.iterrows():
            score = min(90, int(r['volume_ratio'] * 15 + r['change_pct'] * 3))
            reason = f"量比{r['volume_ratio']:.2f}，涨幅{r['change_pct']:.1f}%，换手率{r['turnover_rate']:.1f}%"
            signals.append(_make_signal(r, "放量突破", reason, score))
    
    elif strategy_name == "均线多头":
        if 'ma5' in df.columns and df['ma5'].notna().any():
            pct_min = p.get('change_pct_min', 2)
            pct_max = p.get('change_pct_max', 7)
            subset = df[
                (df['ma5'].notna()) & (df['ma10'].notna()) & (df['ma20'].notna()) &
                (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20']) &
                (df['close_price'] > df['ma5']) &
                (df['change_pct'] >= pct_min) & (df['change_pct'] <= pct_max) &
                (~df['is_st'])
            ].head(50)
            for _, r in subset.iterrows():
                score = min(85, int(50 + r['change_pct'] * 5))
                reason = f"均线多头，涨幅{r['change_pct']:.1f}%，价格站上MA5"
                signals.append(_make_signal(r, "均线多头", reason, score))
    
    elif strategy_name == "缩量回踩":
        if 'ma20' in df.columns and df['ma20'].notna().any():
            vol_max = p.get('volume_ratio_max', 0.8)
            pct_min = p.get('change_pct_min', -3)
            pct_max = p.get('change_pct_max', -0.5)
            subset = df[
                (df['volume_ratio'] < vol_max) & 
                (df['change_pct'].between(pct_min, pct_max)) &
                (df['ma20'].notna()) & (df['close_price'] > df['ma20']) &
                (~df['is_st'])
            ].head(50)
            for _, r in subset.iterrows():
                score = min(80, int(60 - r['change_pct'] * 5))
                reason = f"缩量回踩，量比{r['volume_ratio']:.2f}，跌幅{abs(r['change_pct']):.1f}%，接近MA20支撑"
                signals.append(_make_signal(r, "缩量回踩", reason, score))
    
    elif strategy_name == "高换手":
        turnover_min = p.get('turnover_min', 10)
        pct_min = p.get('change_pct_min', 3)
        subset = df[(df['turnover_rate'] > turnover_min) & (df['change_pct'] > pct_min) & (~df['is_st'])].head(50)
        for _, r in subset.iterrows():
            score = min(85, int(r['turnover_rate'] * 2 + r['change_pct'] * 3))
            reason = f"换手率{r['turnover_rate']:.1f}%，涨幅{r['change_pct']:.1f}%，成交活跃"
            signals.append(_make_signal(r, "高换手", reason, score))
    
    elif strategy_name == "连板股":
        min_days = p.get('min_consecutive_days', 2)
        subset = df[(df['consecutive_limit_up_days'] >= min_days) & (~df['is_st'])]
        subset = subset.sort_values('consecutive_limit_up_days', ascending=False)
        for _, r in subset.iterrows():
            score = min(95, 80 + r['consecutive_limit_up_days'] * 5)
            reason = f"{r['consecutive_limit_up_days']}连板，量比{r['volume_ratio']:.2f}"
            signals.append(_make_signal(r, "连板股", reason, score))
    
    return signals

def _make_signal(row, strategy, reason, score):
    """构建信号字典"""
    return {
        "code": row['stock_code'],
        "name": row['stock_name'],
        "price": float(row['close_price']),
        "change_pct": float(row['change_pct']) if row['change_pct'] else 0,
        "strategy": strategy,
        "reason": reason,
        "score": min(100, max(0, int(score))),
        "volume_ratio": float(row['volume_ratio']) if row['volume_ratio'] else 0,
        "turnover_rate": float(row['turnover_rate']) if row['turnover_rate'] else 0,
        "is_limit_up": bool(row['is_limit_up']),
        "consecutive_limit_up_days": int(row['consecutive_limit_up_days']) if row['consecutive_limit_up_days'] else 0,
    }

def save_signals_to_db(signals, trade_date):
    """保存信号到数据库"""
    if not signals:
        return 0
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    saved = 0
    for s in signals:
        try:
            cur.execute("""
                INSERT INTO stock_signals 
                (trade_date, stock_code, stock_name, price, change_pct, strategy, reason, score, volume_ratio, turnover_rate, is_limit_up, consecutive_limit_up_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date, stock_code, strategy) DO UPDATE SET
                    price=EXCLUDED.price, change_pct=EXCLUDED.change_pct, reason=EXCLUDED.reason, score=EXCLUDED.score
            """, (trade_date, s['code'], s['name'], s['price'], s['change_pct'], 
                  s['strategy'], s['reason'], s['score'], 
                  s.get('volume_ratio'), s.get('turnover_rate'),
                  s.get('is_limit_up', False), s.get('consecutive_limit_up_days', 0)))
            saved += 1
        except Exception as e:
            print(f"保存信号失败 {s['code']}: {e}")
    conn.commit()
    conn.close()
    return saved

def scan_all(strategies=None, save=True, strategy_config=None, filters=None):
    """执行全量扫描，返回所有信号
    - strategies: 策略名称列表，如 ["涨幅榜", "涨停板战法"]
    - strategy_config: 策略参数配置，如 {"涨幅榜": {"change_pct_min": 5, "volume_ratio_min": 1.5}}
    - filters: 过滤条件，如 {"min_price": 3, "max_price": 100}
    """
    trade_date = get_latest_date()
    if not trade_date:
        return [], None
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("""
        SELECT s.stock_code, s.stock_name, s.is_st, s.market,
               d.close_price, d.change_pct, d.volume, d.amount,
               d.turnover_rate, d.volume_ratio, d.amplitude,
               d.is_limit_up, d.consecutive_limit_up_days
        FROM daily_quotes d
        JOIN stocks s ON d.stock_id = s.id
        WHERE d.trade_date = %s
    """, conn, params=[trade_date])
    conn.close()
    
    # 当前数据只有一天，MA暂时不可用，置为None
    df['ma5'] = None
    df['ma10'] = None
    df['ma20'] = None
    
    # 默认策略
    if strategies is None:
        strategies = ["涨幅榜", "涨停板战法", "放量突破", "均线多头", "缩量回踩", "高换手", "连板股"]
    
    # 策略参数映射
    strategy_params = strategy_config or {}
    
    # 应用过滤条件
    f = filters or {}
    min_price = f.get('min_price', 0)
    max_price = f.get('max_price', 99999)
    exclude_st = f.get('exclude_st', True)
    exclude_gem = f.get('exclude_gem', True)    # 排除创业板（30开头）
    exclude_star = f.get('exclude_star', True)   # 排除科创板（68开头）
    mainboard_only = f.get('mainboard_only', True)  # 只要主板

    if exclude_st:
        df = df[~df['is_st']]

    # 主板过滤：通过market字段（更可靠）
    if mainboard_only or exclude_gem or exclude_star:
        df = df[df['market'] == '主板']

    df = df[(df['close_price'] >= min_price) & (df['close_price'] <= max_price)]
    
    all_signals = []
    for sname in strategies:
        params = strategy_params.get(sname, {})
        signals = scan_strategy(df, sname, params)
        all_signals.extend(signals)
    
    # 持久化到数据库
    if save and all_signals:
        save_signals_to_db(all_signals, trade_date)
    
    return all_signals, trade_date

def get_signals_from_db(trade_date=None, strategy=None):
    """直接从数据库读取已有信号，不重新计算"""
    if trade_date is None:
        trade_date = get_latest_date()
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    conditions = ["trade_date = %s"]
    params = [trade_date]
    
    if strategy:
        conditions.append("strategy = %s")
        params.append(strategy)
    
    where = " AND ".join(conditions)
    
    sql = f"""
        SELECT trade_date, stock_code, stock_name, price, change_pct, 
               strategy, reason, score, volume_ratio, turnover_rate,
               is_limit_up, consecutive_limit_up_days
        FROM stock_signals
        WHERE {where}
        ORDER BY score DESC
    """
    df = pd.read_sql(sql, conn, params=params)
    conn.close()
    
    # 转换为Python类型
    records = []
    for _, r in df.iterrows():
        record = {}
        for k, v in r.items():
            if hasattr(v, 'item'):
                record[k] = v.item()
            elif hasattr(v, 'isoformat'):
                record[k] = str(v)
            else:
                record[k] = v
        records.append(record)
    
    return records, trade_date

def query_signals(trade_date=None, code=None, name=None, strategy=None, 
                  start_date=None, end_date=None, min_score=0, 
                  page=1, size=50):
    """查询历史信号，支持多条件搜索"""
    conn = psycopg2.connect(**DB_CONFIG)
    
    conditions = []
    params = []
    
    if trade_date:
        conditions.append("trade_date = %s")
        params.append(trade_date)
    if start_date:
        conditions.append("trade_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("trade_date <= %s")
        params.append(end_date)
    if code:
        conditions.append("stock_code LIKE %s")
        params.append(f"%{code}%")
    if name:
        conditions.append("stock_name ILIKE %s")
        params.append(f"%{name}%")
    if strategy:
        conditions.append("strategy = %s")
        params.append(strategy)
    if min_score > 0:
        conditions.append("score >= %s")
        params.append(min_score)
    
    where = " AND ".join(conditions) if conditions else "1=1"
    
    # 总数
    count_sql = f"SELECT COUNT(*) FROM stock_signals WHERE {where}"
    total = pd.read_sql(count_sql, conn, params=params).iloc[0, 0]
    
    # 分页数据
    offset = (page - 1) * size
    data_sql = f"""
        SELECT trade_date, stock_code, stock_name, price, change_pct, 
               strategy, reason, score, volume_ratio, turnover_rate,
               is_limit_up, consecutive_limit_up_days
        FROM stock_signals WHERE {where}
        ORDER BY trade_date DESC, score DESC
        LIMIT %s OFFSET %s
    """
    df = pd.read_sql(data_sql, conn, params=params + [size, offset])
    conn.close()
    
    # 转换为原生Python类型
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if hasattr(v, 'item'):  # numpy类型
                r[k] = v.item()
            elif hasattr(v, 'isoformat'):  # date/datetime
                r[k] = str(v)
    
    return {
        "total": int(total),
        "page": page,
        "size": size,
        "data": records
    }

def get_market_summary(trade_date=None):
    """获取市场概况"""
    if trade_date is None:
        trade_date = get_latest_date()
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE change_pct > 0) as up_cnt,
               COUNT(*) FILTER (WHERE change_pct < 0) as down_cnt,
               COUNT(*) FILTER (WHERE is_limit_up) as limit_up_cnt,
               COUNT(*) FILTER (WHERE is_limit_down) as limit_down_cnt,
               COUNT(*) FILTER (WHERE change_pct >= 5) as big_up_cnt,
               ROUND(AVG(change_pct)::numeric, 2) as avg_change,
               ROUND(SUM(amount)::numeric / 1e8, 2) as total_amount_yi
        FROM daily_quotes WHERE trade_date = %s
    """, conn, params=[trade_date])
    conn.close()
    
    if df.empty:
        return None
    return df.iloc[0].to_dict()


if __name__ == "__main__":
    signals, dt = scan_all()
    print(f"交易日: {dt}")
    print(f"共产生 {len(signals)} 个信号")
    for s in signals[:10]:
        print(f"  [{s['strategy']}] {s['code']} {s['name']} {s['price']} {s['change_pct']}% - {s['reason']}")
