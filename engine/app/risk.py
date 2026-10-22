"""Position sizing & risk helpers."""
import math


def loss_per_lot(sl_dist: float, info: dict) -> float:
    return sl_dist / info["tick_size"] * info["tick_value"]


def round_volume(vol: float, info: dict) -> float:
    step = info["volume_step"]
    v = math.floor(vol / step + 1e-9) * step
    return round(min(v, info["volume_max"]), 2)


def size_position(equity: float, sl_dist: float, info: dict, cfg):
    """Returns (lots, risk_amount, reject_reason).
    Normal case: lots = risk$ / loss-per-lot, rounded DOWN to the lot step.
    Micro accounts: if the broker minimum lot already risks more than the target, accept it only when the
    resulting risk is still below `micro_max_risk_pct`; otherwise the trade is skipped (account protection)."""
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
    """Like size_position, but never risks more than `budget` dollars (the risk room still free
    after the trades that are already open). The lot size is scaled down to fit when possible.
    Returns (lots, risk_amount, reject_reason)."""
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
