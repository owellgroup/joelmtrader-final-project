"""Unit tests for direction lock and profit lock (no MT5)."""
from app.analyzer import htf_direction
from app.risk import lock_floor_r


def test_htf_follows_daily_and_h4():
    assert htf_direction({"D1": 0.4, "H4": 0.3, "H1": 0.2}, {"D1": {"trend": 1}, "H4": {"trend": 1}}) == 1
    assert htf_direction({"D1": -0.4, "H4": -0.3, "H1": -0.1}, {"D1": {"trend": -1}, "H4": {"trend": -1}}) == -1


def test_htf_waits_when_daily_and_h4_disagree():
    assert htf_direction({"D1": 0.4, "H4": -0.3, "H1": 0.1}, {"D1": {"trend": 1}, "H4": {"trend": -1}}) == 0


def test_lock_floor_keeps_most_of_a_runner():
    # $4 at 2R must not be allowed to walk back to $1 (0.5R)
    floor = lock_floor_r(2.0)
    assert floor is not None and floor >= 1.35
    assert lock_floor_r(0.4) is None
    assert lock_floor_r(0.7) == 0.05


if __name__ == "__main__":
    test_htf_follows_daily_and_h4()
    test_htf_waits_when_daily_and_h4_disagree()
    test_lock_floor_keeps_most_of_a_runner()
    print("OK")
