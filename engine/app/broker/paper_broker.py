"""Simulated broker: realistic synthetic market so the whole stack can be tested without MT5."""
import threading
import time
import numpy as np
import pandas as pd

from ..config import Settings
from .base import Broker

SPECS = {
    "XAUUSD": dict(base=3300.0, digits=2, contract=100.0, spread=0.25, sigma=0.00020),
    "EURUSD": dict(base=1.0850, digits=5, contract=100000.0, spread=0.00010, sigma=0.000045),
    "GBPUSD": dict(base=1.2900, digits=5, contract=100000.0, spread=0.00014, sigma=0.000055),
    # JPY-quoted: profit is in yen, so `fx` converts yen to USD (about 1 / USDJPY)
    "GBPJPY": dict(base=195.0, digits=3, contract=100000.0, spread=0.025, sigma=0.000060, fx=1 / 150.0),
    "EURJPY": dict(base=163.0, digits=3, contract=100000.0, spread=0.020, sigma=0.000055, fx=1 / 150.0),
}
RULE = {"M1": "1min", "M5": "5min", "M10": "10min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D"}
HISTORY_DAYS = 90


class PaperBroker(Broker):
    name = "paper"

    def __init__(self):
        self.lock = threading.RLock()
        self.rng = np.random.default_rng(42)
        self.speed = Settings.paper_speed
        self.balance = Settings.paper_balance
        self.start_balance = self.balance
        self.leverage = 500
        self.positions_d, self.closed = {}, {}
        self.next_ticket = 1000
        self.sim_time = int(time.time()) // 60 * 60
        self.m1, self.cur, self.price, self.drift_left, self.drift = {}, {}, {}, {}, {}
        for s, sp in SPECS.items():
            self._gen_history(s, sp)
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    # ---------------- market generation
    def _gen_history(self, s, sp):
        n = HISTORY_DAYS * 1440
        t0 = self.sim_time - n * 60
        times = t0 + np.arange(n) * 60
        hours = ((times // 3600) % 24)
        season = np.where((hours >= 7) & (hours <= 17), 1.5, 0.7)
        drift = np.zeros(n)
        i = 0
        while i < n:
            L = int(self.rng.integers(90, 400))
            drift[i:i + L] = self.rng.normal(0, 0.35) * sp["sigma"]
            i += L
        steps = self.rng.normal(0, 1, (n, 4)) * (sp["sigma"] * season[:, None] / 2) + drift[:, None] / 4
        path = sp["base"] * np.exp(np.cumsum(steps.reshape(-1)).reshape(n, 4))
        op = np.concatenate([[sp["base"]], path[:-1, 3]])
        df = pd.DataFrame({"time": times, "open": op, "high": np.maximum(op, path.max(1)),
                           "low": np.minimum(op, path.min(1)), "close": path[:, 3],
                           "volume": (self.rng.gamma(4, 50, n) * season).astype(int) + 1})
        self.m1[s] = df
        last = df.iloc[-1]
        self.price[s] = float(last["close"])
        self.cur[s] = dict(time=int(last["time"]) + 60, open=float(last["close"]), high=float(last["close"]),
                           low=float(last["close"]), close=float(last["close"]), volume=1)
        self.drift[s], self.drift_left[s] = 0.0, 0

    def _run(self):
        step = 0.2
        while not self._stop:
            time.sleep(step)
            with self.lock:
                dt = step * self.speed
                self.sim_time += dt
                for s, sp in SPECS.items():
                    if self.drift_left[s] <= 0:
                        self.drift[s], self.drift_left[s] = self.rng.normal(0, 0.35) * sp["sigma"], int(self.rng.integers(90, 400))
                    hour = (int(self.sim_time) // 3600) % 24
                    season = 1.5 if 7 <= hour <= 17 else 0.7
                    ret = self.rng.normal(0, 1) * sp["sigma"] * season * np.sqrt(dt / 60) + self.drift[s] * dt / 60
                    self.price[s] *= float(np.exp(ret))
                    c = self.cur[s]
                    while int(self.sim_time) >= c["time"] + 60:      # roll the minute candle
                        self.m1[s].loc[len(self.m1[s])] = [c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"]]
                        c = self.cur[s] = dict(time=c["time"] + 60, open=c["close"], high=c["close"], low=c["close"], close=c["close"], volume=1)
                        self.drift_left[s] -= 1
                    p = self.price[s]
                    c["high"], c["low"], c["close"] = max(c["high"], p), min(c["low"], p), p
                    c["volume"] += int(self.rng.integers(1, 6))
                self._check_exits()

    def _spread(self, s):
        return SPECS[s]["spread"] * float(1 + 0.2 * abs(np.sin(self.sim_time / 900)))

    # ---------------- Broker API
    def connect(self, login=None, password=None, server=None):
        return {"connected": True, "mode": "paper", "message": "Paper (simulated) broker active"}

    def status(self):
        return {"connected": True, "mode": "paper", "login": "PAPER", "server": "Simulator"}

    def is_connected(self): return True

    def _floating(self):
        return sum(p["profit"] for p in self.positions_d.values())

    def account(self):
        with self.lock:
            self._reprice()
            fl = self._floating()
            margin = sum(self.margin_required(p["symbol"], p["side"], p["volume"]) for p in self.positions_d.values())
            eq = self.balance + fl
            return dict(balance=round(self.balance, 2), equity=round(eq, 2), margin=round(margin, 2),
                        free_margin=round(eq - margin, 2), profit=round(fl, 2), leverage=self.leverage,
                        currency="USD", login="PAPER", server="Simulator", name="Paper account")

    def symbol_info(self, symbol):
        sp = SPECS[symbol]
        point = 10 ** -sp["digits"]
        return dict(symbol=symbol, digits=sp["digits"], point=point, tick_size=point,
                    tick_value=sp["contract"] * point * sp.get("fx", 1.0), contract_size=sp["contract"],
                    volume_min=0.01, volume_max=100.0, volume_step=0.01, stops_level=10)

    def tick(self, symbol):
        with self.lock:
            p, sp = self.price[symbol], self._spread(symbol)
            nd = SPECS[symbol]["digits"]
            return dict(bid=round(p - sp / 2, nd), ask=round(p + sp / 2, nd), spread=round(sp, nd), time=int(self.sim_time))

    def rates(self, symbol, tf, count):
        with self.lock:
            base = self.m1[symbol]
            cur = self.cur[symbol]
            need = min(len(base), count * (RULE and {"M1": 1, "M5": 5, "M10": 10, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}[tf]) + 1500)
            df = pd.concat([base.iloc[-need:], pd.DataFrame([cur])], ignore_index=True)
        if tf == "M1":
            return df.iloc[-count:].reset_index(drop=True)
        d = df.assign(dt=pd.to_datetime(df["time"], unit="s", utc=True)).set_index("dt")
        r = d.resample(RULE[tf]).agg({"time": "first", "open": "first", "high": "max", "low": "min",
                                       "close": "last", "volume": "sum"}).dropna()
        return r.iloc[-count:].reset_index(drop=True)

    def _reprice(self):
        for p in self.positions_d.values():
            t = self.tick(p["symbol"])
            cur = t["bid"] if p["side"] == "BUY" else t["ask"]
            sgn = 1 if p["side"] == "BUY" else -1
            p["price_current"] = cur
            sp = SPECS[p["symbol"]]
            p["profit"] = (cur - p["price_open"]) * sgn * sp["contract"] * p["volume"] * sp.get("fx", 1.0)

    def positions(self):
        with self.lock:
            self._reprice()
            return [dict(p) for p in self.positions_d.values()]

    def margin_required(self, symbol, side, volume):
        sp = SPECS[symbol]
        return sp["contract"] * volume * self.price[symbol] * sp.get("fx", 1.0) / self.leverage

    def send_market(self, symbol, side, volume, sl, tp, comment=""):
        with self.lock:
            t = self.tick(symbol)
            price = t["ask"] if side == "BUY" else t["bid"]
            acct = self.account()
            if self.margin_required(symbol, side, volume) > acct["free_margin"]:
                return dict(ok=False, retcode=10019, msg="Not enough money")
            self.next_ticket += 1
            self.positions_d[self.next_ticket] = dict(
                ticket=self.next_ticket, symbol=symbol, side=side, volume=volume, price_open=price,
                price_current=price, sl=sl or 0.0, tp=tp or 0.0, profit=0.0, swap=0.0,
                time=int(time.time()), sim_time=int(self.sim_time), comment=comment, magic=Settings.magic)
            return dict(ok=True, ticket=self.next_ticket, price=price, retcode=10009, msg="Done")

    def _close(self, ticket, price, reason):
        p = self.positions_d.pop(ticket)
        sgn = 1 if p["side"] == "BUY" else -1
        sp = SPECS[p["symbol"]]
        gross = (price - p["price_open"]) * sgn * sp["contract"] * p["volume"] * sp.get("fx", 1.0)
        comm = -Settings.paper_commission_per_lot * p["volume"]
        self.balance += gross + comm
        self.closed[ticket] = dict(close_price=price, profit=gross, commission=comm, swap=0.0,
                                   time=int(time.time()), reason=reason)

    def _check_exits(self):
        for t, p in list(self.positions_d.items()):
            tk = self.tick(p["symbol"])
            if p["side"] == "BUY":
                if p["sl"] and tk["bid"] <= p["sl"]: self._close(t, p["sl"], "SL")
                elif p["tp"] and tk["bid"] >= p["tp"]: self._close(t, p["tp"], "TP")
            else:
                if p["sl"] and tk["ask"] >= p["sl"]: self._close(t, p["sl"], "SL")
                elif p["tp"] and tk["ask"] <= p["tp"]: self._close(t, p["tp"], "TP")

    def close_position(self, ticket):
        with self.lock:
            p = self.positions_d.get(ticket)
            if not p:
                return dict(ok=False, msg="position not found")
            tk = self.tick(p["symbol"])
            price = tk["bid"] if p["side"] == "BUY" else tk["ask"]
            self._close(ticket, price, "CLIENT")
            return dict(ok=True, price=price)

    def modify_sltp(self, ticket, sl, tp):
        with self.lock:
            p = self.positions_d.get(ticket)
            if not p:
                return dict(ok=False, msg="position not found")
            if sl is not None: p["sl"] = sl
            if tp is not None: p["tp"] = tp
            return dict(ok=True)

    def deal_summary(self, ticket):
        return self.closed.get(ticket)
