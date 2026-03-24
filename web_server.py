"""
Web面板 - 实时选股展示
"""
import os
import sys
import json
from datetime import datetime
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request
from screener import state, load_config, init_strategies, scan_market, start_background_scan

app = Flask(__name__)
app_lock = Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "scanning": state.scanning,
        "last_scan": state.last_scan,
        "total_scanned": state.total_scanned,
        "signal_count": len(state.signals),
    })


@app.route("/api/signals")
def api_signals():
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    strategy = request.args.get("strategy", "")
    
    signals = state.signals
    if strategy:
        signals = [s for s in signals if s.get("strategy") == strategy]
    
    start = (page - 1) * size
    end = start + size
    
    return jsonify({
        "total": len(signals),
        "page": page,
        "size": size,
        "data": signals[start:end],
    })


@app.route("/api/strategies")
def api_strategies():
    strategies = list(set(s.get("strategy", "") for s in state.signals))
    return jsonify({"strategies": strategies})


@app.route("/api/market")
def api_market():
    return jsonify(state.market_overview)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """手动触发扫描"""
    if state.scanning:
        return jsonify({"msg": "正在扫描中，请稍候"})
    
    def do_scan():
        strategies = init_strategies()
        scan_market(strategies)
    
    import threading
    thread = threading.Thread(target=do_scan, daemon=True)
    thread.start()
    
    return jsonify({"msg": "扫描已开始"})


@app.route("/api/config")
def api_config():
    return jsonify(state.config)


@app.route("/api/config", methods=["POST"])
def api_update_config():
    """更新配置"""
    new_config = request.json
    if not new_config:
        return jsonify({"msg": "配置为空"}), 400
    
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(config_path, "w") as f:
        json.dump(new_config, f, ensure_ascii=False, indent=2)
    
    state.config = new_config
    return jsonify({"msg": "配置已更新"})


@app.route("/api/stock/<code>")
def api_stock_detail(code):
    """获取单只股票详情"""
    for sig in state.signals:
        if sig.get("code") == code:
            return jsonify(sig)
    return jsonify({"msg": "未找到"}), 404


def start_web(host="0.0.0.0", port=5000):
    """启动Web服务"""
    # 加载配置
    load_config()
    
    # 启动后台扫描
    start_background_scan()
    
    print(f"Web面板: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    start_web()
