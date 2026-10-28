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
