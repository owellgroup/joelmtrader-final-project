"""Position sizing, basket sizing & soft account-protection helpers."""
import math


def loss_per_lot(sl_dist: float, info: dict) -> float:
    return sl_dist / info["tick_size"] * info["tick_value"]


def round_volume(vol: float, info: dict) -> float:
    step = info["volume_step"]
    v = math.floor(vol / step + 1e-9) * step
    return round(min(v, info["volume_max"]), 2)


def size_position(equity: float, sl_dist: float, info: dict, cfg):
    """Legacy SL-based sizing (kept for charts / non-scalp paths)."""
    per_lot = loss_per_lot(sl_dist, info)
    if per_lot <= 0:
        return 0.0, 0.0, "invalid stop distance"
    target = equity * cfg.risk_per_trade_pct / 100
    lots = round_volume(target / per_lot, info)
    if lots >= info["volume_min"]:
        return lots, lots * per_lot, ""
    min_risk = info["volume_min"] * per_lot
    if min_risk <= equity * cfg.micro_max_risk_pct / 100:
        return info["volume_min"], min_risk, ""
    return 0.0, min_risk, f"min lot would risk ${min_risk:.2f} ({min_risk / equity * 100:.1f}% > {cfg.micro_max_risk_pct}% cap)"


def size_within_budget(equity: float, sl_dist: float, info: dict, cfg, budget: float):
    lots, risk, why = size_position(equity, sl_dist, info, cfg)
    if lots <= 0:
        return lots, risk, why
    if risk <= budget + 1e-9:
        return lots, risk, ""
    per_lot = loss_per_lot(sl_dist, info)
    fit = round_volume(max(budget, 0.0) / per_lot, info)
    if fit >= info["volume_min"]:
        return fit, fit * per_lot, ""
    min_risk = info["volume_min"] * per_lot
    return 0.0, min_risk, f"not enough risk room: ${max(budget, 0.0):.2f} left, minimum lot needs ${min_risk:.2f}"


def risk_pct_at_min_lot(equity: float, sl_dist: float, info: dict) -> float:
    return info["volume_min"] * loss_per_lot(sl_dist, info) / max(equity, 1e-9) * 100


def lock_floor_r(peak_r: float):
    """Legacy R-multiple lock (unused in scalp basket mode)."""
    if peak_r >= 3.0:
        return peak_r - 0.50
    if peak_r >= 2.2:
        return max(1.60, peak_r * 0.72)
    if peak_r >= 1.6:
        return max(1.10, peak_r * 0.68)
    if peak_r >= 1.15:
        return max(0.70, peak_r * 0.60)
    if peak_r >= 0.80:
        return max(0.15, peak_r * 0.45)
    if peak_r >= 0.55:
        return 0.05
    return None


# ---------------------------------------------------------------- scalping basket
def scalp_lot(info: dict, cfg) -> float:
    """Always 0.01 when the broker allows it; otherwise the broker minimum."""
    want = float(getattr(cfg, "scalp_lot", 0.01) or 0.01)
    step = float(info.get("volume_step") or 0.01)
    vmin = float(info.get("volume_min") or 0.01)
    vmax = float(info.get("volume_max") or 100)
    lot = max(vmin, round(want / step) * step)
    return round(min(lot, vmax), 2)


def basket_trade_count(equity: float, cfg) -> int:
    """How many 0.01 tickets to open from account size.

    Rough guide: about one micro ticket per $20–$25 of equity, floored and capped.
    Tiny accounts still open a small bulk so the basket can bank $1–$2 together.
    """
    per = float(getattr(cfg, "scalp_equity_per_ticket", 22.0) or 22.0)
    mn = int(getattr(cfg, "scalp_min_tickets", 2) or 2)
    mx = int(getattr(cfg, "scalp_max_tickets", 30) or 30)
    n = int(equity / max(per, 1.0))
    return max(mn, min(mx, n if n > 0 else mn))


def basket_profit_target(equity: float, tickets: int, cfg) -> float:
    """Meaningful USD profit before the whole basket is closed.

    At least scalp_min_profit_usd ($1–$2), scaling gently with ticket count and equity
    so a 10-ticket basket does not exit on a tiny blip.
    """
    base = float(getattr(cfg, "scalp_min_profit_usd", 1.5) or 1.5)
    per = float(getattr(cfg, "scalp_profit_per_ticket", 0.12) or 0.12)
    eq_boost = equity * float(getattr(cfg, "scalp_profit_equity_pct", 0.15) or 0.15) / 100.0
    return max(base, tickets * per, eq_boost)


def basket_protect_loss(equity: float, tickets: int, cfg) -> float:
    """Soft emergency: close the whole basket if floating loss reaches this (no broker SL)."""
    pct = float(getattr(cfg, "scalp_protect_pct", 1.8) or 1.8)
    floor = float(getattr(cfg, "scalp_protect_floor_usd", 2.5) or 2.5)
    per = float(getattr(cfg, "scalp_protect_per_ticket", 0.35) or 0.35)
    return max(floor, equity * pct / 100.0, tickets * per)


# Typical broker scalping ceilings in *pips*. Generous enough for retail brokers.
_SCALP_MAX_PIPS = {
    "XAUUSD": 80.0,   # gold often quotes 20–60 points
    "GBPJPY": 6.0,
    "EURJPY": 5.5,
    "EURUSD": 3.0,
    "GBPUSD": 3.5,
}


def pip_size(info: dict, symbol: str = "") -> float:
    """One pip in price units from broker point/digits (and symbol family fallback)."""
    point = float(info.get("point") or info.get("tick_size") or 0)
    digits = int(info.get("digits") or 0)
    if point <= 0:
        if symbol == "XAUUSD":
            return 0.01
        if symbol.endswith("JPY"):
            return 0.01
        return 0.0001
    # 3/5-digit FX: pip = 10 points. Gold 2-digit: pip ≈ point (often 0.01).
    if digits in (3, 5) or (digits == 0 and point in (0.001, 0.00001)):
        return point * 10.0
    if symbol == "XAUUSD" or digits == 2:
        return max(point, 0.01)
    if digits == 4:
        return point * 10.0
    return point * 10.0


def spread_pips(spread: float, info: dict, symbol: str = "") -> float:
    return float(spread) / max(pip_size(info, symbol), 1e-12)


def scalp_spread_ok(symbol: str, spread: float, atr: float, info: dict, cfg,
                    price: float | None = None) -> tuple[bool, str]:
    """Pip-first spread gate. Tiny M5 ATR must NEVER block a normal quote.

    Previous bug: quiet ATR made spread/ATR look huge on every pair (EURUSD, gold, JPY).
    Now we only reject clearly fat pip spreads for that symbol.
    """
    sp = max(float(spread or 0), 0.0)
    if sp <= 0:
        return True, "spread flat / unavailable"
    atr_v = float(atr) if atr and atr == atr else 0.0          # NaN-safe
    pip = pip_size(info, symbol)
    pips = sp / pip
    max_pips = float(_SCALP_MAX_PIPS.get(symbol, 4.0))
    soft_pips = max_pips * 1.45          # retail brokers swing a bit
    hard_pips = max_pips * 2.2           # only this is a hard reject

    # Sanity: if pip_size is wrong, pips explode — fall back to % of mid price
    if pips > 500 and price and price > 0:
        pct = sp / price * 10000.0       # approx "pips" as 0.01% units
        if pct <= soft_pips * 2:
            return True, f"spread {sp:g} (~{pct:.1f} bp) ok for {symbol}"
        if pct > hard_pips * 2:
            return False, f"Spread too wide ({pct:.1f} bp) for {symbol}"
        return True, f"spread {sp:g} accepted for {symbol}"

    # Primary rule: normal pip ceiling always passes (ignore ATR)
    if pips <= soft_pips:
        return True, f"{pips:.1f} pip spread (ok for {symbol})"

    # Extreme pip spread → reject
    if pips > hard_pips:
        return False, f"Spread too wide ({pips:.1f} pips) for {symbol}"

    # Borderline pips: only reject if ATR is *healthy* and spread eats most of it
    atr_pips = atr_v / pip if atr_v > 0 else 0.0
    if atr_pips >= 8 and sp > 0.55 * atr_v:
        return False, f"Spread too wide ({pips:.1f} pips on quiet ATR) for {symbol}"

    return True, f"{pips:.1f} pip spread (accepted for {symbol})"
