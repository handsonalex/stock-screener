"""
Web面板 - 实时选股展示
"""
import os
import sys
import json
import hashlib
from datetime import datetime
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, request, send_file, redirect
import os
from screener import state, load_config, init_strategies, scan_market, start_background_scan

# === 数据库选股 ===
import psycopg2
import pandas as pd
from db_screener import scan_all as db_scan_all, get_signals_from_db, get_market_summary, get_latest_date, query_signals as db_query_signals

DB_CONFIG = dict(host="127.0.0.1", port=5432, database="stock_screener", user="stock_user", password="stock_pass_2024")
PASSWORD_FILE = "/root/.openclaw/workspace/stock_query_password.txt"

def get_token():
    try:
        pw = open(PASSWORD_FILE).read().strip()
    except:
        pw = "stock2024"
    return hashlib.sha256(pw.encode()).hexdigest()[:16]

def is_auth():
    token = request.headers.get("X-Auth-Token") or request.args.get("t") or request.cookies.get("stock_t")
    return token == get_token()

app = Flask(__name__)
app_lock = Lock()


@app.route("/")
def index():
    return send_file(os.path.join(os.path.dirname(__file__), "templates", "index.html"))


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
    source = request.args.get("source", "db")  # db 或 realtime
    
    if source == "db":
        # 直接从数据库读取已有信号，秒出结果
        trade_date = get_latest_date()
        signals, _ = get_signals_from_db(trade_date)
        
        # 策略筛选
        if strategy:
            signals = [s for s in signals if s.get("strategy") == strategy]
        
        # 按分数排序
        signals.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        start = (page - 1) * size
        end = start + size
        
        return jsonify({
            "total": len(signals),
            "page": page,
            "size": size,
            "data": signals[start:end],
            "trade_date": str(trade_date),
            "source": "db"
        })
    else:
        # 原有的实时扫描
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
            "source": "realtime"
        })


@app.route("/api/strategies")
def api_strategies():
    strategies = list(set(s.get("strategy", "") for s in state.signals))
    return jsonify({"strategies": strategies})


@app.route("/api/market")
def api_market():
    # 优先用数据库的实时数据
    summary = get_market_summary()
    if summary:
        return jsonify(summary)
    return jsonify(state.market_overview)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """生成信号 - 根据策略配置重新计算"""
    if state.scanning:
        return jsonify({"msg": "正在生成中，请稍候"})
    
    state.scanning = True
    state.scan_progress = "正在生成..."
    
    # 策略名称映射
    STRATEGY_MAP = {
        'ma_bullish': '均线多头',
        'volume_break': '放量突破',
        'pullback': '缩量回踩',
        'limit_up': '涨停板战法',
        'limit_up_today': '涨停板战法',
        'momentum': '涨幅榜',
    }
    
    def do_scan():
        try:
            config = state.config
            strategies_cfg = config.get("strategies", {})
            custom_strategies = config.get("custom_strategies", [])
            filters = config.get("filters", {})
            
            # 收集启用的策略
            enabled_strategies = []
            strategy_params = {}
            for key, cfg in strategies_cfg.items():
                if cfg.get("enabled", True):
                    chinese_name = STRATEGY_MAP.get(key, key)
                    enabled_strategies.append(chinese_name)
                    strategy_params[chinese_name] = {}
            
            # 从自定义策略获取参数
            for cs in custom_strategies:
                if cs.get("enabled", True):
                    name = cs.get("name", "")
                    if name:
                        enabled_strategies.append(name)
                        strategy_params[name] = cs.get("conditions", {})
            
            signals, trade_date = db_scan_all(
                strategies=enabled_strategies,
                save=True,
                strategy_config=strategy_params,
                filters=filters
            )
            
            # 按分数排序
            signals.sort(key=lambda x: x['score'], reverse=True)
            state.signals = signals
            state.last_scan = str(trade_date)
            state.total_scanned = 5522
            state.signal_count = len(signals)
            state.scan_progress = f"完成，共{len(signals)}个信号"
        except Exception as e:
            state.scan_progress = f"生成失败: {e}"
            import traceback
            traceback.print_exc()
        finally:
            state.scanning = False
    
    import threading
    thread = threading.Thread(target=do_scan, daemon=True)
    thread.start()
    
    return jsonify({"msg": "开始生成信号"})


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


# === K线数据API ===
@app.route("/api/kline/<code>")
def api_kline(code):
    """获取K线数据"""
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        from datetime import date, timedelta
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=120)).isoformat()
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("""
        SELECT d.trade_date, d.open_price as o, d.high_price as h, d.low_price as l, 
               d.close_price as c, d.volume as v, d.amount, d.change_pct
        FROM daily_quotes d
        JOIN stocks s ON d.stock_id = s.id
        WHERE s.stock_code = %s AND d.trade_date >= %s AND d.trade_date <= %s
        ORDER BY d.trade_date
    """, conn, params=[code, start, end])
    conn.close()
    
    if df.empty:
        return jsonify({"error": "无数据", "data": []})
    
    import math
    records = []
    for _, r in df.iterrows():
        pct = float(r['change_pct']) if r['change_pct'] is not None else 0
        if math.isnan(pct):
            pct = 0
        records.append({
            "date": str(r['trade_date']),
            "o": float(r['o']), "h": float(r['h']),
            "l": float(r['l']), "c": float(r['c']),
            "v": int(r['v']), "pct": pct
        })
    
    # 获取股票名称
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT stock_name FROM stocks WHERE stock_code=%s", [code])
    row = cur.fetchone()
    conn.close()
    
    return jsonify({"code": code, "name": row[0] if row else "", "data": records})

# === 历史信号查询API ===
@app.route("/api/signals/query")
def api_signals_query():
    """查询历史信号，支持多条件搜索"""
    trade_date = request.args.get("date")  # 单日
    start_date = request.args.get("start")  # 起始日期
    end_date = request.args.get("end")      # 结束日期
    code = request.args.get("code")         # 股票代码（模糊搜索）
    name = request.args.get("name")         # 股票名称（模糊搜索）
    strategy = request.args.get("strategy") # 策略
    min_score = request.args.get("min_score", 0, type=int)
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 50, type=int)
    
    # 如果只传date，同时作为start和end
    if trade_date and not start_date and not end_date:
        start_date = trade_date
        end_date = trade_date
    
    result = db_query_signals(
        trade_date=trade_date,
        code=code, name=name, strategy=strategy,
        start_date=start_date, end_date=end_date,
        min_score=min_score, page=page, size=size
    )
    return jsonify(result)

# === 每日行情API ===

@app.route("/api/daily/login", methods=["POST"])
def daily_login():
    """每日行情登录"""
    pw = request.json.get("password", "") if request.is_json else request.form.get("password", "")
    try:
        real_pw = open(PASSWORD_FILE).read().strip()
    except:
        real_pw = "stock2024"
    if pw == real_pw:
        token = get_token()
        resp = jsonify({"ok": True, "token": token})
        resp.set_cookie("stock_t", token, max_age=86400*7, samesite="Lax")
        return resp
    return jsonify({"ok": False, "msg": "密码错误"}), 401

@app.route("/api/daily/data")
def daily_data():
    """查询每日行情数据"""
    if not is_auth():
        return jsonify({"error": "请先登录", "auth": False}), 401
    
    trade_date = request.args.get("date")
    sort = request.args.get("sort", "change_pct")
    n = int(request.args.get("n", 50))
    
    sort_map = {
        "change_pct": "d.change_pct DESC NULLS LAST",
        "change_pct_asc": "d.change_pct ASC NULLS LAST",
        "volume": "d.volume DESC NULLS LAST",
        "amount": "d.amount DESC NULLS LAST",
        "turnover_rate": "d.turnover_rate DESC NULLS LAST",
        "amplitude": "d.amplitude DESC NULLS LAST",
        "volume_ratio": "d.volume_ratio DESC NULLS LAST",
    }
    order = sort_map.get(sort, "d.change_pct DESC NULLS LAST")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        sum_df = pd.read_sql("""SELECT COUNT(*) as total,
            COUNT(*) FILTER (WHERE change_pct>0) as up_cnt,
            COUNT(*) FILTER (WHERE change_pct<0) as down_cnt,
            COUNT(*) FILTER (WHERE is_limit_up) as limit_up_cnt,
            ROUND(AVG(change_pct)::numeric,2) as avg_change,
            ROUND(SUM(amount)::numeric/1e8,2) as total_amount_yi
            FROM daily_quotes WHERE trade_date=%s""", conn, params=[trade_date])
        
        sql = f"""SELECT s.stock_code, s.stock_name, d.close_price, d.change_pct, d.change_amount,
            d.volume, d.amount, d.turnover_rate, d.volume_ratio, d.is_limit_up, d.consecutive_limit_up_days
            FROM daily_quotes d JOIN stocks s ON d.stock_id=s.id
            WHERE d.trade_date=%s ORDER BY {order} LIMIT %s"""
        df = pd.read_sql(sql, conn, params=[trade_date, n])
        conn.close()
        
        if df.empty:
            return jsonify({"error": "该日期无数据"})
        return jsonify({"summary": sum_df.iloc[0].to_dict(), "rows": df.to_dict(orient="records")})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/daily/dates")
def daily_dates():
    """获取有数据的日期列表"""
    if not is_auth():
        return jsonify({"error": "请先登录"}), 401
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        df = pd.read_sql("SELECT trade_date, COUNT(*) as cnt FROM daily_quotes GROUP BY trade_date ORDER BY trade_date DESC LIMIT 30", conn)
        conn.close()
        return jsonify({"dates": df.to_dict(orient="records")})
    except Exception as e:
        return jsonify({"error": str(e)})


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
