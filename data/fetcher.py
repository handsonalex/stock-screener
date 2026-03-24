"""
数据获取模块 - 新浪财经API
"""
import requests
import json
import time
from typing import Optional

# API URLs
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def get_stock_list(market="all", limit=5000):
    """获取股票列表 - 简化版本"""
    sh_stocks = [{"f12": str(i).zfill(6), "f14": "", "f2": 0, "f3": 0, "f5": 0, "f8": 0, "f13": 1} 
                 for i in range(600000, 605000)]
    sz_stocks = [{"f12": str(i).zfill(6), "f14": "", "f2": 0, "f3": 0, "f5": 0, "f8": 0, "f13": 0}
                 for i in range(1, 3000)]
    cy_stocks = [{"f12": str(i).zfill(6), "f14": "", "f2": 0, "f3": 0, "f5": 0, "f8": 0, "f13": 0}
                 for i in range(300001, 301000)]
    return (sh_stocks + sz_stocks + cy_stocks)[:limit]


def get_stock_quote(stock_code):
    """获取单只股票实时行情"""
    if stock_code.startswith("6"):
        symbol = "sh" + stock_code
    else:
        symbol = "sz" + stock_code
    
    url = "https://hq.sinajs.cn/list=" + symbol
    try:
        resp = requests.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn"}, timeout=10)
        text = resp.text
        # 解析新浪数据格式
        idx = text.find("\"")
        if idx >= 0:
            idx2 = text.find("\"", idx + 1)
            if idx2 > idx + 1:
                data = text[idx+1:idx2].split(",")
                if len(data) > 9:
                    return {
                        "name": data[0],
                        "open": float(data[1]) if data[1] else 0,
                        "close": float(data[2]) if data[2] else 0,
                        "price": float(data[3]) if data[3] else 0,
                        "high": float(data[4]) if data[4] else 0,
                        "low": float(data[5]) if data[5] else 0,
                        "volume": float(data[8]) if data[8] else 0,
                        "amount": float(data[9]) if data[9] else 0,
                    }
    except Exception as e:
        print(f"获取行情失败 {stock_code}: {e}")
    return None


def get_kline_data(stock_code, klt=101, limit=120):
    """获取K线数据"""
    if stock_code.startswith("6"):
        symbol = "sh" + stock_code
    else:
        symbol = "sz" + stock_code
    
    url = SINA_KLINE_URL + "?symbol=" + symbol + "&scale=240&ma=no&datalen=" + str(limit)
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        
        klines = []
        for item in data:
            klines.append({
                "date": item.get("day", ""),
                "open": float(item.get("open", 0)),
                "close": float(item.get("close", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "volume": float(item.get("volume", 0)),
                "amount": 0,
                "amplitude": 0,
                "change_pct": 0,
                "change": 0,
                "turnover": 0,
            })
        
        for i in range(len(klines)):
            if i > 0 and klines[i-1]["close"] > 0:
                klines[i]["change_pct"] = round(
                    (klines[i]["close"] - klines[i-1]["close"]) / klines[i-1]["close"] * 100, 2
                )
                klines[i]["change"] = round(klines[i]["close"] - klines[i-1]["close"], 2)
        
        return klines
        
    except Exception as e:
        print(f"获取K线失败 {stock_code}: {e}")
    return []


def get_market_overview():
    """获取大盘指数"""
    symbols = {"sh": "sh000001", "sz": "sz399001", "cy": "sz399006"}
    result = {}
    
    for name, sym in symbols.items():
        try:
            url = "https://hq.sinajs.cn/list=" + sym
            resp = requests.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn"}, timeout=10)
            text = resp.text
            idx = text.find("\"")
            if idx >= 0:
                idx2 = text.find("\"", idx + 1)
                if idx2 > idx + 1:
                    data = text[idx+1:idx2].split(",")
                    if len(data) > 8 and float(data[2]) > 0:
                        price = float(data[3])
                        prev = float(data[2])
                        result[name] = {
                            "name": data[0],
                            "price": price,
                            "change_pct": round((price - prev) / prev * 100, 2),
                            "volume": float(data[8]) if data[8] else 0,
                        }
        except:
            pass
    
    return result


if __name__ == "__main__":
    print("测试K线...")
    kline = get_kline_data("600143", limit=5)
    print(f"获取到 {len(kline)} 条")
    for k in kline:
        print(f"  {k['date']} 收:{k['close']} 涨幅:{k['change_pct']}%")
    
    print("\n测试大盘...")
    overview = get_market_overview()
    print(overview)
