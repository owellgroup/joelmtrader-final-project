"""Connects this PC's MetaTrader 5 out to the cloud engine.

The server cannot open a port into a home network. This script dials the
server instead, then answers MT5 calls on that connection.

Leave MetaTrader 5 open and logged in, with Algo Trading green.
Leave this process running.
"""
import asyncio
import inspect
import json
import os
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import websockets

SERVER = os.environ.get("MT5_BRIDGE_URL", "ws://145.241.187.174:8088/mt5-bridge")
DEFAULT_KEY = "a293bc338ba95dbd8bcfb55aa4ab99a13f51351f712d034c"


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


def dispatch(method, args, kwargs):
    if method == "__lookup__":
        obj = getattr(mt5, args[0])
        return {"callable": callable(obj), "value": None if callable(obj) else pack(obj)}
    fn = getattr(mt5, method)
    # order_send/order_check on MetaTrader5 5.0.5735+ are keyword-only.
    # A positional request dict fails with (-2, 'Unnamed arguments not allowed').
    if method in ("order_send", "order_check") and len(args) == 1 and isinstance(args[0], dict) and not kwargs:
        try:
            return pack(fn(**args[0]))
        except TypeError:
            return pack(fn(*args))
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
