import logging
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, WebSocket
from pydantic import BaseModel

from .bot import Bot
from .broker.mt5_link import hub
from .broker import get_broker
from .charts import chart_payload
from .config import SYMBOL_ALIASES, SYMBOLS, TIMEFRAMES, Settings, config_store
from .marketdata import MarketData
from .news import News
from .reporter import Reporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("engine")

broker = get_broker()
md = MarketData(broker)
news = News()
reporter = Reporter()
bot = Bot(broker, md, news, reporter, config_store)


def auth(x_api_key: Optional[str] = Header(default=None)):
    if x_api_key != Settings.api_key:
        raise HTTPException(401, "invalid api key")


app = FastAPI(title="ForexBot Engine", version="1.0")
router = APIRouter(dependencies=[Depends(auth)])


class StartReq(BaseModel):
    sessionId: Optional[int] = None


class StopReq(BaseModel):
    closePositions: bool = True


class ConnectReq(BaseModel):
    login: Optional[str] = None
    password: Optional[str] = None
    server: Optional[str] = None


@app.websocket("/mt5-bridge")
async def mt5_bridge(websocket: WebSocket):
    """The Windows PC dials out to here. The engine then calls MetaTrader over this socket."""
    await websocket.accept()
    key = websocket.headers.get("x-api-key", "")
    if key != Settings.api_key:
        await websocket.close(code=1008)
        return
    await hub.attach(websocket)


@app.get("/health")
def health():
    return {"ok": True, "mode": broker.name, "connected": broker.is_connected(), "running": bot.enabled,
            "symbols": list(SYMBOLS), "timeframes": list(TIMEFRAMES), "build": "2026-10-27-jpy-fix"}


@router.get("/bot/status")
def bot_status():
    return bot.status_dict()


@router.post("/bot/start")
def bot_start(req: StartReq):
    if bot.enabled:
        return bot.status_dict()
    try:
        return bot.start(req.sessionId)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post("/bot/stop")
def bot_stop(req: StopReq):
    return bot.stop(req.closePositions)


@router.post("/mt5/connect")
def mt5_connect(req: ConnectReq):
    res = broker.connect(req.login, req.password, req.server)
    md.cache.clear()
    return {**res, **broker.status()}


@router.get("/mt5/status")
def mt5_status():
    return broker.status()


@router.get("/account")
def account():
    a = broker.account()
    if a is None:
        raise HTTPException(503, "broker not connected")
    return a


_scan_gate = threading.Lock()


def _refresh_scan():
    if not _scan_gate.acquire(blocking=False):
        return
    try:
        bot.force_scan()
    except Exception:                                  # noqa: BLE001
        log.exception("background scan failed")
    finally:
        _scan_gate.release()


@router.get("/quotes")
def quotes():
    out = []
    for s in SYMBOLS:
        try:
            t = broker.tick(s)
        except Exception:                              # noqa: BLE001
            t = None
        if not t:
            out.append({"symbol": s, "bid": None, "ask": None, "spread": None, "digits": 5,
                        "changePct": None, "high": None, "low": None, "spark": []})
            continue
        # Candle history is large. The dashboard reads the cache; a scan fills it.
        f1 = md.peek(s, "M1")
        d1 = md.peek(s, "D1")
        try:
            info = broker.symbol_info(s)
        except Exception:                              # noqa: BLE001
            info = {"digits": 5}
        chg = None
        if d1 is not None and len(d1.raw):
            o = float(d1.raw["open"].iloc[-1])
            chg = (t["bid"] - o) / o * 100
        out.append({"symbol": s, "bid": t["bid"], "ask": t["ask"], "spread": t["spread"], "digits": info["digits"],
                    "changePct": chg, "high": float(d1.raw["high"].iloc[-1]) if d1 is not None else None,
                    "low": float(d1.raw["low"].iloc[-1]) if d1 is not None else None,
                    "spark": [float(x) for x in f1.df["close"].iloc[-40:]] if f1 is not None else []})
    return out


@router.get("/scan")
def scan():
    # A full scan downloads every timeframe from the laptop. Never do that
    # inside the dashboard request or the browser gives up and shows
    # "Cannot reach the server".
    stale = bot.scan_data is None or time.time() - (bot.last_scan_ts or 0) > 20
    if stale:
        threading.Thread(target=_refresh_scan, daemon=True).start()
    return bot.scan_data or {"rankings": [], "why": "Loading market data from MT5"}


@router.post("/scan/now")
def scan_now():
    return bot.force_scan()


def _canon_symbol(symbol: str) -> str:
    raw = (symbol or "").upper().replace("/", "").replace(".", "").replace("-", "").replace(" ", "")
    return SYMBOL_ALIASES.get(raw, raw)


def _canon_tf(tf: str) -> str:
    raw = (tf or "M5").upper()
    return {"1": "M1", "5": "M5", "10": "M10", "15": "M15", "30": "M30", "60": "H1",
            "1H": "H1", "4H": "H4", "1D": "D1", "D": "D1"}.get(raw, raw)


@router.get("/analysis/{symbol}")
def analysis(symbol: str, tf: str = "M5", bars: int = 150):
    symbol = _canon_symbol(symbol)
    tf = _canon_tf(tf)
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"unsupported symbol {symbol}. Use {', '.join(SYMBOLS)}")
    if tf not in TIMEFRAMES:
        raise HTTPException(400, f"unsupported timeframe {tf}. Use {', '.join(TIMEFRAMES)}")
    return chart_payload(symbol, tf, max(50, min(bars, 300)), md, broker, bot.scan_data)


@router.get("/news")
def get_news():
    return {"events": news.events(), "headlines": news.headlines(), "blocked": bot._news_state()}


@router.get("/config")
def get_config():
    return config_store.as_dict()


@router.put("/config")
def put_config(data: dict):
    return config_store.update(data)


@router.get("/positions")
def positions():
    live = broker.positions()
    for p in live:
        m = bot.tracked.get(p["ticket"], {})
        p["score"], p["setup"], p["riskAmount"] = m.get("score"), m.get("setup"), m.get("risk_amount")
    return live


@router.post("/positions/{ticket}/close")
def close_position(ticket: int):
    with bot.lock:
        if ticket in bot.tracked:
            bot.close_reason[ticket] = "Closed manually from the app"
        r = broker.close_position(ticket)
        if not r.get("ok"):
            bot.close_reason.pop(ticket, None)
            raise HTTPException(400, r.get("msg", "close failed"))
        if not bot.enabled:
            bot._sync_positions()
    return r


@router.post("/positions/close-all")
def close_all():
    n = 0
    with bot.lock:
        for p in broker.positions():
            bot.close_reason[p["ticket"]] = "Closed manually from the app"
            if broker.close_position(p["ticket"]).get("ok"):
                n += 1
    return {"closed": n}


app.include_router(router)
