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
from .risk import (lock_floor_r, size_within_budget, scalp_lot, basket_trade_count,
                   basket_profit_target, basket_protect_loss)

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
                if not frames:
                    ranks.append(self._pending_rank(s, "Waiting for market data from MT5"))
                    continue
                if not tick or tick.get("bid", 0) <= 0:
                    close = float(frames["M5"].df["close"].iloc[-1])
                    tick = dict(bid=close, ask=close, spread=0.0, time=0, stale=True)
                info = self.info(s)
                price = (tick["ask"] + tick["bid"]) / 2
                zones = st.sr_zones(frames, price, frames["H1"].atr)
                row = analyze_symbol(s, frames, tick, info, zones, cfg, self.perf, equity, self.news)
                if row is None:
                    ranks.append(self._pending_rank(s, "Waiting for enough candles on this pair"))
                    continue
                if tick.get("stale"):
                    row["tradable"] = False
                    row["blockedReasons"] = ["No live bid/ask yet from the broker"] + list(row.get("blockedReasons") or [])
                ranks.append(row)
            except Exception as e:              # noqa: BLE001
                log.warning("scan %s failed: %s", s, e, exc_info=True)
                ranks.append(self._pending_rank(s, f"Scan failed: {e}"))
        # Priority symbols (gold, GBPJPY, EURJPY) always come first; the others only after them.
        ranks.sort(key=lambda r: (0 if r["symbol"] in PRIORITY_SYMBOLS else 1, -r["rankScore"]))
        self._check_priority_affordability(ranks, equity)
        chosen = next((r for r in ranks if r.get("tradable") and r.get("plan")), None)
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

    @staticmethod
    def _pending_rank(symbol, reason):
        """Always keep every symbol on the ranking table, even when MT5 has no data yet."""
        return {
            "symbol": symbol, "direction": 0, "side": "WAIT", "score": 0, "rankScore": -1,
            "setup": "WAITING", "bias": 0, "price": None, "spread": None, "plan": None,
            "rr": 0, "lots": 0, "riskAmount": 0, "riskPctAtMinLot": 0,
            "components": {"htf": 0, "momentum": 0, "location": 0, "trigger": 0, "regime": 0, "volume": 0},
            "reasons": [], "penalties": [], "priority": symbol in PRIORITY_SYMBOLS,
            "accountFix": None,             "affordability": None, "tradable": False, "blockedReasons": [reason],
            "timeframes": {}, "htfLock": "WAIT", "story": reason,
        }

    def _check_priority_affordability(self, ranks, equity):
        """Explain sizing for priority symbols. Scalp mode uses fixed 0.01 baskets, not SL risk."""
        if not self.enabled or getattr(self.cfg, "scalp_mode", True):
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
        if not self.scan_data or time.time() - self.last_scan_ts > 30:
            return
        if now - self.last_entry < cfg.min_entry_gap_seconds:
            return
        if self.broker.name == "mt5":
            u = self._utc()
            if u.weekday() >= 5 or (u.weekday() == 4 and u.hour >= 20):
                return
        if not (cfg.trade_start_utc <= self._utc().hour < cfg.trade_end_utc):
            return
        if getattr(cfg, "scalp_mode", True):
            # One scalp basket at a time: bank it, then hunt the next entry.
            if self.tracked:
                return
            self._maybe_open_scalp_basket(dict(acct), now)
            return
        if len(self.tracked) >= cfg.max_positions:
            return
        acct = dict(acct)
        budget_total = acct["equity"] * cfg.max_total_open_risk_pct / 100
        for cand in self.scan_data["rankings"]:
            if len(self.tracked) >= cfg.max_positions:
                break
            if not cand.get("tradable") or not cand.get("plan") or cand["symbol"] in {m["symbol"] for m in self.tracked.values()}:
                continue
            if self.sym_cooldown.get(cand["symbol"], 0) > now:
                continue
            usd = self._usd_dir(cand["symbol"], cand["side"])
            if usd and sum(1 for m in self.tracked.values() if self._usd_dir(m["symbol"], m["side"]) == usd) >= cfg.max_same_usd_direction:
                continue
            jpy = self._jpy_dir(cand["symbol"], cand["side"])
            if jpy and sum(1 for m in self.tracked.values() if self._jpy_dir(m["symbol"], m["side"]) == jpy) >= cfg.max_same_jpy_direction:
                continue
            room = budget_total - sum(m["risk_amount"] for m in self.tracked.values())
            self._execute_legacy(cand, acct, now, room)

    def _maybe_open_scalp_basket(self, acct, now):
        """Open N×0.01 tickets on the best smart setup — no broker SL/TP."""
        cfg = self.cfg
        for cand in self.scan_data["rankings"]:
            if not cand.get("tradable") or not cand.get("plan"):
                continue
            if self.sym_cooldown.get(cand["symbol"], 0) > now:
                continue
            if self._open_scalp_basket(cand, acct, now):
                return

    def _open_scalp_basket(self, cand, acct, now):
        s, d, plan = cand["symbol"], cand["direction"], cand["plan"]
        info = self.info(s)
        tick = self.broker.tick(s)
        if not tick:
            return False
        atr = max(float(plan.get("sl_dist") or 0), 1e-9)   # build_plan still stores ATR-based distance
        spread = tick["ask"] - tick["bid"]
        entry = tick["ask"] if d == 1 else tick["bid"]
        max_spread_atr = float(getattr(self.cfg, "scalp_max_spread_atr", 0.22) or 0.22)
        if abs(entry - float(plan.get("entry") or entry)) > 0.55 * atr or spread > max_spread_atr * atr:
            self.log_event(f"{s}: skipped - price/spread moved before scalp basket; re-scanning")
            self.last_entry = now
            self.sym_cooldown[s] = now + 8
            self.last_scan_ts = 0
            return False

        lot = scalp_lot(info, self.cfg)
        want = int(plan.get("basketTickets") or basket_trade_count(acct["equity"], self.cfg))
        want = max(int(getattr(self.cfg, "scalp_min_tickets", 2)), min(want, int(getattr(self.cfg, "scalp_max_tickets", 30))))
        target = float(plan.get("basketTarget") or basket_profit_target(acct["equity"], want, self.cfg))
        protect = basket_protect_loss(acct["equity"], want, self.cfg)

        # Fit as many 0.01 tickets as free margin allows (keep ~35% free).
        opened = 0
        basket_id = f"{s}-{int(now)}"
        for i in range(want):
            margin = self.broker.margin_required(s, cand["side"], lot)
            if margin > acct["free_margin"] * 0.65:
                if opened == 0:
                    self._skip_note(s, f"not enough free margin for even one {lot:g} scalp ticket")
                    return False
                break
            res = self.broker.send_market(s, cand["side"], lot, 0, 0, f"SC {cand['setup'][:10]}")
            if not res.get("ok"):
                if opened == 0:
                    self.log_event(f"{s}: scalp order rejected - {res.get('msg')}", "warning")
                    self.sym_cooldown[s] = now + 60
                    self.last_entry = now
                    return False
                self.log_event(f"{s}: basket partial fill after {opened} tickets ({res.get('msg')})")
                break
            ticket = res["ticket"]
            acct["free_margin"] = max(0.0, acct["free_margin"] - margin)
            meta = dict(symbol=s, side=cand["side"], entry=res["price"], sl0=0.0, risk_dist=atr, open_ts=now,
                        setup=cand["setup"], score=cand["score"], risk_amount=0.0, lots=lot, be_done=False,
                        balance_before=acct["balance"], miss=0, peak_r=0.0, peak_profit=0.0,
                        basket_id=basket_id, basket_target=target, basket_protect=protect, scalp=True)
            self.tracked[ticket] = meta
            self.stats["opened"] += 1
            opened += 1
            self.rep.emit("TRADE_OPENED", dict(ticket=ticket, symbol=s, side=cand["side"], lots=lot, openPrice=res["price"],
                                               stopLoss=0, takeProfit=0, openTime=int(time.time()), score=cand["score"],
                                               setup=cand["setup"], reasons=cand["reasons"], balanceBefore=acct["balance"],
                                               riskAmount=0, rr=0, basketId=basket_id, basketTarget=target,
                                               mode="SCALP"), self.session_id)
        self.last_entry = now
        if opened:
            # Refresh target/protect to the tickets actually filled
            target = basket_profit_target(acct["equity"], opened, self.cfg)
            protect = basket_protect_loss(acct["equity"], opened, self.cfg)
            for m in self.tracked.values():
                if m.get("basket_id") == basket_id:
                    m["basket_target"] = target
                    m["basket_protect"] = protect
            self.log_event(
                f"SCALP OPEN {cand['side']} {s} ×{opened} @ {lot:g} (score {cand['score']:.0f}, "
                f"{cand['setup']}) — bank ${target:.2f}+ then exit; soft protect -${protect:.2f}")
            return True
        return False

    def _skip_note(self, symbol, text):
        """Explain a skipped entry in the activity log, at most once a minute per symbol."""
        if time.time() - self._skip_logged.get(symbol, 0) > 60:
            self._skip_logged[symbol] = time.time()
            self.log_event(f"{symbol}: skipped - {text}")

    def _execute_legacy(self, cand, acct, now, risk_room):
        """Legacy single-trade SL/TP path (only when scalp_mode is off)."""
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
            self.last_scan_ts = 0
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
                    balance_before=acct["balance"], miss=0, peak_r=0.0, peak_profit=0.0, scalp=False)
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
                scalp = not p.get("sl") and not p.get("tp")
                self.tracked[p["ticket"]] = dict(symbol=p["symbol"], side=p["side"], entry=p["price_open"], sl0=p["sl"] or 0,
                                                 risk_dist=rd or 1e-9, open_ts=self._now(), setup="ADOPTED", score=0,
                                                 risk_amount=0, lots=p["volume"], be_done=False, balance_before=0, miss=0,
                                                 peak_r=0.0, peak_profit=max(float(p.get("profit") or 0), 0.0),
                                                 scalp=scalp, basket_id=f"adopt-{p['symbol']}",
                                                 basket_target=float(getattr(self.cfg, "scalp_min_profit_usd", 1.5) or 1.5),
                                                 basket_protect=float(getattr(self.cfg, "scalp_protect_floor_usd", 2.5) or 2.5))

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
        if getattr(cfg, "scalp_mode", True) or any(m.get("scalp") for m in self.tracked.values()):
            self._manage_scalp_baskets(live, now, u)
            return
        self._manage_legacy_positions(live, now, u)

    def _close_tickets(self, tickets, reason):
        ok = True
        for t in tickets:
            if not self._close(t, reason):
                ok = False
        return ok

    def _manage_scalp_baskets(self, live, now, u):
        """Fast in/out: bank meaningful basket $ profit; soft-protect the account; never use broker SL/TP."""
        cfg = self.cfg
        # Group live tracked tickets by basket_id (fallback: symbol+side)
        groups = {}
        for t, m in list(self.tracked.items()):
            p = live.get(t)
            if not p:
                continue
            key = m.get("basket_id") or f"{m['symbol']}|{m['side']}"
            groups.setdefault(key, []).append((t, m, p))

        keep_pct = float(getattr(cfg, "scalp_giveback_keep_pct", 55.0) or 55.0) / 100.0
        for key, rows in groups.items():
            s = rows[0][1]["symbol"]
            side = 1 if rows[0][1]["side"] == "BUY" else -1
            profits = [float(p.get("profit") or 0) + float(p.get("swap") or 0) for _, _, p in rows]
            total = sum(profits)
            all_green = all(x > 0 for x in profits)
            tickets = [t for t, _, _ in rows]
            target = max(float(rows[0][1].get("basket_target") or getattr(cfg, "scalp_min_profit_usd", 1.5)),
                         float(getattr(cfg, "scalp_min_profit_usd", 1.5) or 1.5))
            protect = float(rows[0][1].get("basket_protect") or basket_protect_loss(
                (self.broker.account() or {}).get("equity", 100), len(rows), cfg))
            open_ts = min(m["open_ts"] for _, m, _ in rows)
            minutes = (now - open_ts) / 60
            peak = 0.0
            for _, m, p in rows:
                pr = float(p.get("profit") or 0)
                m["peak_profit"] = max(float(m.get("peak_profit") or 0), pr)
                peak = max(peak, float(m.get("peak_profit") or 0))
            # Track basket peak on the first meta row
            basket_peak = max(float(rows[0][1].get("basket_peak") or 0), total)
            for _, m, _ in rows:
                m["basket_peak"] = basket_peak

            if cfg.close_before_news and self.news.imminent(s, 3, time.time()):
                self._close_tickets(tickets, "Scalp basket closed ahead of high-impact news"); continue
            if self.broker.name == "mt5" and u.weekday() == 4 and u.hour >= 21:
                self._close_tickets(tickets, "Scalp basket closed before the weekend"); continue

            # Soft account protection — no fake broker stop-loss numbers
            if total <= -protect:
                self._close_tickets(tickets, f"Soft protect: basket loss ${total:.2f} hit -${protect:.2f} cap")
                continue

            # Primary scalp exit: every ticket green AND meaningful USD banked
            if all_green and total >= target:
                self._close_tickets(tickets, f"Scalp banked ${total:.2f} (target ${target:.2f}) — looking for next entry")
                continue

            # Don't give profit away: once we had a real run, lock most of it
            if basket_peak >= target and total > 0 and total < basket_peak * keep_pct:
                self._close_tickets(
                    tickets,
                    f"Scalp giveback lock: peak ${basket_peak:.2f} → ${total:.2f} (kept {keep_pct * 100:.0f}% rule)")
                continue

            # If peak was strong and we are still above target even if one ticket dipped, bank it
            if basket_peak >= target * 1.35 and total >= target:
                self._close_tickets(tickets, f"Scalp runner banked ${total:.2f} (peak ${basket_peak:.2f})")
                continue

            # Hard M5 flip against a flat/losing basket — get out fast
            f5 = self.md.frame(s, "M5")
            if f5 is not None and total < target * 0.5 and minutes >= 2:
                against = [x for x in st.candle_patterns(f5.df) if x[1] == -side and x[2] >= 0.85]
                if against and side * float(f5.df.macd_hist.iloc[-1]) < 0 and side * f5.struct.get("trend", 0) < -0.15:
                    self._close_tickets(tickets, f"M5 flip ({against[0][0]}) — abort scalp ${total:+.2f}")
                    continue

            # Dead basket: no follow-through
            if minutes > cfg.max_trade_minutes and total < target * 0.35 and basket_peak < target * 0.7:
                self._close_tickets(tickets, f"Scalp time-stop {minutes:.0f}m — no follow-through (${total:+.2f})")
                continue

    def _manage_legacy_positions(self, live, now, u):
        cfg = self.cfg
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
            profit = float(p.get("profit") or 0)
            m["peak_r"] = max(float(m.get("peak_r") or 0), r)
            m["peak_profit"] = max(float(m.get("peak_profit") or 0), profit)
            spread = tick["ask"] - tick["bid"]
            minutes = (now - m["open_ts"]) / 60
            peak = m["peak_r"]

            if cfg.close_before_news and self.news.imminent(s, 3, time.time()):
                self._close(t, "Closed ahead of high-impact news"); continue
            if self.broker.name == "mt5" and u.weekday() == 4 and u.hour >= 21:
                self._close(t, "Closed before the weekend"); continue
            if minutes > cfg.max_trade_minutes and r < 0.15 and peak < 0.55:
                self._close(t, f"Time stop after {minutes:.0f} min - no follow-through ({r:+.1f}R)"); continue
            f15 = self.md.frame(s, "M15")
            if f15 is not None and 0.35 <= r < 1.05 and peak < 1.15:
                against = [x for x in st.candle_patterns(f15.df) if x[1] == -side and x[2] >= 0.8]
                if against and side * float(f15.df.macd_hist.iloc[-1]) < 0 and side * f15.struct.get("trend", 0) < 0:
                    self._close(t, f"M15 reversal ({against[0][0]}) - locking {r:+.1f}R"); continue

            new_sl = None
            floor = lock_floor_r(peak)
            if floor is not None:
                locked = m["entry"] + side * floor * rd
                if (locked - p["sl"]) * side > 0.05 * rd:
                    new_sl = locked
                    m["be_done"] = True
            elif r >= cfg.break_even_r and not m["be_done"]:
                be = m["entry"] + side * (spread + 0.08 * rd)
                if (be - p["sl"]) * side > 0:
                    new_sl = be
                m["be_done"] = True
            if peak >= cfg.trail_start_r:
                f5 = self.md.frame(s, "M5")
                swing = None
                if f5 is not None:
                    pts = f5.lows[-3:] if side == 1 else f5.highs[-3:]
                    if pts:
                        levels = [px for _, px in pts]
                        swing = (max(levels) if side == 1 else min(levels)) - side * 0.15 * rd
                atr_trail = price - side * max(0.45 * rd, 0.8 * (f5.atr if f5 is not None else rd))
                cand = swing if swing is not None else atr_trail
                if floor is not None:
                    floor_px = m["entry"] + side * floor * rd
                    cand = floor_px if (cand - floor_px) * side < 0 else cand
                if (cand - (new_sl if new_sl is not None else p["sl"])) * side > 0.08 * rd:
                    new_sl = cand
            if new_sl is not None:
                new_sl = round(new_sl, info["digits"])
                if abs(price - new_sl) >= max(info.get("stops_level", 0) * info["point"], 0) * 1.2:
                    res = self.broker.modify_sltp(t, new_sl, None)
                    if res.get("ok"):
                        m["be_done"] = True
                        self.log_event(f"#{t} {s}: profit locked at {new_sl} (now {r:+.1f}R, peak {peak:+.1f}R)")

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
                "peakEquity": self.peak_equity, "mode": self.broker.name,
                "strategy": "SCALP_BASKET" if getattr(self.cfg, "scalp_mode", True) else "CLASSIC",
                "scalp": {"lot": getattr(self.cfg, "scalp_lot", 0.01),
                          "minProfit": getattr(self.cfg, "scalp_min_profit_usd", 1.5),
                          "openBaskets": len({m.get("basket_id") for m in self.tracked.values() if m.get("basket_id")})}}
