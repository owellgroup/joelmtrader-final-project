"""Economic calendar (high-impact event avoidance) + market headlines."""
import logging
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

log = logging.getLogger("news")
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEEDS = ["https://www.fxstreet.com/rss/news", "https://www.forexlive.com/feed/news"]
RELEVANT = {"XAUUSD": ["USD"], "EURUSD": ["USD", "EUR"], "GBPUSD": ["USD", "GBP"],
            "GBPJPY": ["GBP", "JPY"], "EURJPY": ["EUR", "JPY"]}
WATCHED = {"USD", "EUR", "GBP", "JPY"}
KEYWORDS = {"XAUUSD": ["gold", "xau", "bullion", "fed", "dollar", "treasury", "inflation", "cpi", "nfp", "powell"],
            "EURUSD": ["eur", "euro", "ecb", "dollar", "fed", "eurozone", "lagarde"],
            "GBPUSD": ["gbp", "pound", "sterling", "boe", "bank of england", "dollar", "fed", "uk "],
            "GBPJPY": ["gbp", "pound", "sterling", "boe", "bank of england", "jpy", "yen", "boj", "bank of japan", "ueda", "japan"],
            "EURJPY": ["eur", "euro", "ecb", "lagarde", "eurozone", "jpy", "yen", "boj", "bank of japan", "ueda", "japan"]}


class News:
    def __init__(self):
        self._events, self._headlines = [], []
        self._cal_ts = self._rss_ts = 0
        self._lock = threading.Lock()
        self._busy = False

    # --------------------------------------------------------- refresh
    def _refresh(self):
        try:
            if time.time() - self._cal_ts > 900:
                r = requests.get(CALENDAR_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                if r.ok:
                    ev = []
                    for e in r.json():
                        try:
                            dt = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
                        except Exception:       # noqa: BLE001
                            continue
                        ev.append({"title": e.get("title", ""), "currency": e.get("country", ""), "impact": e.get("impact", ""),
                                   "time": int(dt.timestamp()), "forecast": e.get("forecast", ""), "previous": e.get("previous", "")})
                    self._events = sorted(ev, key=lambda x: x["time"])
                self._cal_ts = time.time()
            if time.time() - self._rss_ts > 600:
                items = []
                for url in FEEDS:
                    try:
                        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                        root = ET.fromstring(r.content)
                        for it in root.iter("item"):
                            title = (it.findtext("title") or "").strip()
                            if not title:
                                continue
                            try:
                                from email.utils import parsedate_to_datetime
                                ts = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp())
                            except Exception:   # noqa: BLE001
                                ts = int(time.time())
                            items.append({"title": title, "link": it.findtext("link") or "", "time": ts,
                                          "source": url.split("/")[2]})
                    except Exception as ex:     # noqa: BLE001
                        log.debug("feed %s failed: %s", url, ex)
                if items:
                    self._headlines = sorted(items, key=lambda x: -x["time"])[:60]
                self._rss_ts = time.time()
        except Exception as e:                      # noqa: BLE001
            log.debug("news refresh failed: %s", e)
            self._cal_ts = self._rss_ts = time.time() - 600     # retry in a few minutes
        finally:
            self._busy = False

    def _kick(self):
        if self._busy or (time.time() - self._cal_ts < 900 and time.time() - self._rss_ts < 600):
            return
        self._busy = True
        threading.Thread(target=self._refresh, daemon=True).start()

    # --------------------------------------------------------- queries
    def events(self, hours_ahead=72, hours_back=6):
        self._kick()
        now = time.time()
        return [e for e in self._events if now - hours_back * 3600 <= e["time"] <= now + hours_ahead * 3600
                and e["impact"] in ("High", "Medium") and e["currency"] in WATCHED]

    def headlines(self, limit=30):
        self._kick()
        out = []
        for h in self._headlines:
            tags = [s for s, kws in KEYWORDS.items() if any(k in h["title"].lower() for k in kws)]
            out.append({**h, "symbols": tags})
        rel = [h for h in out if h["symbols"]]
        return (rel + [h for h in out if not h["symbols"]])[:limit]

    def blocked(self, symbol, cfg, now=None):
        """(blocked?, reason) - high impact event for a relevant currency within [-after, +before] minutes."""
        self._kick()
        now = now or time.time()
        for e in self._events:
            if e["impact"] != "High" or e["currency"] not in RELEVANT[symbol]:
                continue
            if -cfg.news_after_min * 60 <= e["time"] - now <= cfg.news_before_min * 60:
                mins = (e["time"] - now) / 60
                when = f"in {mins:.0f} min" if mins > 0 else f"{-mins:.0f} min ago"
                return True, f"High-impact news: {e['currency']} {e['title']} {when}"
        return False, ""

    def imminent(self, symbol, minutes=3, now=None):
        now = now or time.time()
        for e in self._events:
            if e["impact"] == "High" and e["currency"] in RELEVANT[symbol] and 0 <= e["time"] - now <= minutes * 60:
                return e
        return None
