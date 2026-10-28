"""Top-down scoring: Daily sets the side, H4/H1 confirm, M30-M5 locate, M10/M5/M1 trigger."""
import math
import numpy as np

from . import structure as st
from .config import PRIORITY_SYMBOLS
from .risk import (risk_pct_at_min_lot, size_position, loss_per_lot,
                   basket_trade_count, basket_profit_target, scalp_lot, scalp_spread_ok,
                   spread_pips, _SCALP_MAX_PIPS)

# Daily and H4 decide where the market is going. Lower TFs only time the entry.
HTF_W = {"D1": 0.22, "H4": 0.24, "H1": 0.20, "M30": 0.12, "M15": 0.12, "M10": 0.10}
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


def htf_direction(trends, structs, bias=0.0):
    """Pick the market side from Daily → H4 → H1. Returns +1 buy, -1 sell, 0 only if flat."""
    d1, h4, h1 = trends.get("D1", 0.0), trends.get("H4", 0.0), trends.get("H1", 0.0)
    s_d1 = (structs.get("D1") or {}).get("trend", 0)
    s_h4 = (structs.get("H4") or {}).get("trend", 0)
    d1_side = sgn(d1) or sgn(s_d1)
    h4_side = sgn(h4) or sgn(s_h4)
    h1_side = sgn(h1)
    # Clear agreement
    if d1_side and h4_side and d1_side == h4_side:
        return int(d1_side)
    # H4 leads when H1 confirms (common on GBPJPY / GBPUSD when Daily lags)
    if h4_side and (h1_side == h4_side or abs(h4) >= 0.22):
        return int(h4_side)
    if d1_side and abs(d1) >= 0.22:
        return int(d1_side)
    # Weighted bias fallback so the pair is never stuck on WAIT in the ranking table
    if abs(bias) >= 0.08:
        return int(sgn(bias))
    if h4_side:
        return int(h4_side)
    if d1_side:
        return int(d1_side)
    return 0


def build_plan(d, tick, info, atr5, f5, zones, cfg, tight=False, f15=None):
    spread = tick["ask"] - tick["bid"]
    entry = tick["ask"] if d == 1 else tick["bid"]
    mid = (tick["ask"] + tick["bid"]) / 2
    src = f15 if f15 is not None and len(getattr(f15, "df", [])) > 30 else f5
    look = src.lows if d == 1 else src.highs
    swings = [p for i, p in look if i > len(src.df) - 50 and ((p < mid) if d == 1 else (p > mid))]
    if swings:
        anchor = max(swings) if d == 1 else min(swings)
        struct_dist = abs(entry - anchor) + 0.25 * atr5
    else:
        struct_dist = 1.6 * atr5
    min_dist = max(0.85 * atr5, 4 * spread, info.get("stops_level", 0) * info["point"] * 1.3)
    sl_dist = min_dist if tight else clip(struct_dist, min_dist, 2.4 * atr5)
    tp_dist, note = 2.2 * sl_dist, "2.2R default target"
    opp = [z for z in zones if (z["kind"] == "resistance" if d == 1 else z["kind"] == "support")
           and (z["strength"] >= 4.0 or z["touches"] >= 3)]
    nearest = None
    for z in opp:
        gap = (z["low"] - entry) if d == 1 else (entry - z["high"])
        if gap > 0 and (nearest is None or gap < nearest[0]):
            nearest = (gap, z)
    zone_block = False
    if nearest:
        gap = nearest[0] - 0.12 * atr5
        if gap >= 1.4 * sl_dist:
            tp_dist = min(gap, 3.2 * sl_dist)
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
    f10 = c["frames"].get("M10") or f5
    r5, r15, r1 = f5.df.iloc[-1], f15.df.iloc[-1], f1.df.iloc[-1]
    r10 = f10.df.iloc[-1]
    price, atr5 = c["price"], c["atr5"]
    why, pen, comp = [], [], {}
    word = ABBR[d]

    # A. Higher-timeframe alignment (34) — Daily and H4 carry the trade
    align = d * bias
    A = 34 * clip((align + 0.05) / 0.55, 0, 1)
    if align > 0.18:
        why.append(
            f"Top-down {word}: D1 {tr.get('D1', 0):+.2f}, H4 {tr.get('H4', 0):+.2f}, "
            f"H1 {tr.get('H1', 0):+.2f}, M30 {tr.get('M30', 0):+.2f}, M15 {tr.get('M15', 0):+.2f}, "
            f"M10 {tr.get('M10', 0):+.2f}")
    if d * tr.get("D1", 0) > 0.12:
        A += 2
        why.append(f"Daily chart is {word} — trade with the day, not against it")
    if d * tr.get("H4", 0) > 0.12:
        A += 2
    if align < -0.12:
        A -= 18
        pen.append("Counter-trend against Daily/H4/H1 (-18)")
    A = clip(A, -8, 34)
    comp["htf"] = A

    # B. Setup momentum (16) — H1/M15/M10/M5 must travel the same way
    B = 5 * clip(d * tr.get("M5", 0), 0, 1) + 3 * clip(d * tr.get("M10", 0), 0, 1)
    rs = float(r5.rsi)
    # Symmetric windows so sells are not easier than buys just because RSI sits near 50
    if (d == 1 and 42 <= rs <= 68) or (d == -1 and 32 <= rs <= 58):
        B += 3
        why.append(f"M5 RSI {rs:.0f} has room to run")
    elif (d == 1 and rs > 74) or (d == -1 and rs < 26):
        B -= 6
        pen.append(f"M5 RSI {rs:.0f} exhausted (-6)")
    h, hp = float(r5.macd_hist), float(f5.df.macd_hist.iloc[-2])
    if d * h > 0 and d * (h - hp) > 0:
        B += 3
        why.append("M5 MACD momentum accelerating")
    if r15.adx > 18 and d * (r15.pdi - r15.mdi) > 0:
        B += 3
        why.append(f"M15 ADX {r15.adx:.0f} confirms trend strength")
    if d * float(r10.macd_hist) > 0:
        B += 2
    B = clip(B, -6, 16)
    comp["momentum"] = B

    # C. Location (22) — no random mid-range entries
    C, pulled, setup, located = 0.0, False, None, False
    dist = d * (price - r5.ema20) / atr5
    if -1.3 <= dist <= 0.40 and d * (price - r5.ema50) > -0.6 * atr5:
        C += 7
        pulled = located = True
        why.append("Price pulled back to the M5 EMA20/50 value area")
    elif dist > 1.6:
        C -= 8
        pen.append("Price extended away from value - chasing (-8)")
    for z in c["zones"]:
        if ((d == 1 and z["kind"] == "support") or (d == -1 and z["kind"] == "resistance")) and \
                z["low"] - 0.35 * atr5 <= price <= z["high"] + 0.35 * atr5:
            C += 8
            located = True
            why.append(f"At {z['kind']} zone {z['low']:.{c['digits']}f}-{z['high']:.{c['digits']}f} ({'/'.join(z['tfs'])})")
            break
    for ob in c["obs"]:
        if ((d == 1 and ob["type"] == "bullish") or (d == -1 and ob["type"] == "bearish")) and \
                ob["low"] - 0.3 * atr5 <= price <= ob["high"] + 0.3 * atr5:
            C += 6
            located = True
            why.append(f"Inside unmitigated {ob['type']} order block")
            break
    fvg = st.nearest_fvg(c["fvgs"], price, d, atr5)
    if fvg:
        C += 5
        located = True
        why.append(f"Inside unfilled {fvg['type']} fair value gap")
    bo = c["breakout"]
    if bo["retest"] and bo["retest"]["direction"] == d:
        C += 8
        located = True
        setup = "BREAKOUT_RETEST"
        why.append("Valid breakout with successful retest")
    if (d == 1 and price <= r5.bb_lo + 0.18 * atr5) or (d == -1 and price >= r5.bb_up - 0.18 * atr5):
        C += 3
        located = True
        why.append("Price at M5 Bollinger band extreme")
    if d * (price - r5.vwap) > 0:
        C += 2
        why.append("Price on the right side of session VWAP")
    C = clip(C, -10, 22)
    comp["location"] = C

    # D. Trigger (14) — prefer M10/M5 confirmation over a lone M1 wick
    D, trig = 0.0, None
    for name, pdir, strength in c.get("pats10", []):
        if pdir == d and 8 * strength > D:
            D, trig = 8 * strength, f"M10 {name}"
    for name, pdir, strength in c["pats5"]:
        if pdir == d and 7 * strength > D:
            D, trig = 7 * strength, f"M5 {name}"
    for name, pdir, strength in c["pats1"]:
        if pdir == d and 5 * strength > D:
            D, trig = 5 * strength, f"M1 {name}"
    if trig:
        why.append(f"Candlestick trigger: {trig}")
    if d * (r1.close - r1.ema20) > 0 and d * (r1.ema9 - r1.ema20) > 0:
        D += 3
        why.append("M1 EMA9/20 aligned with the trade")
    if d * (r10.close - r10.ema20) > 0:
        D += 2
        why.append("M10 close holds on the trade side of EMA20")
    # Fast scalp timing: M1 + M5 must already be moving with the idea
    if d * float(r1.macd_hist) > 0 and d * float(r5.macd_hist) > 0:
        D += 2
        why.append("M1/M5 MACD both agree — ready for a fast scalp in")
    cl = f1.df["close"].values
    if (d == 1 and cl[-1] > f1.df["high"].values[-6:-1].max()) or (d == -1 and cl[-1] < f1.df["low"].values[-6:-1].min()):
        D += 3
        why.append("M1 micro break of structure")
    # Reject late chases: M1 already extended against a clean pullback entry
    m1_ext = d * (float(r1.close) - float(r1.ema20)) / max(float(r1.atr), 1e-9)
    if m1_ext > 2.2:
        D -= 4
        pen.append("M1 already extended — wait for a tighter scalp entry (-4)")
    fb = bo["false_breakout"]
    if fb and fb["direction"] == d:
        D += 6
        located = True
        setup = "FALSE_BREAKOUT_REVERSAL"
        why.append(f"False breakout: {fb['note']}")
    D = clip(D, 0, 14)
    comp["trigger"] = D

    # E. Regime (9)
    E = 0.0
    if 18 <= r15.adx <= 45:
        E += 5
    elif r15.adx > 45:
        E += 2
    ratio = float(r5.atr / r5.atr_ma) if r5.atr_ma and not np.isnan(r5.atr_ma) else 1.0
    if 0.7 <= ratio <= 1.8:
        E += 4
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
    if v1 > 1.3:
        F += 3
        why.append(f"M1 tick-volume {v1:.1f}x average")
    if float(r5.volume / max(r5.vol_ma, 1)) > 1.2:
        F += 2
    comp["volume"] = F

    if setup is None:
        setup = "TREND_PULLBACK" if pulled else ("ZONE_REVERSAL" if located else "MOMENTUM")
        if setup == "MOMENTUM":
            pen.append("No pullback, zone, order block or FVG (-6)")
            comp["location"] = clip(comp["location"] - 6, -10, 22)
    total = sum(comp.values())
    return total, comp, why, pen, setup, located


def analyze_symbol(symbol, frames, tick, info, zones, cfg, perf, equity, news):
    frames = dict(frames)
    if "M5" not in frames:
        return None
    if "M15" not in frames:
        frames["M15"] = frames["M5"]
    if "M1" not in frames:
        frames["M1"] = frames["M5"]
    if "M10" not in frames:
        frames["M10"] = frames.get("M15") or frames["M5"]
    f5 = frames["M5"]
    f15 = frames.get("M15") or f5
    atr5 = f5.atr
    price = (tick["ask"] + tick["bid"]) / 2
    trends = {tf: tf_trend(fr) for tf, fr in frames.items()}
    bias = sum(w * trends.get(tf, 0.0) for tf, w in HTF_W.items())
    structs = {tf: fr.struct for tf, fr in frames.items()}
    locked = htf_direction(trends, structs, bias)
    obs = []
    for tf in ("M5", "M10", "M15", "H1"):
        if tf in frames:
            obs.extend(frames[tf].obs)
    fvgs = []
    for tf in ("M5", "M10", "M15"):
        if tf in frames:
            fvgs.extend(st.fair_value_gaps(frames[tf].df))
    ctx = dict(frames=frames, trends=trends, bias=bias, price=price, atr5=atr5, zones=zones, obs=obs, fvgs=fvgs,
               pats1=st.candle_patterns(frames["M1"].df) if "M1" in frames else [],
               pats5=st.candle_patterns(f5.df),
               pats10=st.candle_patterns(frames["M10"].df) if "M10" in frames else [],
               breakout=st.breakout_state(f5.df, zones, atr5), digits=info["digits"])

    # Always score BUY and SELL so every pair ranks like the others (never a blank WAIT row).
    scored = []
    for d in (1, -1):
        total, comp, why, pen, setup, located = score_direction(d, ctx)
        # Prefer the HTF side when scores are close
        if locked and d == locked:
            total += 4
        scored.append((total, comp, why, pen, setup, located, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    total, comp, why, pen, setup, located, d = scored[0]
    other = scored[1][0] if len(scored) > 1 else None
    total = clip(total - (4 if locked and d == locked else 0), 0, 100)  # remove ranking nudge from the published score

    wait_for_htf = False
    if locked == 0:
        wait_for_htf = True
        pen.append("Higher timeframes are flat — no clear Daily/H4 direction yet")
    elif locked and d != locked:
        # Keep the HTF side for trading; do not publish a counter-trend idea as the active side
        for row in scored:
            if row[6] == locked:
                total, comp, why, pen, setup, located, d = row
                total = clip(total - 4, 0, 100)
                break
    if other is not None and abs(scored[0][0] - scored[1][0]) < 5 and locked == 0:
        wait_for_htf = True
        pen.append("BUY and SELL scores are too close — no edge")

    plan = build_plan(d, tick, info, atr5, f5, zones, cfg, f15=f15)
    scalp = bool(getattr(cfg, "scalp_mode", True))
    account_fix = None
    if not scalp and symbol in PRIORITY_SYMBOLS:
        _, _, unaffordable = size_position(equity, plan["sl_dist"], info, cfg)
        if unaffordable:
            tight = build_plan(d, tick, info, atr5, f5, zones, cfg, tight=True, f15=f15)
            _, _, still = size_position(equity, tight["sl_dist"], info, cfg)
            if not still and tight["sl_dist"] < plan["sl_dist"]:
                plan = tight
                account_fix = "Small-account fix: stop tightened to the minimum so the smallest lot fits the risk cap"
                why.append(account_fix)
    if plan["zone_block"] and not scalp:
        total -= 8
        pen.append(f"Opposing S/R zone only {plan['tp_dist'] / plan['sl_dist']:.1f}R away (-8)")
    elif plan["zone_block"] and scalp:
        # In scalp mode a nearby wall is fine — we bank $1–$2 and leave; just note it.
        why.append("Nearby opposing S/R — scalp target is basket $ profit, not a far TP")
    adj = perf.adjust(symbol, setup)
    if adj:
        total += adj
        (why if adj > 0 else pen).append(f"Recent {setup} performance adjustment ({adj:+.0f})")
    total = clip(total, 0, 100)

    spread = plan["spread"]
    spread_ratio = spread / max(plan["sl_dist"], 1e-12)
    spread_atr = spread / max(atr5, 1e-12)
    blocked_reasons = []
    news_blocked, news_reason = news.blocked(symbol, cfg)
    if wait_for_htf:
        blocked_reasons.append("Blocked: higher timeframes have not chosen a direction yet")
    if locked and d != locked:
        blocked_reasons.append(f"Blocked: refusing to fade Daily/H4 ({'BUY' if locked == 1 else 'SELL'} market)")
    if d * trends.get("H4", 0) < -0.08 and d * trends.get("H1", 0) < -0.08:
        blocked_reasons.append(
            f"Blocked: H4 {trends.get('H4', 0):+.2f} and H1 {trends.get('H1', 0):+.2f} both oppose this {plan['side']}")
    if d * trends.get("D1", 0) < -0.15 and d * trends.get("H4", 0) < 0:
        blocked_reasons.append(f"Blocked: Daily trend {trends.get('D1', 0):+.2f} is against this {plan['side']}")
    if d * trends.get("M5", 0) < -0.20:
        blocked_reasons.append(f"Blocked: M5 trend {trends.get('M5', 0):+.2f} does not agree with this {plan['side']}")
    if not located and setup == "MOMENTUM":
        blocked_reasons.append("Blocked: no pullback / S/R / order-block / FVG location")
    if news_blocked:
        blocked_reasons.append(news_reason)
    spread_note = ""
    if scalp:
        ok_spread, spread_note = scalp_spread_ok(symbol, spread, atr5, info, cfg, price=price)
        if not ok_spread:
            blocked_reasons.append(spread_note)
    elif spread_ratio > cfg.max_spread_to_sl:
        blocked_reasons.append(f"Spread too wide ({spread_ratio * 100:.0f}% of stop)")
    # Quality gates — calculated scalps only (location + momentum + not chop/exhausted)
    if scalp:
        r5q = frames["M5"].df.iloc[-1]
        r15q = frames["M15"].df.iloc[-1]
        r1q = frames["M1"].df.iloc[-1]
        if not located:
            blocked_reasons.append("Blocked: need pullback / S/R / order-block / FVG (no mid-air scalp)")
        if d * float(r5q.macd_hist) <= 0 or d * float(r1q.macd_hist) <= 0:
            blocked_reasons.append("Blocked: waiting for M1+M5 MACD to agree with the scalp side")
        if float(r15q.adx) < 14:
            blocked_reasons.append(f"Blocked: M15 ADX {float(r15q.adx):.0f} — market too choppy to scalp")
        if (d == 1 and float(r5q.rsi) > 72) or (d == -1 and float(r5q.rsi) < 28):
            blocked_reasons.append(f"Blocked: M5 RSI {float(r5q.rsi):.0f} exhausted for a scalp")
        if abs(d * (price - float(r5q.ema20)) / max(atr5, 1e-12)) > 1.8:
            blocked_reasons.append("Blocked: price too extended from M5 EMA20 — wait for value")
    if comp["trigger"] < 5:
        blocked_reasons.append("Waiting for M10/M5/M1 trigger")
    if setup == "MOMENTUM":
        blocked_reasons.append("Momentum-only chase is not allowed")
    if total < cfg.min_score:
        blocked_reasons.append(f"Score {total:.0f} < {cfg.min_score:.0f}")
    if not scalp and plan["rr"] < cfg.min_rr:
        blocked_reasons.append(f"R:R {plan['rr']:.2f} < {cfg.min_rr}")

    tickets = basket_trade_count(equity, cfg) if scalp else 1
    lot = scalp_lot(info, cfg) if scalp else 0.0
    if scalp:
        lots, risk_amt, why_not = tickets * lot, 0.0, ""
        min_lot_risk = 0.0
        plan = dict(plan)
        plan["sl"] = 0.0
        plan["tp"] = 0.0
        plan["note"] = f"Scalp basket: {tickets}×{lot:g} lots, bank ~${basket_profit_target(equity, tickets, cfg):.2f} then exit"
        plan["basketTickets"] = tickets
        plan["basketLot"] = lot
        plan["basketTarget"] = round(basket_profit_target(equity, tickets, cfg), 2)
        why.append(f"Scalp mode: {tickets}×{lot:g} tickets, no broker SL/TP — soft basket exit")
        if spread_note:
            why.append(spread_note)
    else:
        lots, risk_amt, why_not = size_position(equity, plan["sl_dist"], info, cfg)
        min_lot_risk = info["volume_min"] * loss_per_lot(plan["sl_dist"], info)
        if why_not:
            blocked_reasons.append("Unaffordable: " + why_not)
        if spread_ratio <= cfg.max_spread_to_sl:
            why.append(f"Spread {spread:.{info['digits']}f} is only {spread_ratio * 100:.0f}% of the stop distance")
        why.append(f"R:R {plan['rr']:.2f} ({plan['note']})")

    if symbol not in cfg.allowed_symbols:
        blocked_reasons.append("Symbol disabled in settings")

    # Mild spread ranking only — never bury a good setup because ATR was quiet
    if scalp:
        sp_pips = spread_pips(spread, info, symbol)
        cap = float(_SCALP_MAX_PIPS.get(symbol, 4.0))
        spread_pen = min(sp_pips / max(cap, 1e-9), 1.0) * 0.35
    else:
        spread_pen = min(spread_ratio, 1.0)
    rank_score = total - 20 * spread_pen - (30 if why_not else 0)
    story = (
        f"{plan['side']} scalp from Daily {trends.get('D1', 0):+.2f} / H4 {trends.get('H4', 0):+.2f} / "
        f"H1 {trends.get('H1', 0):+.2f} (HTF lock "
        f"{'BUY' if locked == 1 else 'SELL' if locked == -1 else 'none'}). "
        + (" ".join(why[:3]) if why else "Waiting for location and trigger.")
    )
    return {
        "symbol": symbol, "direction": d, "side": plan["side"], "score": round(total, 1), "rankScore": round(rank_score, 1),
        "setup": setup, "bias": round(bias, 3), "price": f(price, info["digits"]), "spread": f(spread, info["digits"]),
        "plan": {k: (f(v, info["digits"]) if isinstance(v, float) else v) for k, v in plan.items() if k != "zone_block"},
        "rr": round(plan["rr"], 2), "lots": lots, "riskAmount": round(risk_amt, 2),
        "riskPctAtMinLot": round(risk_pct_at_min_lot(equity, plan["sl_dist"], info), 2) if not scalp else 0.0,
        "components": {k: round(v, 1) for k, v in comp.items()}, "reasons": why, "penalties": pen,
        "priority": symbol in PRIORITY_SYMBOLS, "accountFix": account_fix,
        "affordability": {"affordable": True if scalp else not why_not, "minLotRisk": round(min_lot_risk, 2),
                          "riskCap": round(equity * cfg.micro_max_risk_pct / 100, 2),
                          "balanceNeeded": 0 if scalp else round(min_lot_risk / max(cfg.micro_max_risk_pct, 1e-9) * 100, 2),
                          "basketTickets": tickets if scalp else 1, "scalpLot": lot if scalp else None},
        "tradable": len(blocked_reasons) == 0, "blockedReasons": blocked_reasons,
        "timeframes": {tf: tf_summary(fr) for tf, fr in frames.items()},
        "htfLock": {1: "BUY", -1: "SELL", 0: "WAIT"}[locked],
        "story": story, "scalpMode": scalp,
    }
