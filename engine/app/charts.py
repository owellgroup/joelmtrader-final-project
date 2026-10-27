"""Builds chart payloads (candles + indicators + drawn analysis objects) for the Flutter app."""
import math

from . import structure as st
from .config import TF_SECONDS, TIMEFRAMES


def _clean(x, nd=5):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def _empty_payload(symbol, tf, nd=5, error="Waiting for market data from MT5"):
    return {
        "symbol": symbol, "tf": tf, "tfSeconds": TF_SECONDS.get(tf, 300), "digits": nd,
        "candles": [], "indicators": {}, "zones": [], "trendlines": [], "orderBlocks": [],
        "fvgs": [], "swings": [], "markers": [], "pivots": [], "sessions": [], "liquidity": [],
        "structure": {"label": "waiting", "bos": None, "choch": None},
        "plan": None, "positions": [], "bid": None, "ask": None,
        "analysis": {"bias": "WAIT", "htfLock": "WAIT", "story": error, "stack": {}, "tools": []},
        "error": error,
    }


def chart_payload(symbol, tf, bars, md, broker, scan_data):
    try:
        return _chart_payload(symbol, tf, bars, md, broker, scan_data)
    except Exception as e:                                  # noqa: BLE001
        return _empty_payload(symbol, tf, error=f"Chart for {symbol} is loading ({e})")


def _chart_payload(symbol, tf, bars, md, broker, scan_data):
    fr = md.frame(symbol, tf)
    frames = md.frames(symbol) or {}
    if fr is None and frames:
        fr = frames.get(tf) or next(iter(frames.values()), None)
    try:
        info = broker.symbol_info(symbol)
    except Exception as e:                                  # noqa: BLE001
        return _empty_payload(symbol, tf, error=f"{symbol} is not mapped on this broker yet ({e})")
    nd = info["digits"]
    if fr is None or fr.df is None or len(fr.df) < 8:
        return _empty_payload(symbol, tf, nd, f"Waiting for {symbol} {tf} candles from MT5")
    df, raw = fr.df, fr.raw
    k = min(bars, len(df))
    tail = df.iloc[-k:]
    off = len(df) - k
    candles = [[int(r.time), _clean(r.open, nd), _clean(r.high, nd), _clean(r.low, nd), _clean(r.close, nd), int(r.volume)]
               for r in raw.iloc[-(k + 1):].itertuples()]
    ind = {name: [_clean(v, nd) for v in tail[col].tolist()] + [None] for name, col in
           (("ema9", "ema9"), ("ema20", "ema20"), ("ema50", "ema50"), ("ema200", "ema200"),
            ("bbUp", "bb_up"), ("bbLo", "bb_lo"), ("vwap", "vwap"))}
    ind["rsi"] = [_clean(v, 1) for v in tail["rsi"].tolist()] + [None]
    ind["macd"] = [_clean(v, nd) for v in tail["macd_hist"].tolist()] + [None]
    ind["stoch"] = [_clean(v, 1) for v in tail["stoch_k"].tolist()] + [None]
    ind["adx"] = [_clean(v, 1) for v in tail["adx"].tolist()] + [None]
    atr_v = fr.atr
    tick = broker.tick(symbol) or {}
    bid, ask = tick.get("bid"), tick.get("ask")
    price = ((ask + bid) / 2) if bid and ask else float(df["close"].iloc[-1])
    zones = st.sr_zones(frames, price, (frames.get("H1") or fr).atr) if frames else []
    t_at = lambda i: int(df["time"].iloc[min(max(i, 0), len(df) - 1)])
    tls = []
    for tl in st.trendlines(df, fr.highs, fr.lows, atr_v):
        tls.append({"kind": tl["kind"], "t1": t_at(tl["i1"]), "p1": _clean(tl["p1"], nd), "t2": int(df["time"].iloc[-1]),
                    "p2": _clean(tl["price_now"], nd), "touches": tl["touches"]})
    obs = [{"type": o["type"], "t": t_at(o["idx"]), "low": _clean(o["low"], nd), "high": _clean(o["high"], nd)}
           for o in (st.order_blocks(df) if tf != "D1" else [])]
    fvgs = [{"type": g["type"], "t": t_at(g["idx"]), "low": _clean(g["low"], nd), "high": _clean(g["high"], nd)}
            for g in st.fair_value_gaps(df)]
    swings = [{"t": t_at(i), "p": _clean(p, nd), "kind": "high"} for i, p in fr.highs if i >= off] + \
             [{"t": t_at(i), "p": _clean(p, nd), "kind": "low"} for i, p in fr.lows if i >= off]
    src5 = frames.get("M5") or fr
    bo = st.breakout_state(src5.df, zones, src5.atr)
    markers = []
    if bo["false_breakout"]:
        markers.append({"label": "False breakout " + ("↑" if bo["false_breakout"]["direction"] == 1 else "↓"),
                        "t": int(candles[-1][0]), "p": candles[-1][4]})
    if bo["retest"]:
        markers.append({"label": "Breakout retest", "t": int(candles[-1][0]), "p": candles[-1][4]})
    if fr.struct.get("bos"):
        markers.append({"label": fr.struct["bos"], "t": int(candles[-1][0]), "p": candles[-1][4]})
    if fr.struct.get("choch"):
        markers.append({"label": fr.struct["choch"], "t": int(candles[-1][0]), "p": candles[-1][4]})
    d1 = frames.get("D1") or fr
    pivots = [{"label": pv["label"], "price": _clean(pv["price"], nd), "kind": pv["kind"]}
              for pv in st.classic_pivots(d1.df)]
    sessions = []
    for sl in st.session_levels(frames.get("M15").df if frames.get("M15") is not None else df):
        sessions.append({"session": sl["session"], "high": _clean(sl["high"], nd), "low": _clean(sl["low"], nd)})
    liquidity = [{"kind": eq["kind"], "price": _clean(eq["price"], nd), "touches": eq["touches"]}
                 for eq in st.equal_swings(fr.highs, fr.lows, atr_v)]
    plan, rank = None, None
    if scan_data:
        rank = next((r for r in scan_data.get("rankings") or [] if r.get("symbol") == symbol), None)
        raw_plan = (rank or {}).get("plan")
        if rank and isinstance(raw_plan, dict):
            plan = {"side": rank.get("side"), "entry": raw_plan.get("entry"), "sl": raw_plan.get("sl"),
                    "tp": raw_plan.get("tp"), "rr": rank.get("rr"), "score": rank.get("score"),
                    "tradable": rank.get("tradable")}
    positions = [{"side": p["side"], "entry": p["price_open"], "sl": p["sl"], "tp": p["tp"],
                  "profit": p["profit"], "ticket": p["ticket"]}
                 for p in broker.positions() if p.get("symbol") == symbol]
    stack = {}
    tools = []
    for name in TIMEFRAMES:
        item = frames.get(name)
        if item is None:
            continue
        stack[name] = {"trend": round(float(item.struct.get("trend") or 0), 2),
                       "label": item.struct.get("label"), "adx": _clean(item.df["adx"].iloc[-1], 1),
                       "rsi": _clean(item.df["rsi"].iloc[-1], 1)}
        if item.struct.get("label") and item.struct["label"] != "range":
            tools.append(f"{name}: {item.struct['label']}")
    if zones:
        tools.append(f"{len(zones)} multi-TF S/R zones")
    if obs:
        tools.append(f"{len(obs)} unmitigated order blocks")
    if fvgs:
        tools.append(f"{len(fvgs)} open fair value gaps")
    if tls:
        tools.append(f"{len(tls)} active trendlines")
    if liquidity:
        tools.append(f"{len(liquidity)} equal-high / equal-low liquidity pools")
    if sessions:
        tools.append("Asia / London / New York session levels")
    if pivots:
        tools.append("Classic daily pivots (P, S1/S2, R1/R2)")
    story = (rank or {}).get("story") or (scan_data or {}).get("why") or "Scanning this pair from Daily down to M1."
    htf_lock = (rank or {}).get("htfLock") or "WAIT"
    return {"symbol": symbol, "tf": tf, "tfSeconds": TF_SECONDS.get(tf, 300), "digits": nd, "candles": candles,
            "indicators": ind,
            "zones": [{"low": _clean(z["low"], nd), "high": _clean(z["high"], nd), "kind": z["kind"],
                       "strength": z["strength"], "touches": z["touches"], "tfs": z["tfs"]} for z in zones],
            "trendlines": tls, "orderBlocks": obs, "fvgs": fvgs, "swings": swings, "markers": markers,
            "pivots": pivots, "sessions": sessions, "liquidity": liquidity,
            "structure": {"label": fr.struct["label"], "bos": fr.struct["bos"], "choch": fr.struct["choch"]},
            "plan": plan, "positions": positions, "bid": bid, "ask": ask,
            "analysis": {"bias": (rank or {}).get("side") or htf_lock, "htfLock": htf_lock, "story": story,
                         "stack": stack, "tools": tools},
            "error": None}
