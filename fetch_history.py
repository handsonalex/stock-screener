#!/usr/bin/env python3
"""用腾讯API补A股近两年历史K线数据"""
import psycopg2
import requests
import json
import pandas as pd
from datetime import date, timedelta
import sys, time

DB = dict(host="127.0.0.1", port=5432, database="stock_screener", user="stock_user", password="stock_pass_2024")
TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com"}

def get_stock_list():
    conn = psycopg2.connect(**DB)
    df = pd.read_sql("SELECT id, stock_code, exchange FROM stocks WHERE status='active'", conn)
    conn.close()
    return df

def fetch_tencent_kline(code, exchange, start_date, end_date, days=500):
    """腾讯日K线"""
    prefix = "sz" if exchange == "SZ" else "sh"
    symbol = f"{prefix}{code}"
    param = f"{symbol},day,{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')},{days},qfq"
    try:
        r = requests.get(TENCENT_URL, params={"param": param}, headers=HEADERS, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return None
        stock_data = data["data"].get(symbol, {})
        klines = stock_data.get("day") or stock_data.get("qfqday")
        if not klines:
            return None
        rows = []
        for k in klines:
            if len(k) >= 6:
                rows.append({"date": k[0], "open": float(k[1]), "close": float(k[2]),
                            "high": float(k[3]), "low": float(k[4]), "volume": int(float(k[5]))})
        return pd.DataFrame(rows) if rows else None
    except Exception:
        return None

def insert_daily_quotes(stock_id, df, cur):
    count = 0
    for _, r in df.iterrows():
        try:
            cur.execute("""
                INSERT INTO daily_quotes 
                (stock_id, trade_date, open_price, high_price, low_price, close_price, 
                 prev_close, volume, amount, change_pct, change_amount, turnover_rate,
                 amplitude, is_limit_up, is_limit_down)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (stock_id, trade_date) DO NOTHING
            """, (stock_id, r['date'], r['open'], r['high'], r['low'], r['close'],
                  None, r['volume'], None, None, None, None, None, False, False))
            count += 1
        except Exception:
            pass
    return count

def main():
    end_date = date.today()
    start_date = end_date - timedelta(days=730)
    print(f"补历史数据: {start_date} ~ {end_date}", flush=True)
    
    stocks = get_stock_list()
    print(f"共 {len(stocks)} 只股票", flush=True)
    
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    total = 0
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code = row['stock_code']
        df = fetch_tencent_kline(code, row['exchange'], start_date, end_date)
        if df is not None and not df.empty:
            n = insert_daily_quotes(row['id'], df, cur)
            total += n
        
        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  [{i+1}/{len(stocks)}] 已插入 {total} 条", flush=True)
            time.sleep(0.5)
    
    conn.commit()
    conn.close()
    print(f"完成！共插入 {total} 条K线数据", flush=True)

if __name__ == "__main__":
    main()
