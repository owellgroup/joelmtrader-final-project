"""The trading brain: scanning loop, ranking, entry, position management, risk guards."""
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

from . import structure as st
from .analyzer import analyze_symbol
from .config import SYMBOLS, PRIORITY_SYMBOLS, USD_QUOTED, JPY_CROSSES, DATA_DIR, Settings
from .risk import size_within_budget

log = logging.getLogger("bot")


class PerformanceTracker:
    """Remembers how each (symbol, setup) combination has been performing and nudges its score."""
    path = os.path.join(DATA_DIR, "perf.json")

    def __init__(self):
        self.hist = {}
        try:
            self.hist = json.load(open(self.path))
        except Exception:               # noqa: BLE001
            pass

    def record(self, symbol, setup, win):
        h = self.hist.setdefault(f"{symbol}|{setup}", [])
        h.append(1 if win else 0)
        del h[:-20]
        try:
            json.dump(self.hist, open(self.path, "w"))
        except Exception:               # noqa: BLE001
            pass

    def adjust(self, symbol, setup):
        h = self.hist.get(f"{symbol}|{setup}", [])
        if len(h) < 6:
            return 0
        wr = sum(h) / len(h)
        return -8 if wr < 0.30 else (-3 if wr < 0.40 else (3 if wr > 0.60 else 0))


class Bot:
    def __init__(self, broker, md, news, reporter, cfgstore):
        self.broker, self.md, self.news, self.rep, self.cfgs = broker, md, news, reporter, cfgstore
        self.perf = PerformanceTracker()
        self.lock = threading.RLock()
        self.enabled = False
        self.session_id = None
        self.status = "STOPPED"
        self.halt_reason = ""
        self.halt_day = None
        self.cooldown_until = 0
        self.consec_losses = 0
        self.peak_equity = 0
        self.day_key, self.day_start_balance = None, 0
        self.tracked, self.close_reason, self.sym_cooldown = {}, {}, {}
        self.last_entry = 0
        self._skip_logged = {}
        self.scan_data, self.last_scan_ts, self.last_scan_push, self.last_snapshot = None, 0, 0, 0
        self._found_key, self._found_at = None, 0
        self.activity = deque(maxlen=60)
        self.stats = dict(opened=0, closed=0, wins=0, losses=0, pnl=0.0)
        self.info_cache = {}
        self.last_alert = {}
        self._stop = False
        threading.Thread(target=self._loop, daemon=True, name="bot-loop").start()

    # ------------------------------------------------------------------ helpers
    @property
    def cfg(self): return self.cfgs.cfg

    def _now(self):
        return float(getattr(self.broker, "sim_time", time.time())) if self.broker.name == "paper" else time.time()

    def _utc(self): return datetime.fromtimestamp(self._now(), tz=timezone.utc)

    def log_event(self, msg, level="info"):
        self.activity.appendleft({"time": int(time.time()), "level": level, "message": msg})
        log.info(msg)

    def info(self, symbol):
        c = self.info_cache.get(symbol)
        if not c or time.time() - c[0] > 600:
            c = (time.time(), self.broker.symbol_info(symbol))
            self.info_cache[symbol] = c
        return c[1]

    def alert(self, key, subject, message, severity="WARNING", every=1800):
        if time.time() - self.last_alert.get(key, 0) < every:
            return
        self.last_alert[key] = time.time()
        self.rep.emit("ALERT", {"key": key, "subject": subject, "message": message, "severity": severity}, self.session_id)

    # ------------------------------------------------------------------ control
    def start(self, session_id):
        with self.lock:
            acct = self.broker.account()
            if not acct:
                raise RuntimeError("Broker not connected - link your MT5 account first")
            self.enabled, self.session_id = True, session_id
            self.status, self.halt_reason, self.halt_day = "SCANNING", "", None
            self.consec_losses, self.cooldown_until = 0, 0
            self.stats = dict(opened=0, closed=0, wins=0, losses=0, pnl=0.0)
            self.peak_equity = acct["equity"]
            self.day_key, self.day_start_balance = self._utc().date(), acct["balance"]
            self.log_event(f"Bot started - balance ${acct['balance']:.2f}")
            self._adopt_positions()
            return self.status_dict()

    def stop(self, close_positions=True):
        with self.lock:
            self.enabled = False
            if close_positions:
                for t in list(self.tracked):
                    self.close_reason[t] = "Bot stopped by user"
                    self.broker.close_position(t)
                for _ in range(20):
                    self._sync_positions()
                    if not self.tracked:
                        break
                    time.sleep(0.5)
            self.status = "STOPPED"
            self.log_event("Bot stopped")
            acct = self.broker.account() or {}
        self.rep.flush(15)
        out = self.status_dict()
        out["account"] = acct
        return out

    # ------------------------------------------------------------------ main loop
    def _loop(self):
        while not self._stop:
            try:
                with self.lock:
                    self._tick()
            except Exception as e:                  # noqa: BLE001
                log.exception("loop error: %s", e)
            time.sleep(Settings.loop_seconds / (Settings.paper_speed if self.broker.name == "paper" and Settings.paper_speed > 1 else 1))

    def _tick(self):
        now = self._now()
        acct = self.broker.account()
        if acct is None:
            if self.enabled:
                self.status = "DISCONNECTED"
                self.alert("mt5_disconnected", "MT5 disconnected", "The bot lost its connection to MetaTrader 5 and is retrying.", "CRITICAL", 900)
            return
        if self.enabled and self.status == "DISCONNECTED":
            self.status = "SCANNING"
        interval = Settings.scan_seconds_running if self.enabled else Settings.scan_seconds_idle
        if time.time() - self.last_scan_ts >= interval:
            self._scan(acct)
        if not self.enabled:
            return

        key = self._utc().date()
        if key != self.day_key:                       # new UTC day -> reset daily guards
            self.day_key, self.day_start_balance = key, acct["balance"]
            if self.status == "HALTED" and self.halt_day is not None and key != self.halt_day:
                self.status, self.halt_reason = "SCANNING", ""
                self.log_event("New trading day - daily-loss halt lifted")
        self.peak_equity = max(self.peak_equity, acct["equity"])
        self._sync_positions()
        if time.time() - self.last_snapshot > 60:
            self.last_snapshot = time.time()
            self.rep.emit("SNAPSHOT", dict(balance=acct["balance"], equity=acct["equity"], margin=acct["margin"],
                                           freeMargin=acct["free_margin"], openPositions=len(self.tracked)), self.session_id)

        cfg = self.cfg
        dd = (self.peak_equity - acct["equity"]) / max(self.peak_equity, 1e-9) * 100
        dl = (self.day_start_balance - acct["equity"]) / max(self.day_start_balance, 1e-9) * 100
        if self.status != "HALTED":
            if dd >= cfg.max_drawdown_pct:
                self._halt(f"Max drawdown {dd:.1f}% reached - kill switch", None)
            elif dl >= cfg.daily_loss_limit_pct:
                self._halt(f"Daily loss limit {dl:.1f}% reached - paused until next UTC day", self.day_key)
        if self.status == "HALTED":
            return
        self._manage_positions()
        if self.cooldown_until > now:
            self.status = "COOLDOWN"
            return
        self.status = "IN_TRADE" if self.tracked else "SCANNING"
        self._maybe_open(acct, now)

    # ------------------------------------------------------------------ scanning
    def _scan(self, acct):
        cfg, equity = self.cfg, acct["equity"]
        ranks = []
        for s in SYMBOLS:
            try:
                frames = self.md.frames(s)
                tick = self.broker.tick(s)
                if not frames or not tick:
                    continue
                info = self.info(s)
                price = (tick["ask"] + tick["bid"]) / 2
                zones = st.sr_zones(frames, price, frames["H1"].atr)
                ranks.append(analyze_symbol(s, frames, tick, info, zones, cfg, self.perf, equity, self.news))
            except Exception as e:              # noqa: BLE001
                log.warning("scan %s failed: %s", s, e, exc_info=True)
        # Priority symbols (gold, GBPJPY, EURJPY) always come first; the others only after them.
        ranks.sort(key=lambda r: (0 if r["symbol"] in PRIORITY_SYMBOLS else 1, -r["rankScore"]))
        self._check_priority_affordability(ranks, equity)
        chosen = next((r for r in ranks if r["tradable"]), None)
        if chosen:
            why = f"{chosen['symbol']} {chosen['side']} selected - score {chosen['score']:.0f}, R:R {chosen['rr']}, setup {chosen['setup']}. " + "; ".join(chosen["reasons"][:4])
        elif ranks:
            top = ranks[0]
            why = f"No valid entry right now. Best candidate {top['symbol']} {top['side']} (score {top['score']:.0f}): " + "; ".join(top["blockedReasons"][:3])
        else:
            why = "Waiting for market data"
        self.scan_data = {"time": int(time.time()), "rankings": ranks, "chosen": chosen["symbol"] if chosen else None,
                          "why": why, "news": self._news_state(), "running": self.enabled}
        self._announce_found(chosen)
        self.last_scan_ts = time.time()
        if time.time() - self.last_scan_push > 15:
            self.last_scan_push = time.time()
            self.rep.emit("SCAN", self.scan_data, self.session_id)

    def _check_priority_affordability(self, ranks, equity):
        """Every scan: does the balance allow a trade on each priority symbol? If not, say exactly why."""
        if not self.enabled:
            return
        for r in ranks:
            a = r.get("affordability") or {}
            if r.get("priority") and not a.get("affordable", True):
                self._skip_note(r["symbol"], (
                    f"cannot be afforded yet - the smallest lot risks ${a['minLotRisk']:.2f} but the cap on a "
                    f"${equity:.2f} account is ${a['riskCap']:.2f}. It qualifies at about ${a['balanceNeeded']:.0f} equity "
                    f"with the current stop."))

    @staticmethod
    def _usd_dir(symbol, side):
        """+1 = long USD, -1 = short USD, 0 = no USD exposure."""
        if symbol not in USD_QUOTED:
            return 0
        return -1 if side == "BUY" else 1

    @staticmethod
    def _jpy_dir(symbol, side):
        """+1 = long JPY, -1 = short JPY, 0 = no JPY exposure."""
        if symbol not in JPY_CROSSES:
            return 0
        return -1 if side == "BUY" else 1

    def _news_state(self):
        out = {}
        for s in SYMBOLS:
            b, reason = self.news.blocked(s, self.cfg)
            out[s] = {"blocked": b, "reason": reason}
        return out

    def _announce_found(self, chosen):
        """One alert per new tradable setup, through the same notification path as entries."""
        if not self.enabled:
            return
        if not chosen:
            if self._found_key and time.time() - self._found_at > 600:
                self._found_key = None
            return
        key = f"{chosen['symbol']}|{chosen['side']}|{chosen['setup']}"
        if key == self._found_key:
            return
        self._found_key, self._found_at = key, time.time()
        plan = chosen.get("plan") or {}
        self.log_event(f"Found {chosen['side']} {chosen['symbol']} score {chosen['score']:.0f} ({chosen['setup']})")
        self.rep.emit("TRADE_FOUND", dict(symbol=chosen["symbol"], side=chosen["side"], score=chosen["score"],
                                           setup=chosen["setup"], rr=chosen["rr"], entry=plan.get("entry"),
                                           sl=plan.get("sl"), tp=plan.get("tp"), reasons=(chosen.get("reasons") or [])[:4]),
                      self.session_id)

    def force_scan(self):
        with self.lock:
            acct = self.broker.account()
            if acct:
                self._scan(acct)
        return self.scan_data

    # ------------------------------------------------------------------ entries
    def _maybe_open(self, acct, now):
        cfg = self.cfg
        if not self.scan_data or time.time() - self.last_scan_ts > 30 or len(self.tracked) >= cfg.max_positions:
            return
        if now - self.last_entry < cfg.min_entry_gap_seconds:
            return
        if self.broker.name == "mt5":
            u = self._utc()
            if u.weekday() >= 5 or (u.weekday() == 4 and u.hour >= 20):
                return
        if not (cfg.trade_start_utc <= self._utc().hour < cfg.trade_end_utc):
            return
        # Work like a human: best entry first, then the next best, each one sized to the risk room
        # that is still free. A candidate that cannot be afforded is skipped, not forced.
        acct = dict(acct)                           # local copy: free margin shrinks as we open trades
        budget_total = acct["equity"] * cfg.max_total_open_risk_pct / 100
        for cand in self.scan_data["rankings"]:
            if len(self.tracked) >= cfg.max_positions:
                break
            if not cand["tradable"] or cand["symbol"] in {m["symbol"] for m in self.tracked.values()}:
                continue
            if self.sym_cooldown.get(cand["symbol"], 0) > now:
                continue
            usd = self._usd_dir(cand["symbol"], cand["side"])      # buying EUR/GBP/XAU = short USD
            if usd and sum(1 for m in self.tracked.values() if self._usd_dir(m["symbol"], m["side"]) == usd) >= cfg.max_same_usd_direction:
                continue
            jpy = self._jpy_dir(cand["symbol"], cand["side"])      # buying GBPJPY/EURJPY = short JPY
            if jpy and sum(1 for m in self.tracked.values() if self._jpy_dir(m["symbol"], m["side"]) == jpy) >= cfg.max_same_jpy_direction:
                continue
            room = budget_total - sum(m["risk_amount"] for m in self.tracked.values())
            self._execute(cand, acct, now, room)

    def _skip_note(self, symbol, text):
        """Explain a skipped entry in the activity log, at most once a minute per symbol."""
        if time.time() - self._skip_logged.get(symbol, 0) > 60:
            self._skip_logged[symbol] = time.time()
            self.log_event(f"{symbol}: skipped - {text}")

    def _execute(self, cand, acct, now, risk_room):
        s, d, plan = cand["symbol"], cand["direction"], cand["plan"]
        info = self.info(s)
        tick = self.broker.tick(s)
        if not tick:
            return False
        entry = tick["ask"] if d == 1 else tick["bid"]
        sl_dist, tp_dist = plan["sl_dist"], plan["tp_dist"]
        if abs(entry - plan["entry"]) > 0.3 * sl_dist or (tick["ask"] - tick["bid"]) > self.cfg.max_spread_to_sl * sl_dist:
            self.log_event(f"{s}: skipped - price moved/spread widened before entry; re-scanning")
            self.last_entry = now
            self.sym_cooldown[s] = now + 15
            self.last_scan_ts = 0                    # force a fresh plan on the next loop
            return False
        lots, risk_amt, why_not = size_within_budget(acct["equity"], sl_dist, info, self.cfg, risk_room)
        if lots <= 0:
            self._skip_note(s, why_not or "cannot size the position")
            return False
        margin = self.broker.margin_required(s, cand["side"], lots)
        if margin > acct["free_margin"] * 0.6:
            self._skip_note(s, f"not enough free margin for {lots} lots")
            return False
        nd = info["digits"]
        sl, tp = round(entry - d * sl_dist, nd), round(entry + d * tp_dist, nd)
        res = self.broker.send_market(s, cand["side"], lots, sl, tp, f"FB {cand['setup'][:12]}")
        self.last_entry = now
        if not res.get("ok"):
            self.log_event(f"{s}: order rejected - {res.get('msg')}", "warning")
            self.sym_cooldown[s] = now + 120
            return False
        ticket = res["ticket"]
        acct["free_margin"] = acct["free_margin"] - margin
        meta = dict(symbol=s, side=cand["side"], entry=res["price"], sl0=sl, risk_dist=sl_dist, open_ts=now,
                    setup=cand["setup"], score=cand["score"], risk_amount=risk_amt, lots=lots, be_done=False,
                    balance_before=acct["balance"], miss=0)
        self.tracked[ticket] = meta
        self.stats["opened"] += 1
        self.log_event(f"OPEN {cand['side']} {s} {lots} lots @ {res['price']} SL {sl} TP {tp} (score {cand['score']:.0f}, {cand['setup']})")
        self.rep.emit("TRADE_OPENED", dict(ticket=ticket, symbol=s, side=cand["side"], lots=lots, openPrice=res["price"],
                                           stopLoss=sl, takeProfit=tp, openTime=int(time.time()), score=cand["score"],
                                           setup=cand["setup"], reasons=cand["reasons"], balanceBefore=acct["balance"],
                                           riskAmount=round(risk_amt, 2), rr=cand["rr"]), self.session_id)
        return True

    # ------------------------------------------------------------------ position sync / management
    def _adopt_positions(self):
        for p in self.broker.positions():
            if p["ticket"] not in self.tracked:
                rd = abs(p["price_open"] - p["sl"]) if p["sl"] else 0
                self.tracked[p["ticket"]] = dict(symbol=p["symbol"], side=p["side"], entry=p["price_open"], sl0=p["sl"],
                                                 risk_dist=rd or 1e-9, open_ts=self._now(), setup="ADOPTED", score=0,
                                                 risk_amount=0, lots=p["volume"], be_done=False, balance_before=0, miss=0)

    def _sync_positions(self):
        live = {p["ticket"]: p for p in self.broker.positions()}
        for t in list(self.tracked):
            if t in live:
                self.tracked[t]["miss"] = 0
                continue
            m = self.tracked[t]
            summ = self.broker.deal_summary(t)
            m["miss"] += 1
            if summ is None and m["miss"] < 10:
                continue
            self._handle_closed(t, m, summ)
            del self.tracked[t]

    def _handle_closed(self, ticket, m, summ):
        acct = self.broker.account() or {"balance": 0}
        summ = summ or dict(close_price=m["entry"], profit=0, commission=0, swap=0, time=int(time.time()), reason="CLIENT")
        net = summ["profit"] + summ["commission"] + summ["swap"]
        reason = self.close_reason.pop(ticket, None)
        if not reason:
            if summ["reason"] == "TP": reason = f"Take profit hit (+${net:.2f})"
            elif summ["reason"] == "SL":
                reason = f"Break-even/trailing stop hit ({net:+.2f})" if m["be_done"] and net > -0.05 * max(m["risk_amount"], 0.01) else f"Stop loss hit (${net:.2f})"
            elif summ["reason"] == "SO": reason = "Stop-out by broker (margin)"
            else: reason = "Closed manually outside the bot"
        win = net > 0
        self.stats["closed"] += 1
        self.stats["wins" if win else "losses"] += 1
        self.stats["pnl"] += net
        now = self._now()
        if win:
            self.consec_losses = 0
        else:
            self.consec_losses += 1
            self.sym_cooldown[m["symbol"]] = now + self.cfg.symbol_cooldown_minutes * 60
            if self.consec_losses >= self.cfg.max_consecutive_losses:
                self.cooldown_until = now + self.cfg.cooldown_minutes * 60
                self.consec_losses = 0
                self.log_event(f"{self.cfg.max_consecutive_losses} losses in a row - cooling down {self.cfg.cooldown_minutes} min", "warning")
        if m["setup"] != "ADOPTED":
            self.perf.record(m["symbol"], m["setup"], win)
        self.log_event(f"CLOSE {m['symbol']} #{ticket}: {reason} -> net ${net:+.2f}", "info" if win else "warning")
        self.rep.emit("TRADE_CLOSED", dict(ticket=ticket, symbol=m["symbol"], closePrice=summ["close_price"], closeTime=int(time.time()),
                                           profit=summ["profit"], commission=summ["commission"], swap=summ["swap"], netProfit=net,
                                           closeReason=summ["reason"], remark=reason, balanceAfter=acct["balance"]), self.session_id)

    def _close(self, ticket, reason):
        self.close_reason[ticket] = reason
        r = self.broker.close_position(ticket)
        if not r.get("ok"):
            self.close_reason.pop(ticket, None)
            self.log_event(f"close #{ticket} failed: {r.get('msg')}", "warning")
        return r.get("ok")

    def _manage_positions(self):
        cfg, now = self.cfg, self._now()
        live = {p["ticket"]: p for p in self.broker.positions()}
        u = self._utc()
        for t, m in list(self.tracked.items()):
            p = live.get(t)
            if not p:
                continue
            s, side = m["symbol"], 1 if m["side"] == "BUY" else -1
            tick = self.broker.tick(s)
            if not tick:
                continue
            info = self.info(s)
            price = tick["bid"] if side == 1 else tick["ask"]
            rd = m["risk_dist"]
            r = (price - m["entry"]) * side / rd if rd else 0
            spread = tick["ask"] - tick["bid"]
            minutes = (now - m["open_ts"]) / 60

            if cfg.close_before_news and self.news.imminent(s, 3, time.time()):
                self._close(t, "Closed ahead of high-impact news"); continue
            if self.broker.name == "mt5" and u.weekday() == 4 and u.hour >= 21:
                self._close(t, "Closed before the weekend"); continue
            if minutes > cfg.max_trade_minutes and r < 0.5:
                self._close(t, f"Time stop after {minutes:.0f} min - no follow-through ({r:+.1f}R)"); continue
            f1 = self.md.frame(s, "M1")
            if f1 is not None and r >= 0.4:
                against = [x for x in st.candle_patterns(f1.df) if x[1] == -side and x[2] >= 0.8]
                if against and side * float(f1.df.macd_hist.iloc[-1]) < 0:
                    self._close(t, f"Momentum reversal ({against[0][0]}) - profit secured ({r:+.1f}R)"); continue
            new_sl = None
            if r >= cfg.trail_start_r:
                cand = price - side * 0.7 * rd
                if (cand - p["sl"]) * side > 0.1 * rd:
                    new_sl = cand
            if r >= cfg.break_even_r and not m["be_done"]:
                be = m["entry"] + side * (spread + 0.1 * rd)
                if (be - p["sl"]) * side > 0:
                    new_sl = be if new_sl is None or (be - new_sl) * side > 0 else new_sl
                m["be_done"] = True
            if new_sl is not None:
                new_sl = round(new_sl, info["digits"])
                if abs(price - new_sl) >= max(info.get("stops_level", 0) * info["point"], 0) * 1.2:
                    res = self.broker.modify_sltp(t, new_sl, None)
                    if res.get("ok"):
                        m["be_done"] = True
                        self.log_event(f"#{t} {s}: stop moved to {new_sl} ({r:+.1f}R)")

    def _halt(self, reason, day):
        self.log_event(f"HALT: {reason}", "critical")
        for t in list(self.tracked):
            self._close(t, f"Risk halt: {reason}")
        self.status, self.halt_reason, self.halt_day = "HALTED", reason, day
        self._sync_positions()
        self.alert("halt", "Trading halted by risk manager", reason, "CRITICAL", 600)

    # ------------------------------------------------------------------ status
    def status_dict(self):
        acct = self.broker.account() or {}
        return {"running": self.enabled, "status": self.status, "sessionId": self.session_id, "haltReason": self.halt_reason,
                "cooldownUntil": self.cooldown_until if self.cooldown_until > self._now() else None,
                "consecutiveLosses": self.consec_losses, "openPositions": len(self.tracked), "stats": self.stats,
                "account": acct, "broker": self.broker.status(), "activity": list(self.activity)[:25],
                "peakEquity": self.peak_equity, "mode": self.broker.name}
