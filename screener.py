"""
选股平台主程序
"""
import json
import time
import threading
from datetime import datetime
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.fetcher import get_stock_list, get_kline_data, get_market_overview
from strategies.engine import BUILTIN_STRATEGIES, load_custom_strategy, Signal


# ============ 全局状态 ============

class ScreenerState:
    def __init__(self):
        self.signals: List[dict] = []  # 今日选股结果
        self.stock_cache: Dict[str, dict] = {}  # 股票基本信息缓存
        self.last_scan: str = ""  # 上次扫描时间
        self.scanning: bool = False  # 是否正在扫描
        self.total_scanned: int = 0  # 已扫描数量
        self.market_overview: dict = {}  # 大盘概况
        self.config: dict = {}  # 配置

state = ScreenerState()


def load_config():
    """加载配置"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path, "r") as f:
        state.config = json.load(f)
    print(f"配置已加载: {len(state.config.get('strategies', {}))} 个策略")


def init_strategies():
    """初始化策略"""
    strategies = []
    
    # 加载预设策略
    for name, cfg in state.config.get("strategies", {}).items():
        if cfg.get("enabled", True) and name in BUILTIN_STRATEGIES:
            strategies.append(BUILTIN_STRATEGIES[name]())
    
    # 加载自定义策略
    for cfg in state.config.get("custom_strategies", []):
        strategies.append(load_custom_strategy(cfg))
    
    print(f"已加载 {len(strategies)} 个策略: {[s.name for s in strategies]}")
    return strategies


def apply_filters(stock: dict, filters: dict) -> bool:
    """应用股票过滤器 - 简化版，预设列表不过滤价格"""
    code = stock.get("f12", "")
    
    # 排除北交所（8开头的）
    if code.startswith("8"):
        return False
    
    # 排除明显无效的代码
    if not code.isdigit() or len(code) != 6:
        return False
    
    return True


def scan_market(strategies: list) -> List[dict]:
    """全市场扫描"""
    state.scanning = True
    state.signals = []
    state.total_scanned = 0
    
    print(f"\n{'='*50}")
    print(f"开始扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    # 获取股票列表
    print("获取股票列表...")
    stocks = get_stock_list(limit=5000)
    print(f"共 {len(stocks)} 只股票")
    
    # 过滤
    filters = state.config.get("filters", {})
    filtered_stocks = [s for s in stocks if apply_filters(s, filters)]
    print(f"过滤后: {len(filtered_stocks)} 只")
    
    # 缓存股票基本信息
    state.stock_cache = {}
    for s in filtered_stocks:
        code = str(s.get("f12", "")).zfill(6)
        state.stock_cache[code] = {
            "code": code,
            "name": s.get("f14", ""),
            "price": s.get("f2", 0),
            "change_pct": s.get("f3", 0),
            "volume": s.get("f5", 0),
            "turnover": s.get("f8", 0),
        }
    
    # 逐只扫描
    min_score = state.config.get("notify", {}).get("min_score", 50)
    
    for i, stock in enumerate(filtered_stocks):
        code = str(stock.get("f12", "")).zfill(6)
        state.total_scanned = i + 1
        
        # 获取K线数据
        klines = get_kline_data(code, limit=120)
        if not klines:
            continue
        
        # 各策略检查
        for strategy in strategies:
            try:
                signal = strategy.check(code, klines)
                if signal and signal.score >= min_score:
                    signal.name = state.stock_cache.get(code, {}).get("name", "")
                    sig_dict = signal.to_dict()
                    # 避免重复
                    key = f"{code}_{strategy.name}"
                    if not any(s.get("_key") == key for s in state.signals):
                        sig_dict["_key"] = key
                        state.signals.append(sig_dict)
                        print(f"  ✅ {signal}")
            except Exception as e:
                print(f"  ❌ {code} {strategy.name} 出错: {e}")
        
        # 进度显示
        if (i + 1) % 100 == 0:
            print(f"进度: {i+1}/{len(filtered_stocks)} | 已发现 {len(state.signals)} 个信号")
    
    # 按评分排序
    state.signals.sort(key=lambda x: x.get("score", 0), reverse=True)
    state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state.scanning = False
    
    print(f"\n扫描完成! 共扫描 {state.total_scanned} 只，发现 {len(state.signals)} 个信号")
    
    return state.signals


def format_signal_message(signals: list) -> str:
    """格式化选股结果为消息"""
    if not signals:
        return ""
    
    lines = [f"📊 选股信号 ({datetime.now().strftime('%m/%d %H:%M')})\n"]
    
    for sig in signals[:20]:
        emoji = "🔴" if sig["change_pct"] > 0 else "🟢"
        score_bar = "█" * (sig["score"] // 10) + "░" * (10 - sig["score"] // 10)
        lines.append(
            f"{emoji} {sig['code']} {sig['name']} | {sig['price']}元 {sig['change_pct']}% | {sig['strategy']}\n"
            f"   理由: {sig['reason']}\n"
            f"   信号强度: [{score_bar}] {sig['score']}分\n"
        )
    
    return "\n".join(lines)


def run_screener():
    """运行选股器（在后台线程中）"""
    strategies = init_strategies()
    
    while True:
        try:
            scan_market(strategies)
            # 打印摘要
            for sig in state.signals[:10]:
                print(f"  {sig['code']} {sig['name']} {sig['score']}分 {sig['strategy']}")
        except Exception as e:
            print(f"扫描出错: {e}")
        
        interval = state.config.get("scan_interval", 300)
        print(f"\n下次扫描: {interval}秒后")
        time.sleep(interval)


def start_background_scan():
    """启动后台扫描线程"""
    thread = threading.Thread(target=run_screener, daemon=True)
    thread.start()
    return thread


# ============ 命令行入口 ============

if __name__ == "__main__":
    load_config()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # 单次扫描
        strategies = init_strategies()
        signals = scan_market(strategies)
        print(format_signal_message(signals))
    else:
        # 持续扫描
        start_background_scan()
        # 保持主线程运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止扫描")
