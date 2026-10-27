"""Connects this PC's MetaTrader 5 out to the cloud engine.

The server cannot open a port into a home network. This script dials the
server instead, then answers MT5 calls on that connection.

Leave MetaTrader 5 open and logged in, with Algo Trading green.
Leave this process running.

Order handling (the part that used to fail with
    order_send returned None: (-2, 'Unnamed arguments not allowed')):
  * The MetaTrader5 package only accepts order_send / order_check with the
    request passed as KEYWORDS. A positional dict is rejected before the
    terminal ever sees the order. Whatever the engine sends (dict, keywords,
    request=), this bridge always calls the terminal with keywords.
  * Request values are coerced to plain int / float / str.
  * The symbol is mapped to this broker's own spelling (EURUSD, EURUSDm,
    EURUSD.a, GOLD ...) if the exact name does not exist.
  * If the broker refuses the filling mode, the other modes are tried.
"""
import asyncio
import inspect
import json
import os
import sys
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import websockets

SERVER = os.environ.get("MT5_BRIDGE_URL", "ws://145.241.187.174:8088/mt5-bridge")
DEFAULT_KEY = "a293bc338ba95dbd8bcfb55aa4ab99a13f51351f712d034c"

print(f"MetaTrader5 {getattr(mt5, '__version__', '?')}, numpy {np.__version__}, python {sys.version.split()[0]}")

INT_FIELDS = ("action", "magic", "order", "type", "type_filling", "type_time", "deviation",
              "expiration", "position", "position_by")
FLOAT_FIELDS = ("volume", "price", "stoplimit", "sl", "tp")
STR_FIELDS = ("symbol", "comment")
RETCODE_BAD_FILLING = 10030

_last_error = {"value": None}


def api_key():
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ENGINE_API_KEY=") and not line.startswith("ENGINE_API_KEY=#"):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return os.environ.get("ENGINE_API_KEY", DEFAULT_KEY)


def pack(obj):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        if obj.dtype.names:
            rows = []
            for row in obj.tolist():
                rows.append({name: pack(val) for name, val in zip(obj.dtype.names, row)})
            return rows
        return [pack(v) for v in obj.tolist()]
    if hasattr(obj, "_asdict"):
        return {k: pack(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): pack(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [pack(v) for v in obj]
    return str(obj)


# --------------------------------------------------------------------- order requests
def _clean_request(request):
    """Plain python types only; drop empty values the terminal does not want."""
    out = {}
    for key, value in request.items():
        if value is None:
            continue
        if key in INT_FIELDS:
            out[key] = int(value)
        elif key in FLOAT_FIELDS:
            out[key] = float(value)
        elif key in STR_FIELDS:
            out[key] = str(value)
        else:
            out[key] = value
    return out


def _resolve_symbol(name):
    """Return the symbol spelling this broker uses for `name`."""
    if not name:
        return name
    try:
        if mt5.symbol_info(name) is not None:
            mt5.symbol_select(name, True)
            return name
        names = [s.name for s in (mt5.symbols_get() or [])]
    except Exception:  # noqa: BLE001
        return name
    base = name.upper()
    for suffix in ("M", ".A", ".PRO", ".R", ".ECN", "_", "#", "."):
        if base.endswith(suffix) and len(base) > len(suffix) + 3:
            base = base[: -len(suffix)]
            break
    alias = "GOLD" if base == "XAUUSD" else ("SILVER" if base == "XAGUSD" else None)
    extras = []
    if base in ("GBPJPY", "EURJPY", "EURUSD", "GBPUSD", "XAUUSD"):
        extras = [base + s for s in ("m", "M", ".m", ".", "#", ".a", "micro")]
    for cand in [base, alias, *extras]:
        if not cand:
            continue
        try:
            info = mt5.symbol_info(cand)
        except Exception:  # noqa: BLE001
            info = None
        if info is not None:
            pick = getattr(info, "name", cand)
            mt5.symbol_select(pick, True)
            print(f"Symbol {name} mapped to {pick}")
            return pick
    for stem in (base, alias, *extras):
        if not stem:
            continue
        exact = [s for s in names if s.upper() == stem]
        near = sorted((s for s in names if s.upper().startswith(stem)), key=len)
        pick = (exact or near or [None])[0]
        if pick:
            mt5.symbol_select(pick, True)
            print(f"Symbol {name} mapped to {pick}")
            return pick
    return name


def _fill_candidates(first):
    modes = [first]
    for mode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        if mode not in modes:
            modes.append(mode)
    return modes


def _call_terminal(fn, method, request):
    """MetaTrader5 wants keywords. Older builds wanted a dict. Try keywords first,
    and only fall back when the terminal says the call style itself is wrong."""
    first_error = None
    for label, call in (("keywords", lambda: fn(**request)),
                        ("dict", lambda: fn(request)),
                        ("request=", lambda: fn(request=request))):
        try:
            result = call()
        except TypeError as e:
            print(f"{method} style '{label}' not accepted: {e}")
            continue
        if result is not None:
            return result
        err = mt5.last_error()
        if first_error is None:
            first_error = err
        if err and err[0] != -2:       # a real failure, not a call-style problem: do not mask it
            break
        print(f"{method} style '{label}' returned None, last_error={err}")
    _last_error["value"] = first_error or mt5.last_error()
    print(f"{method} failed. last_error={_last_error['value']} Request: {request}")
    return None


def _send_request(fn, method, request):
    request = _clean_request(request)
    if "symbol" in request:
        request["symbol"] = _resolve_symbol(request["symbol"])
    result = _call_terminal(fn, method, request)
    if result is not None and getattr(result, "retcode", None) == RETCODE_BAD_FILLING and "type_filling" in request:
        for mode in _fill_candidates(request["type_filling"])[1:]:
            retry = _call_terminal(fn, method, dict(request, type_filling=mode))
            if retry is not None and retry.retcode != RETCODE_BAD_FILLING:
                print(f"{method}: broker accepted filling mode {mode}")
                return retry
    return result


def dispatch(method, args, kwargs):
    if method == "__lookup__":
        obj = getattr(mt5, args[0])
        return {"callable": callable(obj), "value": None if callable(obj) else pack(obj)}
    if method == "last_error" and _last_error["value"] is not None:
        err, _last_error["value"] = _last_error["value"], None
        return pack(err)
    fn = getattr(mt5, method)
    if method in ("order_send", "order_check"):
        request = None
        if len(args) == 1 and isinstance(args[0], dict):
            request = args[0]
        elif not args and isinstance(kwargs.get("request"), dict):
            request = kwargs["request"]
        elif kwargs and not args:
            request = kwargs
        if request is not None:
            _last_error["value"] = None
            return pack(_send_request(fn, method, request))
    return pack(fn(*args, **kwargs))


async def serve():
    key = api_key()
    headers = {"X-Api-Key": key}
    while True:
        try:
            print(f"Connecting to {SERVER} ...")
            params = {"ping_interval": 20, "ping_timeout": 30, "max_size": 20_000_000}
            if "additional_headers" in inspect.signature(websockets.connect).parameters:
                params["additional_headers"] = headers
            else:
                params["extra_headers"] = headers
            async with websockets.connect(SERVER, **params) as ws:
                print("Connected to the server. Leave this window open.")
                print("Leave MetaTrader 5 open, logged in, with Algo Trading green.")
                async for raw in ws:
                    req = json.loads(raw)
                    try:
                        result = await asyncio.to_thread(dispatch, req["method"], req.get("args") or [], req.get("kwargs") or {})
                        await ws.send(json.dumps({"id": req["id"], "ok": True, "result": result}))
                    except Exception as e:  # noqa: BLE001
                        await ws.send(json.dumps({
                            "id": req.get("id"),
                            "ok": False,
                            "error": f"{type(e).__name__}: {e}",
                        }))
        except Exception as e:  # noqa: BLE001
            print(f"Not connected ({type(e).__name__}: {e}). Retrying in 5 seconds.")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(serve())
