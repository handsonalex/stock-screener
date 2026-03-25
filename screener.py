"""
选股平台 - 批量极速版
先用批量接口快速获取全市场实时数据，筛选候选股后再逐只分析K线
"""
import json
import time
import threading
import requests
from datetime import datetime
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategies.engine import BUILTIN_STRATEGIES, load_custom_strategy, Signal

# ============ API配置 ============
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.qq.com",
}

# ============ 全局状态 ============
class ScreenerState:
    def __init__(self):
        self.signals: List[dict] = []
        self.last_scan: str = ""
        self.scanning: bool = False
        self.total_scanned: int = 0
        self.config: dict = {}
        self.scan_progress: str = ""

state = ScreenerState()


def load_config():
    with open(os.path.join(os.path.dirname(__file__), "config.json")) as f:
        state.config = json.load(f)


def init_strategies():
    strategies = []
    for name, cfg in state.config.get("strategies", {}).items():
        if cfg.get("enabled", True) and name in BUILTIN_STRATEGIES:
            strategies.append(BUILTIN_STRATEGIES[name]())
    for cfg in state.config.get("custom_strategies", []):
        strategies.append(load_custom_strategy(cfg))
    print(f"已加载 {len(strategies)} 个策略")
    return strategies


def get_realtime_batch(codes: List[str]) -> Dict[str, dict]:
    """批量获取实时行情"""
    results = {}
    for i in range(0, len(codes), 500):
        batch = codes[i:i+500]
        symbols = ",".join([("sh" if c.startswith("6") else "sz") + c for c in batch])
        url = f"{TENCENT_QUOTE_URL}={symbols}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            for line in resp.text.strip().split(";"):
                if "~" not in line:
                    continue
                try:
                    parts = line.split("~")
                    code = parts[2].zfill(6)
                    name = parts[1]
                    price = float(parts[3]) if parts[3] else 0
                    prev_close = float(parts[4]) if parts[4] else 0
                    change_pct = float(parts[32]) if parts[32] else 0
                    volume = float(parts[6]) if parts[6] else 0
                    high = float(parts[33]) if parts[33] else price
                    turnover = float(parts[38]) if len(parts) > 38 and parts[38] else 0
                    if price > 0 and name:
                        results[code] = {
                            "name": name, "price": price, "prev_close": prev_close,
                            "change_pct": change_pct, "volume": volume, "high": high, "turnover": turnover,
                        }
                except:
                    pass
        except Exception as e:
            print(f"批量行情获取失败: {e}")
        time.sleep(0.05)
    return results


def get_kline(code: str, limit: int = 60) -> list:
    """获取K线数据"""
    symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
    url = f"{TENCENT_KLINE_URL}?param={symbol},day,,,{limit},qfq"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        data = resp.json()
        if data.get("code") != 0:
            return []
        stock_data = data.get("data", {}).get(symbol, {})
        day_data = stock_data.get("qfqday") or stock_data.get("day") or []
        klines = []
        for item in day_data[-60:]:
            if len(item) >= 6:
                klines.append({
                    "date": item[0], "open": float(item[1]), "close": float(item[2]),
                    "high": float(item[3]), "low": float(item[4]), "volume": float(item[5]),
                    "amount": 0, "amplitude": 0, "change_pct": 0, "change": 0, "turnover": 0,
                })
        for i in range(len(klines)):
            if i > 0 and klines[i-1]["close"] > 0:
                klines[i]["change_pct"] = round(
                    (klines[i]["close"] - klines[i-1]["close"]) / klines[i-1]["close"] * 100, 2)
                klines[i]["change"] = round(klines[i]["close"] - klines[i-1]["close"], 2)
        return klines
    except:
        return []


def scan_market(strategies: list) -> List[dict]:
    """扫描市场 - 批量极速版"""
    state.scanning = True
    state.signals = []
    state.total_scanned = 0
    
    print(f"\n{'='*50}")
    print(f"开始扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    # 生成股票代码 — 只扫主板，排除创业板(30xxxx)和科创板(68xxxx)
    all_codes = []
    all_codes.extend([str(i).zfill(6) for i in range(600000, 606000)])  # 沪主板
    all_codes.extend([str(i).zfill(6) for i in range(1, 10000)])        # 深主板(000xxx-009xxx)
    
    total = len(all_codes)
    print(f"待扫描: {total} 只")
    state.scan_progress = "批量获取实时行情..."
    
    # 第一步：批量获取实时行情（3-5秒）
    print("正在批量获取实时行情...")
    realtime = get_realtime_batch(all_codes)
    print(f"获取到 {len(realtime)} 只股票行情")
    
    if not realtime:
        print("行情获取失败，请检查网络")
        state.scanning = False
        return []
    
    # 第二步：筛选候选股（主板、非ST、涨幅>2%、价格3-100、有成交量）
    candidates = []
    for code, data in realtime.items():
        price = data.get("price", 0)
        change_pct = data.get("change_pct", 0)
        turnover = data.get("turnover", 0)
        name = data.get("name", "")
        # 排除ST
        if "ST" in name.upper() or "*ST" in name.upper():
            continue
        # 排除停牌(成交量为0)
        if turnover <= 0 or price <= 0:
            continue
        # 价格范围
        if not (3 <= price <= 100):
            continue
        # 只看有涨幅的：涨幅>2%
        if change_pct < 5:
            continue
        candidates.append((code, data))
    
    print(f"候选股: {len(candidates)} 只")
    state.scan_progress = f"分析候选股 {len(candidates)} 只..."
    
    if not candidates:
        state.scanning = False
        return []
    
    # 第三步：逐只获取K线分析
    min_score = state.config.get("notify", {}).get("min_score", 60)
    signals = []
    
    for i, (code, rt) in enumerate(candidates):
        klines = get_kline(code, limit=60)
        if not klines or len(klines) < 10:
            continue
        
        state.total_scanned = i + 1
        
        for strategy in strategies:
            try:
                signal = strategy.check(code, klines)
                if signal and signal.score >= min_score:
                    signal_dict = signal.to_dict()
                    signal_dict["name"] = rt.get("name", "")
                    signal_dict["price"] = rt.get("price", 0)
                    signal_dict["change_pct"] = rt.get("change_pct", 0)
                    key = f"{code}_{strategy.name}"
                    if not any(s.get("_key") == key for s in signals):
                        signal_dict["_key"] = key
                        signals.append(signal_dict)
                        print(f"  ✅ {code} {rt.get('name', '')} {strategy.name} {signal.score}分")
            except:
                pass
        
        if (i + 1) % 100 == 0:
            state.scan_progress = f"分析中 {i+1}/{len(candidates)}"
            print(f"进度: {i+1}/{len(candidates)} | 信号: {len(signals)}")
        
        time.sleep(0.08)
    
    signals.sort(key=lambda x: x.get("score", 0), reverse=True)
    state.signals = signals
    state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state.scanning = False
    state.scan_progress = ""
    
    print(f"\n扫描完成! 分析 {len(candidates)} 只候选股，发现 {len(signals)} 个信号")
    return signals


def run_screener():
    strategies = init_strategies()
    while True:
        try:
            scan_market(strategies)
        except Exception as e:
            print(f"扫描出错: {e}")
        interval = state.config.get("scan_interval", 300)
        time.sleep(interval)


def start_background_scan():
    thread = threading.Thread(target=run_screener, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        strategies = init_strategies()
        scan_market(strategies)
    else:
        start_background_scan()
        while True:
            time.sleep(1)
