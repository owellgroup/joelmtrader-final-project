"""Price-action tools: swings, market structure, S/R zones, trendlines, order blocks,
fair value gaps, candlestick patterns, breakouts and false breakouts."""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- swings / structure
def swings(df: pd.DataFrame, n: int = 3):
    h, l = df["high"].values, df["low"].values
    highs, lows = [], []
    for i in range(n, len(df) - n):
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - 1] and h[i] >= h[i + 1]:
            highs.append((i, float(h[i])))
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - 1] and l[i] <= l[i + 1]:
            lows.append((i, float(l[i])))
    return highs, lows


def market_structure(df, highs, lows):
    trend, label = 0, "range"
    if len(highs) >= 2 and len(lows) >= 2:
        hh, hl = highs[-1][1] > highs[-2][1], lows[-1][1] > lows[-2][1]
        lh, ll = highs[-1][1] < highs[-2][1], lows[-1][1] < lows[-2][1]
        if hh and hl:
            trend, label = 1, "uptrend (HH/HL)"
        elif lh and ll:
            trend, label = -1, "downtrend (LH/LL)"
    last = float(df["close"].iloc[-1])
    choch = None
    if trend == 1 and lows and last < lows[-1][1]:
        choch = "bearish CHoCH"
    if trend == -1 and highs and last > highs[-1][1]:
        choch = "bullish CHoCH"
    bos = None
    if highs and last > highs[-1][1] and trend >= 0:
        bos = "bullish BOS"
    if lows and last < lows[-1][1] and trend <= 0:
        bos = "bearish BOS"
    return {"trend": trend, "label": label, "choch": choch, "bos": bos,
            "last_high": highs[-1][1] if highs else None, "last_low": lows[-1][1] if lows else None}


# ---------------------------------------------------------------- zones
def cluster_zones(points, tol, min_width):
    """points: list of (price, weight, tf). Returns merged S/R zones."""
    if not points:
        return []
    pts = sorted(points, key=lambda x: x[0])
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if p[0] - cur[0][0] <= tol:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    zones = []
    for c in clusters:
        prices = [x[0] for x in c]
        lo, hi = min(prices), max(prices)
        if hi - lo < min_width:
            mid = (hi + lo) / 2
            lo, hi = mid - min_width / 2, mid + min_width / 2
        zones.append({"low": lo, "high": hi, "mid": (lo + hi) / 2, "touches": len(c),
                      "strength": round(sum(x[1] for x in c), 2), "tfs": sorted({x[2] for x in c})})
    return zones


def sr_zones(frames: dict, price: float, ref_atr: float, max_each=4):
    """frames: tf -> Frame (with .highs, .lows). Builds multi-timeframe S/R zones."""
    weights = {"D1": 3.0, "H4": 2.5, "H1": 2.0, "M30": 1.5, "M15": 1.0}
    pts = []
    for tf, w in weights.items():
        f = frames.get(tf)
        if not f:
            continue
        for _, p in f.highs[-12:] + f.lows[-12:]:
            pts.append((p, w, tf))
    zones = cluster_zones(pts, tol=ref_atr * 0.6, min_width=ref_atr * 0.25)
    zones = [z for z in zones if z["strength"] >= 3.0 or z["touches"] >= 2]
    for z in zones:
        z["kind"] = "support" if z["mid"] < price else "resistance"
        z["distance"] = abs(z["mid"] - price)
    sup = sorted([z for z in zones if z["kind"] == "support"], key=lambda z: z["distance"])[:max_each]
    res = sorted([z for z in zones if z["kind"] == "resistance"], key=lambda z: z["distance"])[:max_each]
    return sup + res


# ---------------------------------------------------------------- trendlines
def _best_line(points, df, atr_v, kind):
    """A support line rises or stays flat under price. A resistance line falls or stays flat above it.
    Two swings are not enough: the line needs a third touch and must still be near the current price."""
    if atr_v <= 0:
        return None
    n = len(df)
    recent = [p for p in points if p[0] >= n - 140]
    pts = (recent or points)[-8:]
    best, best_score = None, 0
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    last = float(cl[-1])
    for a in range(len(pts)):
        for b in range(a + 1, len(pts)):
            (i1, p1), (i2, p2) = pts[a], pts[b]
            if i2 - i1 < 8:
                continue
            slope = (p2 - p1) / (i2 - i1)
            if abs(slope) > 0.12 * atr_v:
                continue
            if kind == "support" and slope < -0.01 * atr_v:
                continue
            if kind == "resistance" and slope > 0.01 * atr_v:
                continue
            touches, broken = 0, False
            for j in range(i1, n):
                y = p1 + slope * (j - i1)
                if kind == "support":
                    if cl[j] < y - 0.25 * atr_v:
                        broken = True
                        break
                    if abs(lo[j] - y) < 0.30 * atr_v:
                        touches += 1
                else:
                    if cl[j] > y + 0.25 * atr_v:
                        broken = True
                        break
                    if abs(hi[j] - y) < 0.30 * atr_v:
                        touches += 1
            price_now = p1 + slope * (n - 1 - i1)
            if broken or touches < 3 or abs(price_now - last) > 2.5 * atr_v:
                continue
            score = touches * 2 + (i2 / n) * 4 - abs(price_now - last) / atr_v
            if score > best_score:
                best_score = score
                best = {"kind": kind, "i1": i1, "p1": p1, "i2": i2, "p2": p2, "slope": slope, "touches": touches,
                        "price_now": price_now}
    return best


def trendlines(df, highs, lows, atr_v):
    out = []
    for kind, pts in (("support", lows), ("resistance", highs)):
        if len(pts) >= 2:
            line = _best_line(pts, df, atr_v, kind)
            if line:
                out.append(line)
    return out


# ---------------------------------------------------------------- order blocks / FVG
def order_blocks(df: pd.DataFrame, lookback=120, max_out=4):
    d = df.iloc[-lookback:].reset_index()
    o, h, l, c = d["open"].values, d["high"].values, d["low"].values, d["close"].values
    a = d["atr"].values
    out = []
    for i in range(12, len(d)):
        rng = h[i] - l[i]
        if np.isnan(a[i - 1]) or a[i - 1] == 0 or rng < 1.3 * a[i - 1]:
            continue
        prior_high, prior_low = h[i - 10:i].max(), l[i - 10:i].min()
        if c[i] > o[i] and c[i] > prior_high:        # bullish displacement + BOS
            for j in range(i - 1, max(i - 7, 0), -1):
                if c[j] < o[j]:
                    out.append({"type": "bullish", "idx": int(d["index"][j]), "low": float(l[j]), "high": float(h[j])})
                    break
        elif c[i] < o[i] and c[i] < prior_low:       # bearish displacement + BOS
            for j in range(i - 1, max(i - 7, 0), -1):
                if c[j] > o[j]:
                    out.append({"type": "bearish", "idx": int(d["index"][j]), "low": float(l[j]), "high": float(h[j])})
                    break
    last_idx = len(df) - 1
    live = []
    for ob in out:
        after = df["close"].values[ob["idx"] + 2:last_idx + 1]
        mitigated = (len(after) > 0) and ((after.min() < ob["low"]) if ob["type"] == "bullish" else (after.max() > ob["high"]))
        if not mitigated:
            live.append(ob)
    seen, uniq = set(), []
    for ob in reversed(live):
        if ob["idx"] not in seen:
            seen.add(ob["idx"])
            uniq.append(ob)
    return uniq[:max_out]


def fair_value_gaps(df: pd.DataFrame, lookback=100, max_out=3):
    d = df.iloc[-lookback:].reset_index()
    h, l, c = d["high"].values, d["low"].values, d["close"].values
    out = []
    for i in range(2, len(d)):
        if l[i] > h[i - 2]:
            lo, hi, typ = h[i - 2], l[i], "bullish"
            filled = (l[i + 1:].min() <= lo) if i + 1 < len(d) else False
        elif h[i] < l[i - 2]:
            lo, hi, typ = h[i], l[i - 2], "bearish"
            filled = (h[i + 1:].max() >= hi) if i + 1 < len(d) else False
        else:
            continue
        if not filled and (hi - lo) > 0:
            out.append({"type": typ, "idx": int(d["index"][i - 1]), "low": float(lo), "high": float(hi)})
    return out[-max_out:]


# ---------------------------------------------------------------- candlestick patterns
def candle_patterns(df: pd.DataFrame):
    """Patterns on the last closed bars. Returns list of (name, direction(+1/-1), strength 0..1)."""
    if len(df) < 5:
        return []
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    out = []
    i = len(df) - 1
    body = lambda k: abs(c[k] - o[k])
    rng = lambda k: max(h[k] - l[k], 1e-12)
    atr_v = df["atr"].iloc[-1] if "atr" in df else rng(i)
    # engulfing
    if c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body(i) > body(i - 1):
        out.append(("bullish engulfing", 1, min(1.0, 0.6 + body(i) / max(atr_v, 1e-12) * 0.3)))
    if c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body(i) > body(i - 1):
        out.append(("bearish engulfing", -1, min(1.0, 0.6 + body(i) / max(atr_v, 1e-12) * 0.3)))
    # pin bars
    upper, lower = h[i] - max(o[i], c[i]), min(o[i], c[i]) - l[i]
    if lower >= 2 * body(i) and lower >= 0.55 * rng(i) and rng(i) > 0.5 * atr_v:
        out.append(("bullish pin bar", 1, 0.8))
    if upper >= 2 * body(i) and upper >= 0.55 * rng(i) and rng(i) > 0.5 * atr_v:
        out.append(("bearish pin bar", -1, 0.8))
    # stars
    if i >= 2:
        if c[i - 2] < o[i - 2] and body(i - 1) < 0.4 * body(i - 2) and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2:
            out.append(("morning star", 1, 0.85))
        if c[i - 2] > o[i - 2] and body(i - 1) < 0.4 * body(i - 2) and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2:
            out.append(("evening star", -1, 0.85))
    # strong momentum candle (marubozu-like)
    if body(i) > 0.75 * rng(i) and rng(i) > 1.0 * atr_v:
        out.append(("bullish momentum candle" if c[i] > o[i] else "bearish momentum candle", 1 if c[i] > o[i] else -1, 0.6))
    # inside bar breakout
    if h[i - 1] < h[i - 2] and l[i - 1] > l[i - 2]:
        if c[i] > h[i - 1]:
            out.append(("inside bar breakout up", 1, 0.55))
        elif c[i] < l[i - 1]:
            out.append(("inside bar breakout down", -1, 0.55))
    return out


# ---------------------------------------------------------------- breakouts
def breakout_state(df: pd.DataFrame, zones, atr_v):
    """Detect valid breakout+retest and false breakouts (liquidity sweeps) on the last few bars."""
    res = {"breakout": None, "retest": None, "false_breakout": None}
    if len(df) < 15 or atr_v <= 0:
        return res
    c, h, l = df["close"].values, df["high"].values, df["low"].values
    last = len(df) - 1
    for z in zones:
        # false breakout: wick pierced the zone edge but price closed back inside within 3 bars
        if z["kind"] == "resistance":
            pierced = h[last - 3:last + 1].max() > z["high"] + 0.1 * atr_v
            if pierced and c[last] < z["high"] and c[last] < c[last - 1]:
                res["false_breakout"] = {"direction": -1, "zone": z, "note": "sweep above resistance rejected"}
        else:
            pierced = l[last - 3:last + 1].min() < z["low"] - 0.1 * atr_v
            if pierced and c[last] > z["low"] and c[last] > c[last - 1]:
                res["false_breakout"] = {"direction": 1, "zone": z, "note": "sweep below support rejected"}
        # genuine breakout: 2 closes beyond the zone, then retest of its edge
        recent = c[last - 8:last + 1]
        if z["kind"] == "support" and recent.max() < z["low"] - 0.2 * atr_v and (c[last - 8:last - 3] > z["high"]).any():
            res["breakout"] = {"direction": -1, "zone": z}
            if h[last] >= z["low"] - 0.3 * atr_v and c[last] < z["low"]:
                res["retest"] = {"direction": -1, "zone": z}
        if z["kind"] == "resistance" and recent.min() > z["high"] + 0.2 * atr_v and (c[last - 8:last - 3] < z["low"]).any():
            res["breakout"] = {"direction": 1, "zone": z}
            if l[last] <= z["high"] + 0.3 * atr_v and c[last] > z["high"]:
                res["retest"] = {"direction": 1, "zone": z}
    return res
