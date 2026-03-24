"""
策略引擎 - 预设策略 + 自定义策略
"""
from abc import ABC, abstractmethod
from data.fetcher import get_kline_data, get_stock_quote
from typing import Optional
import json


class Signal:
    """选股信号"""
    def __init__(self, code: str, name: str, price: float, change_pct: float,
                 strategy: str, reason: str, score: int = 50):
        self.code = code
        self.name = name
        self.price = price
        self.change_pct = change_pct
        self.strategy = strategy
        self.reason = reason
        self.score = score  # 信号强度 0-100
    
    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "change_pct": self.change_pct,
            "strategy": self.strategy,
            "reason": self.reason,
            "score": self.score,
        }
    
    def __str__(self):
        return f"[{self.strategy}] {self.code} {self.name} {self.price}元 {self.change_pct}% | {self.reason}"


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    @abstractmethod
    def check(self, code: str, klines: list) -> Optional[Signal]:
        """
        检查单只股票是否符合条件
        返回 Signal 表示符合条件，None 表示不符合
        """
        pass


class MA多头排列(BaseStrategy):
    """均线多头排列策略
    条件：
    - MA5 > MA10 > MA20 > MA60
    - 当前价格在MA5之上
    - 今日涨幅 2%-7%
    """
    
    def __init__(self):
        super().__init__("均线多头排列", "MA5>MA10>MA20>MA60，价格在均线上方，温和上涨")
    
    def check(self, code: str, klines: list) -> Optional[Signal]:
        if len(klines) < 60:
            return None
        
        # 计算均线
        closes = [k["close"] for k in klines]
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        
        latest = klines[-1]
        price = latest["close"]
        change_pct = latest["change_pct"]
        
        # 条件判断
        if (ma5 > ma10 > ma20 > ma60 and 
            price > ma5 and 
            2 < change_pct < 7):
            
            score = 50
            # MA5偏离度小加分
            if (price - ma5) / ma5 < 0.02:
                score += 20
            # 连续3天上涨加分
            if all(k["change_pct"] > 0 for k in klines[-3:]):
                score += 15
            
            return Signal(
                code=code[:6], name="", price=price,
                change_pct=change_pct,
                strategy=self.name,
                reason=f"均线多头 MA5={ma5:.2f}>MA10={ma10:.2f}>MA20={ma20:.2f}，价格在均线上方",
                score=min(score, 100)
            )
        return None


class 放量突破(BaseStrategy):
    """放量突破策略
    条件：
    - 今日成交量 > 过去5天平均成交量的2倍
    - 今日涨幅 > 3%
    - 收盘价创20日新高
    """
    
    def __init__(self):
        super().__init__("放量突破", "成交量倍量放大，价格突破近期新高")
    
    def check(self, code: str, klines: list) -> Optional[Signal]:
        if len(klines) < 20:
            return None
        
        latest = klines[-1]
        avg_vol_5 = sum(k["volume"] for k in klines[-5:-1]) / 4
        high_20 = max(k["high"] for k in klines[-20:])
        
        price = latest["close"]
        volume = latest["volume"]
        change_pct = latest["change_pct"]
        
        vol_ratio = volume / avg_vol_5 if avg_vol_5 > 0 else 0
        
        if (vol_ratio >= 2.0 and 
            change_pct > 3 and 
            price >= high_20 * 0.99):  # 接近20日新高
            
            score = 60
            if vol_ratio >= 3:
                score += 15
            if change_pct >= 5:
                score += 10
            
            return Signal(
                code=code[:6], name="", price=price,
                change_pct=change_pct,
                strategy=self.name,
                reason=f"放量{vol_ratio:.1f}倍，涨幅{change_pct:.1f}%，突破20日高点",
                score=min(score, 100)
            )
        return None


class 缩量回踩(BaseStrategy):
    """缩量回踩策略
    条件：
    - 过去5天有至少2天涨幅>2%
    - 今日缩量（成交量 < 5日均量的50%）
    - 今日跌幅在-3%以内
    - 价格仍在20日均线之上
    """
    
    def __init__(self):
        super().__init__("缩量回踩", "前期放量上涨后缩量调整，低吸机会")
    
    def check(self, code: str, klines: list) -> Optional[Signal]:
        if len(klines) < 20:
            return None
        
        closes = [k["close"] for k in klines]
        ma20 = sum(closes[-20:]) / 20
        
        # 过去5天有放量上涨
        recent_5 = klines[-5:-1]
        up_days = sum(1 for k in recent_5 if k["change_pct"] > 2)
        
        latest = klines[-1]
        avg_vol_5 = sum(k["volume"] for k in klines[-5:-1]) / 4
        vol_ratio = latest["volume"] / avg_vol_5 if avg_vol_5 > 0 else 1
        
        if (up_days >= 2 and 
            vol_ratio < 0.5 and 
            -3 < latest["change_pct"] < 0 and 
            latest["close"] > ma20):
            
            return Signal(
                code=code[:6], name="", price=latest["close"],
                change_pct=latest["change_pct"],
                strategy=self.name,
                reason=f"缩量至5日均量的{vol_ratio:.0%}，回踩20日均线，低吸机会",
                score=55
            )
        return None


class 涨停板战法(BaseStrategy):
    """涨停板次日策略
    条件：
    - 昨日涨停
    - 今日低开（开盘价 < 昨收）
    - 今日成交量放大
    """
    
    def __init__(self):
        super().__init__("涨停板战法", "昨日涨停今日低开，博弈反包")
    
    def check(self, code: str, klines: list) -> Optional[Signal]:
        if len(klines) < 3:
            return None
        
        yesterday = klines[-2]
        today = klines[-1]
        
        # 昨日涨停
        if yesterday["change_pct"] < 9.5:
            return None
        
        # 今日低开
        if today["open"] >= yesterday["close"]:
            return None
        
        # 今日放量
        if len(klines) >= 6:
            avg_vol = sum(k["volume"] for k in klines[-6:-2]) / 4
            if today["volume"] < avg_vol * 0.8:
                return None
        
        return Signal(
            code=code[:6], name="", price=today["close"],
            change_pct=today["change_pct"],
            strategy=self.name,
            reason=f"昨日涨停{yesterday['change_pct']:.1f}%，今日低开后{'翻红' if today['change_pct'] > 0 else '震荡'}",
            score=60
        )


class 涨幅榜情绪(BaseStrategy):
    """涨幅榜筛选策略
    条件：
    - 当日涨幅 3%-7%
    - 成交量放大
    - 换手率 3%-15%
    """
    
    def __init__(self):
        super().__init__("涨幅榜情绪", "筛选温和放量上涨的强势股")
    
    def check(self, code: str, klines: list) -> Optional[Signal]:
        if len(klines) < 1:
            return None
        
        latest = klines[-1]
        change_pct = latest["change_pct"]
        turnover = latest.get("turnover", 0)
        
        if 3 < change_pct < 7 and 3 < turnover < 15:
            score = 50
            if change_pct > 5:
                score += 10
            if turnover > 5:
                score += 10
            
            return Signal(
                code=code[:6], name="", price=latest["close"],
                change_pct=change_pct,
                strategy=self.name,
                reason=f"涨幅{change_pct:.1f}%，换手率{turnover:.1f}%，温和放量",
                score=score
            )
        return None


# ============ 预设策略注册 ============

BUILTIN_STRATEGIES = {
    "ma_bullish": MA多头排列,
    "volume_break": 放量突破,
    "pullback": 缩量回踩,
    "limit_up": 涨停板战法,
    "momentum": 涨幅榜情绪,
}


def load_custom_strategy(config: dict) -> BaseStrategy:
    """
    从配置加载自定义策略
    config格式：
    {
        "name": "我的策略",
        "conditions": {
            "change_pct_min": 3,
            "change_pct_max": 7,
            "volume_ratio_min": 2,
            "turnover_min": 3,
        }
    }
    """
    
    class CustomStrategy(BaseStrategy):
        def __init__(self, conditions):
            super().__init__(config.get("name", "自定义策略"), config.get("description", ""))
            self.conditions = conditions
        
        def check(self, code: str, klines: list) -> Optional[Signal]:
            if len(klines) < 20:
                return None
            
            latest = klines[-1]
            closes = [k["close"] for k in klines]
            volumes = [k["volume"] for k in klines]
            
            conditions = self.conditions
            reasons = []
            passed = True
            
            # 涨跌幅范围
            if "change_pct_min" in conditions:
                if latest["change_pct"] < conditions["change_pct_min"]:
                    passed = False
                else:
                    reasons.append(f"涨幅>{conditions['change_pct_min']}%")
            if "change_pct_max" in conditions:
                if latest["change_pct"] > conditions["change_pct_max"]:
                    passed = False
                else:
                    reasons.append(f"涨幅<{conditions['change_pct_max']}%")
            
            # 量比
            if "volume_ratio_min" in conditions:
                avg_vol = sum(volumes[-5:-1]) / 4
                vol_ratio = latest["volume"] / avg_vol if avg_vol > 0 else 0
                if vol_ratio < conditions["volume_ratio_min"]:
                    passed = False
                else:
                    reasons.append(f"量比>{conditions['volume_ratio_min']}")
            
            # 换手率
            if "turnover_min" in conditions:
                if latest.get("turnover", 0) < conditions["turnover_min"]:
                    passed = False
                else:
                    reasons.append(f"换手率>{conditions['turnover_min']}%")
            if "turnover_max" in conditions:
                if latest.get("turnover", 0) > conditions["turnover_max"]:
                    passed = False
                else:
                    reasons.append(f"换手率<{conditions['turnover_max']}%")
            
            # 价格在均线上方
            if conditions.get("above_ma20"):
                ma20 = sum(closes[-20:]) / 20
                if latest["close"] < ma20:
                    passed = False
                else:
                    reasons.append("价格在MA20上方")
            
            if passed:
                return Signal(
                    code=code[:6], name="", price=latest["close"],
                    change_pct=latest["change_pct"],
                    strategy=self.name,
                    reason=" | ".join(reasons),
                    score=50
                )
            return None
    
    return CustomStrategy(config.get("conditions", {}))
