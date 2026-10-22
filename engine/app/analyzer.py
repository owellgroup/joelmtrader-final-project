"""Multi-timeframe scoring engine: Daily -> H4 -> H1 -> M30 -> M15 -> M5 -> M1 trigger."""
import math
import numpy as np

from . import structure as st
from .config import PRIORITY_SYMBOLS
from .risk import risk_pct_at_min_lot, size_position, loss_per_lot

HTF_W = {"D1": 0.15, "H4": 0.25, "H1": 0.25, "M30": 0.15, "M15": 0.20}
ABBR = {1: "bullish", -1: "bearish"}


def sgn(x): return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)
def clip(x, lo, hi): return max(lo, min(hi, x))
def f(x, nd=5): return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def tf_trend(fr):
    r = fr.df.iloc[-1]
    s = (0.25 * sgn(r.close - r.ema20) + 0.20 * sgn(r.ema20 - r.ema50) + 0.15 * sgn(r.ema50 - r.ema200)
         + 0.15 * sgn(r.macd_hist) + 0.25 * fr.struct["trend"])
    return float(s * clip(r.adx / 30, 0.3, 1.0))


def tf_summary(fr):
    r = fr.df.iloc[-1]
    return {"trend": round(tf_trend(fr), 2), "rsi": round(float(r.rsi), 1), "adx": round(float(r.adx), 1),
            "atr": float(r.atr), "structure": fr.struct["label"], "bos": fr.struct["bos"], "choch": fr.struct["choch"],
            "macd_hist": float(r.macd_hist), "bb_width": f(r.bb_bw, 4)}


def build_plan(d, tick, info, atr5, f5, zones, cfg, tight=False):
    spread = tick["ask"] - tick["bid"]
    entry = tick["ask"] if d == 1 else tick["bid"]
    mid = (tick["ask"] + tick["bid"]) / 2
    lows = [p for i, p in f5.lows if i > len(f5.df) - 40 and p < mid] if d == 1 else \
           [p for i, p in f5.highs if i > len(f5.df) - 40 and p > mid]
    if lows:
        anchor = max(lows) if d == 1 else min(lows)           # nearest protective swing
        struct_dist = abs(entry - anchor) + 0.3 * atr5
    else:
        struct_dist = 1.5 * atr5
    min_dist = max(0.8 * atr5, 4 * spread, info.get("stops_level", 0) * info["point"] * 1.3)
    sl_dist = min_dist if tight else clip(struct_dist, min_dist, 2.0 * atr5)
    tp_dist, note = 2.0 * sl_dist, "2R default target"
    opp = [z for z in zones if (z["kind"] == "resistance" if d == 1 else z["kind"] == "support")
           and (z["strength"] >= 4.5 or z["touches"] >= 3)]          # only meaningful zones cap the target
    nearest = None
    for z in opp:
        gap = (z["low"] - entry) if d == 1 else (entry - z["high"])
        if gap > 0 and (nearest is None or gap < nearest[0]):
            nearest = (gap, z)
    zone_block = False
    if nearest:
        gap = nearest[0] - 0.1 * atr5
        if gap >= 1.3 * sl_dist:
            tp_dist = min(gap, 3.0 * sl_dist)
            note = "target before opposing S/R zone"
        else:
            tp_dist, zone_block = max(gap, 0.1 * atr5), True
            note = "opposing S/R zone too close"
    sl = entry - d * sl_dist
    tp = entry + d * tp_dist
    nd = info["digits"]
    rr = (tp_dist - spread / 2) / (sl_dist + spread / 2)
    return {"direction": d, "side": "BUY" if d == 1 else "SELL", "entry": round(entry, nd), "sl": round(sl, nd),
            "tp": round(tp, nd), "sl_dist": sl_dist, "tp_dist": tp_dist, "rr": rr, "note": note,
            "zone_block": zone_block, "spread": spread}


def score_direction(d, c):
    bias, tr = c["bias"], c["trends"]
    f5, f15, f1 = c["frames"]["M5"], c["frames"]["M15"], c["frames"]["M1"]
    r5, r15, r1 = f5.df.iloc[-1], f15.df.iloc[-1], f1.df.iloc[-1]
    price, atr5 = c["price"], c["atr5"]
    why, pen, comp = [], [], {}
    word = ABBR[d]

    # A. Higher-timeframe alignment (30)
    align = d * bias
    A = 30 * clip((align + 0.1) / 0.6, 0, 1)
    if align > 0.2:
        why.append(f"Top-down bias {word}: D1 {tr['D1']:+.2f}, H4 {tr['H4']:+.2f}, H1 {tr['H1']:+.2f}, M30 {tr['M30']:+.2f}, M15 {tr['M15']:+.2f}")
    if align < -0.25:
        A -= 12
        pen.append("Counter-trend against higher timeframes (-12)")
    comp["htf"] = A

    # B. Setup momentum (20)
    B = 8 * clip(d * tr["M5"], 0, 1)
    rs = float(r5.rsi)
    if (d == 1 and 45 <= rs <= 68) or (d == -1 and 32 <= rs <= 55):
        B += 4
        why.append(f"M5 RSI {rs:.0f} has room to run")
    elif (d == 1 and rs > 75) or (d == -1 and rs < 25):
        B -= 6
        pen.append(f"M5 RSI {rs:.0f} exhausted (-6)")
    h, hp = float(r5.macd_hist), float(f5.df.macd_hist.iloc[-2])
    if d * h > 0 and d * (h - hp) > 0:
        B += 4
        why.append("M5 MACD momentum accelerating")
    if r15.adx > 20 and d * (r15.pdi - r15.mdi) > 0:
        B += 4
        why.append(f"M15 ADX {r15.adx:.0f} confirms trend strength")
    comp["momentum"] = B

    # C. Location (20)
    C, pulled, setup = 0.0, False, None
    dist = d * (price - r5.ema20) / atr5
    if -1.2 <= dist <= 0.35 and d * (price - r5.ema50) > -0.5 * atr5:
        C += 6
        pulled = True
        why.append("Price pulled back to the M5 EMA20/50 value area")
    elif dist > 1.5:
        C -= 6
        pen.append("Price extended away from value - chasing (-6)")
    for z in c["zones"]:
        if ((d == 1 and z["kind"] == "support") or (d == -1 and z["kind"] == "resistance")) and \
                z["low"] - 0.3 * atr5 <= price <= z["high"] + 0.3 * atr5:
            C += 8
            why.append(f"At {z['kind']} zone {z['low']:.{c['digits']}f}-{z['high']:.{c['digits']}f} ({'/'.join(z['tfs'])})")
            break
    for ob in c["obs"]:
        if ((d == 1 and ob["type"] == "bullish") or (d == -1 and ob["type"] == "bearish")) and \
                ob["low"] - 0.3 * atr5 <= price <= ob["high"] + 0.3 * atr5:
            C += 6
            why.append(f"Inside unmitigated {ob['type']} order block")
            break
    bo = c["breakout"]
    if bo["retest"] and bo["retest"]["direction"] == d:
        C += 8
        setup = "BREAKOUT_RETEST"
        why.append("Valid breakout with successful retest")
    if (d == 1 and price <= r5.bb_lo + 0.15 * atr5) or (d == -1 and price >= r5.bb_up - 0.15 * atr5):
        C += 3
        why.append("Price at M5 Bollinger band extreme")
    if d * (price - r5.vwap) > 0:
        C += 3
        why.append("Price on the right side of session VWAP")
    C = clip(C, -10, 20)
    comp["location"] = C

    # D. M1 trigger (15)
    D, trig = 0.0, None
    for name, pdir, strength in c["pats1"]:
        if pdir == d and 8 * strength > D:
            D, trig = 8 * strength, f"M1 {name}"
    for name, pdir, strength in c["pats5"]:
        if pdir == d and 6 * strength > D:
            D, trig = 6 * strength, f"M5 {name}"
    if trig:
        why.append(f"Candlestick trigger: {trig}")
    if d * (r1.close - r1.ema20) > 0 and d * (r1.ema9 - r1.ema20) > 0:
        D += 3
        why.append("M1 EMA9/20 aligned with the trade")
    cl = f1.df["close"].values
    if (d == 1 and cl[-1] > f1.df["high"].values[-6:-1].max()) or (d == -1 and cl[-1] < f1.df["low"].values[-6:-1].min()):
        D += 4
        why.append("M1 micro break of structure")
    fb = bo["false_breakout"]
    if fb and fb["direction"] == d:
        D += 6
        setup = "FALSE_BREAKOUT_REVERSAL"
        why.append(f"False breakout: {fb['note']}")
    D = clip(D, 0, 15)
    comp["trigger"] = D

    # E. Regime (10)
    E = 0.0
    if 18 <= r15.adx <= 45: E += 5
    elif r15.adx > 45: E += 2
    ratio = float(r5.atr / r5.atr_ma) if r5.atr_ma and not np.isnan(r5.atr_ma) else 1.0
    if 0.7 <= ratio <= 1.8: E += 5
    elif ratio > 2.5:
        E -= 8
        pen.append("Volatility spike - unstable conditions (-8)")
    elif ratio < 0.5:
        E -= 6
        pen.append("Dead market - volatility too low (-6)")
    comp["regime"] = E

    # F. Volume (5)
    F = 0.0
    v1 = float(f1.df.volume.iloc[-3:].mean() / max(r1.vol_ma, 1))
    if v1 > 1.3: F += 3; why.append(f"M1 tick-volume {v1:.1f}x average")
    if float(r5.volume / max(r5.vol_ma, 1)) > 1.2: F += 2
    comp["volume"] = F

    if setup is None:
        setup = "TREND_PULLBACK" if pulled else "MOMENTUM"
        if setup == "MOMENTUM":
            pen.append("No pullback/zone confluence (-4)")
            comp["location"] -= 4
    total = sum(comp.values())
    return total, comp, why, pen, setup


def analyze_symbol(symbol, frames, tick, info, zones, cfg, perf, equity, news):
    f5 = frames["M5"]
    atr5 = f5.atr
    price = (tick["ask"] + tick["bid"]) / 2
    trends = {tf: tf_trend(fr) for tf, fr in frames.items()}
    bias = sum(w * trends[tf] for tf, w in HTF_W.items())
    obs = frames["M5"].obs + frames["M15"].obs + frames["H1"].obs
    ctx = dict(frames=frames, trends=trends, bias=bias, price=price, atr5=atr5, zones=zones, obs=obs,
               pats1=st.candle_patterns(frames["M1"].df), pats5=st.candle_patterns(frames["M5"].df),
               breakout=st.breakout_state(f5.df, zones, atr5), digits=info["digits"])
    best = None
    for d in (1, -1):
        total, comp, why, pen, setup = score_direction(d, ctx)
        if best is None or total > best[0]:
            best = (total, comp, why, pen, setup, d)
    total, comp, why, pen, setup, d = best

    plan = build_plan(d, tick, info, atr5, f5, zones, cfg)
    account_fix = None
    if symbol in PRIORITY_SYMBOLS:
        # Priority symbol that the account cannot afford with the normal stop: try the tightest allowed
        # stop (0.8 x ATR, never below the broker/spread minimum) so the minimum lot fits the risk cap.
        _, _, unaffordable = size_position(equity, plan["sl_dist"], info, cfg)
        if unaffordable:
            tight = build_plan(d, tick, info, atr5, f5, zones, cfg, tight=True)
            _, _, still = size_position(equity, tight["sl_dist"], info, cfg)
            if not still and tight["sl_dist"] < plan["sl_dist"]:
                plan = tight
                account_fix = "Small-account fix: stop tightened to the minimum so the smallest lot fits the risk cap"
                why.append(account_fix)
    if plan["zone_block"]:
        total -= 8
        pen.append(f"Opposing S/R zone only {plan['tp_dist'] / plan['sl_dist']:.1f}R away (-8)")
    adj = perf.adjust(symbol, setup)
    if adj:
        total += adj
        (why if adj > 0 else pen).append(f"Recent {setup} performance adjustment ({adj:+.0f})")
    total = clip(total, 0, 100)

    spread = plan["spread"]
    spread_ratio = spread / plan["sl_dist"]
    blocked_reasons = []
    news_blocked, news_reason = news.blocked(symbol, cfg)
    if news_blocked: blocked_reasons.append(news_reason)
    if spread_ratio > cfg.max_spread_to_sl: blocked_reasons.append(f"Spread too wide ({spread_ratio * 100:.0f}% of stop)")
    if comp["trigger"] < 4: blocked_reasons.append("Waiting for M1 trigger")
    if setup == "MOMENTUM" and total < cfg.min_score + 8:
        blocked_reasons.append(f"Momentum-only setup needs score >= {cfg.min_score + 8:.0f}")
    if total < cfg.min_score: blocked_reasons.append(f"Score {total:.0f} < {cfg.min_score:.0f}")
    if plan["rr"] < cfg.min_rr: blocked_reasons.append(f"R:R {plan['rr']:.2f} < {cfg.min_rr}")
    lots, risk_amt, why_not = size_position(equity, plan["sl_dist"], info, cfg)
    min_lot_risk = info["volume_min"] * loss_per_lot(plan["sl_dist"], info)
    if why_not: blocked_reasons.append("Unaffordable: " + why_not)
    if symbol not in cfg.allowed_symbols: blocked_reasons.append("Symbol disabled in settings")
    if spread_ratio <= cfg.max_spread_to_sl:
        why.append(f"Spread {spread:.{info['digits']}f} is only {spread_ratio * 100:.0f}% of the stop distance")
    why.append(f"R:R {plan['rr']:.2f} ({plan['note']})")

    rank_score = total - 20 * min(spread_ratio, 1.0) - (30 if why_not else 0)
    return {
        "symbol": symbol, "direction": d, "side": plan["side"], "score": round(total, 1), "rankScore": round(rank_score, 1),
        "setup": setup, "bias": round(bias, 3), "price": f(price, info["digits"]), "spread": f(spread, info["digits"]),
        "plan": {k: (f(v, info["digits"]) if isinstance(v, float) else v) for k, v in plan.items() if k != "zone_block"},
        "rr": round(plan["rr"], 2), "lots": lots, "riskAmount": round(risk_amt, 2),
        "riskPctAtMinLot": round(risk_pct_at_min_lot(equity, plan["sl_dist"], info), 2),
        "components": {k: round(v, 1) for k, v in comp.items()}, "reasons": why, "penalties": pen,
        "priority": symbol in PRIORITY_SYMBOLS, "accountFix": account_fix,
        "affordability": {"affordable": not why_not, "minLotRisk": round(min_lot_risk, 2),
                          "riskCap": round(equity * cfg.micro_max_risk_pct / 100, 2),
                          "balanceNeeded": round(min_lot_risk / max(cfg.micro_max_risk_pct, 1e-9) * 100, 2)},
        "tradable": len(blocked_reasons) == 0, "blockedReasons": blocked_reasons,
        "timeframes": {tf: tf_summary(fr) for tf, fr in frames.items()},
    }
