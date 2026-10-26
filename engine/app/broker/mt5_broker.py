"""MetaTrader 5 broker.

Two transports, same API surface:
  * Windows  : `import MetaTrader5` talks directly to the locally installed MT5 terminal.
  * Linux    : an RPyC client talks to scripts/mt5_bridge.py on the Windows PC
               where the MT5 desktop (terminal64.exe) is open.
"""
import logging
import sys
import threading
import time
import numpy as np
import pandas as pd

from ..config import SYMBOLS, Settings
from .base import Broker

log = logging.getLogger("mt5")
DEAL_REASONS = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL", 5: "TP", 6: "SO"}


def _plain(value):
    """MetaTrader5 rejects numpy scalars inside an order request."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        return _plain(item())
    return value


class MT5Broker(Broker):
    name = "mt5"

    def __init__(self):
        self.lock = threading.RLock()
        self.mt5 = None
        self.symbols = {}          # canonical -> broker symbol name
        self.login = Settings.mt5_login
        self.password = Settings.mt5_password
        self.server = Settings.mt5_server
        self._connected = False
        self._last_error = ""
        self._last_attempt = 0
        self._ticks = {}
        self._info_cache = {}
        self._acct_cache = None
        self._quote_ready = set()

    # ---------------------------------------------------------------- connection
    def _module(self):
        if self.mt5 is not None:
            return self.mt5
        if sys.platform == "win32":
            import MetaTrader5 as m
            self.mt5 = m
        else:
            from .mt5_remote import RemoteMetaTrader5
            self.mt5 = RemoteMetaTrader5(host=Settings.mt5_rpyc_host, port=Settings.mt5_rpyc_port)
        return self.mt5

    def connect(self, login=None, password=None, server=None):
        with self.lock:
            if login: self.login = str(login)
            if password: self.password = password
            if server: self.server = server
            self._last_attempt = time.time()
            try:
                m = self._module()
                kwargs = {}
                if Settings.mt5_path and sys.platform == "win32":
                    kwargs["path"] = Settings.mt5_path
                if self.login and self.password and self.server:
                    ok = m.initialize(login=int(self.login), password=self.password, server=self.server, **kwargs)
                else:
                    ok = m.initialize(**kwargs)       # uses the account already logged in inside the terminal
                if not ok:
                    self._connected = False
                    self._last_error = f"initialize() failed: {m.last_error()}"
                    return {"connected": False, "message": self._last_error}
                info = m.account_info()
                if info is None:
                    self._connected = False
                    self._last_error = "Terminal started but no account is logged in. Check login/server/password."
                    return {"connected": False, "message": self._last_error}
                self._connected = True
                self._last_error = ""
                self._resolve_symbols()
                return {"connected": True, "message": f"Connected to {info.server} (#{info.login})"}
            except Exception as e:                      # noqa: BLE001
                self._connected = False
                self.mt5 = None
                self._last_error = f"{type(e).__name__}: {e}"
                low = self._last_error.lower()
                if "not connected to the server" in low or any(s in low for s in ("timeout", "timed out", "refused")):
                    self._last_error += " Start scripts\\mt5-bridge-windows.bat on the laptop and leave it open."
                log.warning("MT5 connect failed: %s", self._last_error)
                return {"connected": False, "message": self._last_error}

    def _broker_names(self):
        try:
            return [s.name for s in (self.mt5.symbols_get() or [])]
        except Exception:                               # noqa: BLE001
            return []

    def _pick_broker_name(self, canon):
        """Headway and others use GBPJPYm / EURUSDm. Match the live spelling, not the pretty name."""
        known = self.symbols.get(canon)
        if known and known != canon:
            return known
        names = self._broker_names()
        by_upper = {n.upper(): n for n in names}
        for suf in (Settings.symbol_suffix, "", "m", ".m", "micro", ".a", ".r", ".pro", "_", "#"):
            hit = by_upper.get((canon + (suf or "")).upper())
            if hit:
                return hit
        if canon == "XAUUSD":
            for alt in ("XAUUSD", "GOLD"):
                hits = [n for n in names if n.upper().startswith(alt) and not any(ch.isdigit() for ch in n)]
                if hits:
                    return sorted(hits, key=len)[0]
        hits = [n for n in names if n.upper().startswith(canon) and not any(ch.isdigit() for ch in n)]
        return sorted(hits, key=len)[0] if hits else canon

    def _ensure_symbol(self, canon):
        """Select the broker symbol and wait until bid/ask are real. First select often returns 0."""
        name = self._pick_broker_name(canon)
        self.symbols[canon] = name
        if self.mt5 is None:
            return name
        try:
            self.mt5.symbol_select(name, True)
        except Exception:                               # noqa: BLE001
            return name
        if name in self._quote_ready:
            return name
        deadline = time.time() + 2.5
        while time.time() <= deadline:
            t = self.mt5.symbol_info_tick(name)
            if t is not None and float(getattr(t, "bid", 0) or 0) > 0 and float(getattr(t, "ask", 0) or 0) > 0:
                self._quote_ready.add(name)
                return name
            time.sleep(0.25)
        log.warning("%s (%s) has no live bid/ask yet", canon, name)
        return name

    def _resolve_symbols(self):
        for canon in SYMBOLS:
            self._ensure_symbol(canon)
        log.info("Symbol map: %s", self.symbols)

    def is_connected(self):
        return self._connected

    def ensure(self):
        if self._connected:
            try:
                if self._module().account_info() is not None:
                    return True
            except Exception:                           # noqa: BLE001
                pass
            self._connected = False
        if time.time() - self._last_attempt > 10:
            self.connect()
        return self._connected

    def status(self):
        d = {"connected": self._connected, "mode": "mt5", "login": self.login, "server": self.server,
             "message": self._last_error}
        if self._connected:
            try:
                a = self._module().account_info()
                d.update(login=a.login, server=a.server, name=a.name, company=a.company,
                         currency=a.currency, leverage=a.leverage,
                         demo=(a.trade_mode == 0), trade_allowed=bool(a.trade_allowed))
            except Exception:                           # noqa: BLE001
                pass
        return d

    # ---------------------------------------------------------------- data
    def sym(self, canonical):
        return self.symbols.get(canonical, canonical + Settings.symbol_suffix)

    def account(self):
        with self.lock:
            if self._acct_cache and time.time() - self._acct_cache[0] < 2:
                return self._acct_cache[1]
            if not self.ensure():
                return None
            a = self.mt5.account_info()
            if a is None:
                return None
            snap = dict(balance=a.balance, equity=a.equity, margin=a.margin, free_margin=a.margin_free,
                        profit=a.profit, leverage=a.leverage, currency=a.currency, login=a.login,
                        server=a.server, name=a.name)
            self._acct_cache = (time.time(), snap)
            return snap

    def symbol_info(self, symbol):
        with self.lock:
            cached = self._info_cache.get(symbol)
            if cached and time.time() - cached[0] < 60:
                return cached[1]
            if self.mt5 is None:
                raise RuntimeError(self._last_error or "MT5 is not connected")
            name = self._ensure_symbol(symbol)
            i = self.mt5.symbol_info(name)
            if i is None:
                raise RuntimeError(f"symbol {symbol} not available on this broker")
            info = dict(symbol=name, digits=i.digits, point=i.point,
                        tick_size=i.trade_tick_size or i.point, tick_value=i.trade_tick_value,
                        contract_size=i.trade_contract_size, volume_min=i.volume_min, volume_max=i.volume_max,
                        volume_step=i.volume_step, stops_level=i.trade_stops_level, filling=i.filling_mode)
            self._info_cache[symbol] = (time.time(), info)
            return info

    def tick(self, symbol):
        with self.lock:
            cached = self._ticks.get(symbol)
            if cached and time.time() - cached[0] < 1 and cached[1]["bid"] > 0:
                return cached[1]
            if self.mt5 is None:
                return None
            name = self._ensure_symbol(symbol)
            t = self.mt5.symbol_info_tick(name)
            if t is None or float(getattr(t, "bid", 0) or 0) <= 0 or float(getattr(t, "ask", 0) or 0) <= 0:
                return None
            snap = dict(bid=t.bid, ask=t.ask, spread=t.ask - t.bid, time=t.time)
            self._ticks[symbol] = (time.time(), snap)
            return snap

    def rates(self, symbol, tf, count):
        m = self.mt5
        if m is None:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        self._ensure_symbol(symbol)
        tfm = {"M1": m.TIMEFRAME_M1, "M5": m.TIMEFRAME_M5, "M15": m.TIMEFRAME_M15, "M30": m.TIMEFRAME_M30,
               "H1": m.TIMEFRAME_H1, "H4": m.TIMEFRAME_H4, "D1": m.TIMEFRAME_D1}[tf]
        with self.lock:
            arr = m.copy_rates_from_pos(self.sym(symbol), tfm, 0, count)
        if arr is None or len(arr) == 0:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(arr)
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["time", "open", "high", "low", "close", "volume"]].astype(
            {"time": "int64", "open": float, "high": float, "low": float, "close": float, "volume": float})

    def _canon(self, name):
        for k, v in self.symbols.items():
            if v == name:
                return k
        return name

    def positions(self):
        with self.lock:
            if self.mt5 is None:
                return []
            res = self.mt5.positions_get() or []
            out = []
            for p in res:
                if p.magic != Settings.magic:
                    continue
                out.append(dict(ticket=p.ticket, symbol=self._canon(p.symbol), side="BUY" if p.type == 0 else "SELL",
                                volume=p.volume, price_open=p.price_open, price_current=p.price_current,
                                sl=p.sl, tp=p.tp, profit=p.profit, swap=p.swap, time=p.time, comment=p.comment,
                                magic=p.magic))
            return out

    def margin_required(self, symbol, side, volume):
        with self.lock:
            m = self.mt5
            t = self.tick(symbol)
            if t is None:
                return 1e9
            r = m.order_calc_margin(m.ORDER_TYPE_BUY if side == "BUY" else m.ORDER_TYPE_SELL,
                                    self.sym(symbol), volume, t["ask"] if side == "BUY" else t["bid"])
            return float(r) if r is not None else 1e9

    # ---------------------------------------------------------------- trading
    def _filling(self, name):
        m = self.mt5
        fm = m.symbol_info(name).filling_mode
        if fm & 2:
            return m.ORDER_FILLING_IOC
        if fm & 1:
            return m.ORDER_FILLING_FOK
        return m.ORDER_FILLING_RETURN

    def _order_send(self, req):
        # Wheel 5.0.5735+ made order_send keyword-only. A positional dict
        # returns None and last_error (-2, 'Unnamed arguments not allowed')
        # before the terminal sees the order. Older wheels accept only the dict.
        m = self.mt5
        clean = {key: _plain(value) for key, value in req.items()}
        try:
            return m.order_send(**clean)
        except TypeError:
            return m.order_send(clean)

    def send_market(self, symbol, side, volume, sl, tp, comment=""):
        with self.lock:
            m = self.mt5
            name = self.sym(symbol)
            t = m.symbol_info_tick(name)
            if t is None:
                return dict(ok=False, msg="no tick")
            price = t.ask if side == "BUY" else t.bid
            req = {"action": m.TRADE_ACTION_DEAL, "symbol": name, "volume": float(volume),
                   "type": m.ORDER_TYPE_BUY if side == "BUY" else m.ORDER_TYPE_SELL, "price": price,
                   "sl": float(sl or 0), "tp": float(tp or 0), "deviation": 20, "magic": Settings.magic,
                   "comment": (comment or "ForexBot")[:30], "type_time": m.ORDER_TIME_GTC,
                   "type_filling": self._filling(name)}
            r = self._order_send(req)
            if r is None:
                return dict(ok=False, msg=f"order_send returned None: {m.last_error()}")
            ok = r.retcode == m.TRADE_RETCODE_DONE
            return dict(ok=ok, ticket=r.order if ok else None, price=r.price, retcode=r.retcode, msg=r.comment)

    def close_position(self, ticket):
        with self.lock:
            m = self.mt5
            pos = m.positions_get(ticket=int(ticket))
            if not pos:
                return dict(ok=False, msg="position not found")
            p = pos[0]
            t = m.symbol_info_tick(p.symbol)
            buy = p.type == 0
            req = {"action": m.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                   "type": m.ORDER_TYPE_SELL if buy else m.ORDER_TYPE_BUY, "position": int(ticket),
                   "price": t.bid if buy else t.ask, "deviation": 30, "magic": Settings.magic,
                   "comment": "ForexBot close", "type_time": m.ORDER_TIME_GTC, "type_filling": self._filling(p.symbol)}
            r = self._order_send(req)
            if r is None:
                return dict(ok=False, price=None, msg=f"close order_send returned None: {m.last_error()}")
            ok = r.retcode == m.TRADE_RETCODE_DONE
            return dict(ok=ok, price=getattr(r, "price", None), msg=getattr(r, "comment", "none"))

    def modify_sltp(self, ticket, sl, tp):
        with self.lock:
            m = self.mt5
            pos = m.positions_get(ticket=int(ticket))
            if not pos:
                return dict(ok=False, msg="position not found")
            p = pos[0]
            req = {"action": m.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": int(ticket),
                   "sl": float(sl if sl is not None else p.sl), "tp": float(tp if tp is not None else p.tp)}
            r = self._order_send(req)
            if r is None:
                return dict(ok=False, msg=f"modify order_send returned None: {m.last_error()}")
            return dict(ok=r.retcode == m.TRADE_RETCODE_DONE, msg=getattr(r, "comment", "none"))

    def deal_summary(self, ticket):
        with self.lock:
            m = self.mt5
            deals = m.history_deals_get(position=int(ticket)) or []
            outs = [d for d in deals if d.entry in (1, 3)]       # DEAL_ENTRY_OUT / OUT_BY
            if not outs:
                return None
            return dict(close_price=outs[-1].price, profit=sum(d.profit for d in deals),
                        commission=sum(d.commission for d in deals), swap=sum(d.swap for d in deals),
                        time=outs[-1].time, reason=DEAL_REASONS.get(outs[-1].reason, "CLIENT"))
