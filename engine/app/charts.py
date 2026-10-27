"""Builds chart payloads (candles + indicators + drawn analysis objects) for the Flutter app.

Overlays are anchored to the *selected* timeframe's candle times (and visible indices),
so D1 / H4 / H1 charts do not drift the way fixed tfSeconds math does across gaps.
"""
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


def _idx_in_window(df_i, off, n_vis):
    """Map a dataframe index onto the visible candle array (0 .. n_vis-1), or None."""
    vis = int(df_i) - int(off)
    if vis < 0 or vis >= n_vis:
        return None
    return vis


def _chart_payload(symbol, tf, bars, md, broker, scan_data):
    # Refresh the selected TF so switching H1→D1 always paints that TF's own structure.
    fr = md.frame(symbol, tf, force=True)
    frames = md.frames(symbol) or {}
    if fr is None and frames:
        fr = frames.get(tf)
    if fr is not None and frames.get(tf) is None:
        frames[tf] = fr
    try:
        info = broker.symbol_info(symbol)
    except Exception as e:                                  # noqa: BLE001
        return _empty_payload(symbol, tf, error=f"{symbol} is not mapped on this broker yet ({e})")
    nd = info["digits"]
    if fr is None or fr.df is None or len(fr.df) < 8:
        return _empty_payload(symbol, tf, nd, f"Waiting for {symbol} {tf} candles from MT5")

    df, raw = fr.df, fr.raw
    # Visible window: last k closed bars + the forming bar → k+1 candles.
    k = min(max(bars, 40), len(df))
    off = len(df) - k                                       # first closed-bar index in the window
    closed_tail = df.iloc[-k:]
    candle_rows = raw.iloc[-(k + 1):] if len(raw) >= k + 1 else raw
    candles = [[int(r.time), _clean(r.open, nd), _clean(r.high, nd), _clean(r.low, nd),
                _clean(r.close, nd), int(getattr(r, "volume", 0) or 0)]
               for r in candle_rows.itertuples()]
    n_vis = len(candles)                                    # usually k+1 (closed + forming)

    # Indicators align 1:1 with candles: k closed values + trailing None for the forming bar.
    def series(col, places=nd):
        vals = [_clean(v, places) for v in closed_tail[col].tolist()]
        while len(vals) < n_vis:
            vals.append(None)
        return vals[:n_vis]

    ind = {name: series(col) for name, col in
           (("ema9", "ema9"), ("ema20", "ema20"), ("ema50", "ema50"), ("ema200", "ema200"),
            ("bbUp", "bb_up"), ("bbLo", "bb_lo"), ("vwap", "vwap"))}
    ind["rsi"] = series("rsi", 1)
    ind["macd"] = series("macd_hist")
    ind["stoch"] = series("stoch_k", 1)
    ind["adx"] = series("adx", 1)

    atr_v = fr.atr
    tick = broker.tick(symbol) or {}
    bid, ask = tick.get("bid"), tick.get("ask")
    price = ((ask + bid) / 2) if bid and ask else float(df["close"].iloc[-1])
    ref_atr = (frames.get("H1") or fr).atr
    zones = st.sr_zones(frames, price, ref_atr) if frames else []

    def t_at(df_i):
        return int(df["time"].iloc[min(max(int(df_i), 0), len(df) - 1)])

    def pack_time(df_i, *, clamp=False):
        """Time + visible index so the painter never relies on uniform bar spacing."""
        closed_slots = max(n_vis - 1, 1)                   # forming candle is last; overlays sit on closed bars
        vis = _idx_in_window(df_i, off, closed_slots)
        if vis is None:
            if not clamp:
                return None
            vis = 0 if int(df_i) < off else (n_vis - 2 if n_vis > 1 else 0)
        return int(t_at(df_i)), int(vis)

    tls = []
    for tl in st.trendlines(df, fr.highs, fr.lows, atr_v):
        packed = pack_time(tl["i1"], clamp=True)           # allow start off-screen; line still extends into view
        if packed is None:
            continue
        t1, i1 = packed
        t2 = int(df["time"].iloc[-1])
        i2 = n_vis - 2 if n_vis > 1 else 0
        tls.append({"kind": tl["kind"], "t1": t1, "i1": i1, "p1": _clean(tl["p1"], nd),
                    "t2": t2, "i2": i2, "p2": _clean(tl["price_now"], nd), "touches": tl["touches"]})

    obs = []
    if tf != "D1":
        for o in st.order_blocks(df):
            packed = pack_time(o["idx"])
            if packed is None:
                continue
            t, ii = packed
            obs.append({"type": o["type"], "t": t, "i": ii,
                        "low": _clean(o["low"], nd), "high": _clean(o["high"], nd)})

    fvgs = []
    for g in st.fair_value_gaps(df):
        packed = pack_time(g["idx"])
        if packed is None:
            continue
        t, ii = packed
        fvgs.append({"type": g["type"], "t": t, "i": ii,
                     "low": _clean(g["low"], nd), "high": _clean(g["high"], nd)})

    swings = []
    for i_df, p in fr.highs:
        packed = pack_time(i_df)
        if packed is None:
            continue
        t, ii = packed
        swings.append({"t": t, "i": ii, "p": _clean(p, nd), "kind": "high"})
    for i_df, p in fr.lows:
        packed = pack_time(i_df)
        if packed is None:
            continue
        t, ii = packed
        swings.append({"t": t, "i": ii, "p": _clean(p, nd), "kind": "low"})

    # Breakouts / structure markers for the *selected* timeframe (not always M5).
    bo = st.breakout_state(df, zones, atr_v)
    last_t = int(candles[-1][0])
    last_p = candles[-1][4]
    last_i = n_vis - 1
    markers = []
    if bo.get("false_breakout"):
        markers.append({"label": "False breakout " + ("↑" if bo["false_breakout"]["direction"] == 1 else "↓"),
                        "t": last_t, "i": last_i, "p": last_p})
    if bo.get("retest"):
        markers.append({"label": "Breakout retest", "t": last_t, "i": last_i, "p": last_p})
    if fr.struct.get("bos"):
        markers.append({"label": fr.struct["bos"], "t": last_t, "i": last_i, "p": last_p})
    if fr.struct.get("choch"):
        markers.append({"label": fr.struct["choch"], "t": last_t, "i": last_i, "p": last_p})

    d1 = frames.get("D1") or fr
    pivots = [{"label": pv["label"], "price": _clean(pv["price"], nd), "kind": pv["kind"]}
              for pv in st.classic_pivots(d1.df)]

    # Session levels: use an intraday frame when available; on D1/H4 still show today's range from M15/M5.
    sess_src = frames.get("M15") or frames.get("M5") or fr
    sessions = []
    for sl in st.session_levels(sess_src.df):
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
    tools = [f"Chart TF {tf}: {fr.struct.get('label') or 'range'}"]
    for name in TIMEFRAMES:
        item = frames.get(name)
        if item is None:
            continue
        stack[name] = {"trend": round(float(item.struct.get("trend") or 0), 2),
                       "label": item.struct.get("label"), "adx": _clean(item.df["adx"].iloc[-1], 1),
                       "rsi": _clean(item.df["rsi"].iloc[-1], 1)}
        if name != tf and item.struct.get("label") and item.struct["label"] != "range":
            tools.append(f"{name}: {item.struct['label']}")
    if zones:
        tools.append(f"{len(zones)} multi-TF S/R zones")
    if obs:
        tools.append(f"{len(obs)} {tf} order blocks")
    if fvgs:
        tools.append(f"{len(fvgs)} {tf} fair value gaps")
    if tls:
        tools.append(f"{len(tls)} {tf} trendlines")
    if liquidity:
        tools.append(f"{len(liquidity)} equal-high / equal-low pools")
    if sessions:
        tools.append("Asia / London / New York session levels")
    if pivots:
        tools.append("Classic daily pivots (P, S1/S2, R1/R2)")

    story = (rank or {}).get("story") or (scan_data or {}).get("why") or f"{symbol} {tf} structure and indicators."
    htf_lock = (rank or {}).get("htfLock") or "WAIT"
    # Median bar duration from the visible window — painter uses this only as a fallback.
    if n_vis >= 3:
        gaps = sorted(max(1, int(candles[i][0]) - int(candles[i - 1][0])) for i in range(1, n_vis))
        bar_sec = gaps[len(gaps) // 2]
    else:
        bar_sec = TF_SECONDS.get(tf, 300)

    return {"symbol": symbol, "tf": tf, "tfSeconds": int(bar_sec), "digits": nd, "candles": candles,
            "indicators": ind,
            "zones": [{"low": _clean(z["low"], nd), "high": _clean(z["high"], nd), "kind": z["kind"],
                       "strength": z["strength"], "touches": z["touches"], "tfs": z["tfs"]} for z in zones],
            "trendlines": tls, "orderBlocks": obs, "fvgs": fvgs, "swings": swings, "markers": markers,
            "pivots": pivots, "sessions": sessions, "liquidity": liquidity,
            "structure": {"label": fr.struct["label"], "bos": fr.struct["bos"], "choch": fr.struct["choch"]},
            "plan": plan, "positions": positions, "bid": bid, "ask": ask,
            "analysis": {"bias": (rank or {}).get("side") or htf_lock, "htfLock": htf_lock, "story": story,
                         "stack": stack, "tools": tools, "chartTf": tf},
            "error": None}
