"""Unit tests for direction lock and scalp basket helpers (no MT5)."""
from app.analyzer import htf_direction
from app.config import RiskConfig
from app.risk import lock_floor_r, basket_trade_count, basket_profit_target, basket_protect_loss, scalp_lot


def test_htf_follows_daily_and_h4():
    assert htf_direction({"D1": 0.4, "H4": 0.3, "H1": 0.2}, {"D1": {"trend": 1}, "H4": {"trend": 1}}) == 1
    assert htf_direction({"D1": -0.4, "H4": -0.3, "H1": -0.1}, {"D1": {"trend": -1}, "H4": {"trend": -1}}) == -1


def test_htf_prefers_h4_when_daily_disagrees():
    assert htf_direction({"D1": 0.4, "H4": -0.3, "H1": -0.2}, {"D1": {"trend": 1}, "H4": {"trend": -1}}) == -1


def test_htf_bias_fallback():
    assert htf_direction({"D1": 0.05, "H4": 0.05, "H1": 0.0}, {"D1": {"trend": 0}, "H4": {"trend": 0}}, bias=0.2) == 1


def test_lock_floor_keeps_most_of_a_runner():
    floor = lock_floor_r(2.0)
    assert floor is not None and floor >= 1.35
    assert lock_floor_r(0.4) is None
    assert lock_floor_r(0.7) == 0.05


def test_basket_scales_with_equity():
    cfg = RiskConfig()
    assert basket_trade_count(40, cfg) >= 2
    assert basket_trade_count(220, cfg) >= 8
    assert basket_trade_count(5000, cfg) <= cfg.scalp_max_tickets


def test_basket_profit_is_meaningful():
    cfg = RiskConfig()
    t = basket_profit_target(100, 5, cfg)
    assert t >= cfg.scalp_min_profit_usd
    assert basket_profit_target(100, 20, cfg) >= t


def test_soft_protect_exists():
    cfg = RiskConfig()
    loss = basket_protect_loss(100, 8, cfg)
    assert loss >= cfg.scalp_protect_floor_usd


def test_scalp_lot_defaults_to_001():
    cfg = RiskConfig()
    info = {"volume_min": 0.01, "volume_step": 0.01, "volume_max": 100}
    assert scalp_lot(info, cfg) == 0.01


if __name__ == "__main__":
    test_htf_follows_daily_and_h4()
    test_htf_prefers_h4_when_daily_disagrees()
    test_htf_bias_fallback()
    test_lock_floor_keeps_most_of_a_runner()
    test_basket_scales_with_equity()
    test_basket_profit_is_meaningful()
    test_soft_protect_exists()
    test_scalp_lot_defaults_to_001()
    print("OK")
