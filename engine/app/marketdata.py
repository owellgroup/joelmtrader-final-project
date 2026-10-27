"""Cached multi-timeframe frames with indicators and structure pre-computed."""
import threading
import time

import pandas as pd

from .config import TIMEFRAMES
from .indicators import add_indicators
from . import structure as st

TTL = {"M1": 3, "M5": 8, "M10": 12, "M15": 20, "M30": 45, "H1": 120, "H4": 420, "D1": 1800}
COUNT = {"M1": 300, "M5": 300, "M10": 250, "M15": 250, "M30": 200, "H1": 250, "H4": 200, "D1": 150}
MIN_BARS = {"M1": 40, "M5": 40, "M10": 30, "M15": 30, "M30": 28, "H1": 28, "H4": 24, "D1": 20}
FULL_DETAIL = {"M5", "M10", "M15", "H1", "M1"}
# A symbol is usable for analysis if these exist. Missing M10/M30/M1 can be synthesised.
CORE_TFS = ("D1", "H4", "H1", "M15", "M5")
RESAMPLE = {"M10": ("M5", "10min"), "M30": ("M5", "30min"), "M15": ("M5", "15min"), "H4": ("H1", "4h")}


class Frame:
    def __init__(self, tf, raw, detail=True):
        self.tf = tf
        self.raw = raw                                   # includes the forming bar
        closed = raw.iloc[:-1] if len(raw) > 30 else raw
        self.df = add_indicators(closed, intraday=tf not in ("D1", "H4"))
        n = 3 if tf in ("M1", "M5", "M10", "M15") else 2
        self.highs, self.lows = st.swings(self.df, n)
        self.struct = st.market_structure(self.df, self.highs, self.lows)
        self.obs = st.order_blocks(self.df) if (detail and tf in FULL_DETAIL) else []
        self.ts = time.time()

    @property
    def atr(self):
        return float(self.df["atr"].iloc[-1])


def _resample(raw: pd.DataFrame, rule: str, count: int) -> pd.DataFrame | None:
    if raw is None or len(raw) < 8:
        return None
    d = raw.assign(dt=pd.to_datetime(raw["time"], unit="s", utc=True)).set_index("dt")
    r = d.resample(rule).agg({"time": "first", "open": "first", "high": "max", "low": "min",
                              "close": "last", "volume": "sum"}).dropna()
    if len(r) < 8:
        return None
    return r.iloc[-count:].reset_index(drop=True)


class MarketData:
    def __init__(self, broker):
        self.broker = broker
        self.cache = {}
        self.lock = threading.RLock()

    def peek(self, symbol, tf) -> Frame | None:
        """Return a frame already in memory. Does not call MetaTrader."""
        with self.lock:
            return self.cache.get((symbol, tf))

    def _pull(self, symbol, tf):
        raw = self.broker.rates(symbol, tf, COUNT[tf])
        if raw is not None and len(raw) >= MIN_BARS[tf]:
            return raw
        src_tf, rule = RESAMPLE.get(tf, (None, None))
        if src_tf:
            src = self.broker.rates(symbol, src_tf, COUNT.get(src_tf, 300))
            built = _resample(src, rule, COUNT[tf])
            if built is not None and len(built) >= MIN_BARS[tf]:
                return built
        if raw is not None and len(raw) >= 12:
            return raw
        return None

    def frame(self, symbol, tf, force=False) -> Frame | None:
        key = (symbol, tf)
        with self.lock:
            f = self.cache.get(key)
            if f and not force and time.time() - f.ts < TTL[tf]:
                return f
        raw = self._pull(symbol, tf)
        if raw is None:
            return f if "f" in locals() else None
        built = Frame(tf, raw)
        with self.lock:
            self.cache[key] = built
        return built

    def frames(self, symbol):
        """Load every timeframe. Never drop a symbol just because M10 or D1 is thin —
        synthesise what we can so GBPJPY / EURJPY still appear on rankings and charts."""
        out = {}
        for tf in TIMEFRAMES:
            f = self.frame(symbol, tf)
            if f is not None:
                out[tf] = f
        for tf, (src_tf, rule) in RESAMPLE.items():
            if tf in out or src_tf not in out:
                continue
            built = _resample(out[src_tf].raw, rule, COUNT[tf])
            if built is not None and len(built) >= MIN_BARS[tf]:
                out[tf] = Frame(tf, built)
                with self.lock:
                    self.cache[(symbol, tf)] = out[tf]
        if any(tf not in out for tf in CORE_TFS):
            return None
        return out
