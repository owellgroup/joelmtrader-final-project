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

import subprocess
import sys
from importlib import metadata


def _ensure_numpy_1x():
    """MetaTrader5 5.0.x is built against numpy 1.x. With numpy 2.x every order_send fails with
    (-2, 'Unnamed arguments not allowed'), while reading prices still works. Downgrade before importing it."""
    try:
        major = int(metadata.version("numpy").split(".")[0])
    except Exception:  # noqa: BLE001
        return
    if major < 2:
        return
    print("numpy 2.x found. MetaTrader5 cannot place orders with it. Installing numpy<2 ...")
    exe = sys.executable
    py = os.path.join(os.path.dirname(exe), "python.exe")
    if os.path.exists(py):
        exe = py
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run([exe, "-m", "pip", "install", "numpy>=1.26,<2"], check=False, creationflags=flags)


_ensure_numpy_1x()

import MetaTrader5 as mt5  # noqa: E402
import numpy as np  # noqa: E402
import websockets  # noqa: E402

print(f"MetaTrader5 {getattr(mt5, '__version__', '?')}, numpy {np.__version__}")
if int(np.__version__.split(".")[0]) >= 2:
    print("WARNING: numpy 2.x is still installed. Orders will fail. Run: pip install \"numpy<2\"")

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
    if method in ("order_send", "order_check"):
        request = args[0] if len(args) == 1 and isinstance(args[0], dict) else (kwargs if kwargs and not args else None)
        if request is not None:
            return pack(_send_request(fn, method, request))
    return pack(fn(*args, **kwargs))


def _send_request(fn, method, request):
    """Different MetaTrader5 builds want the request as a dict, as keywords, or as request=dict.
    Try each style until the terminal answers; print what failed so the cause is visible."""
    styles = (("keywords", lambda: fn(**request)),
              ("dict", lambda: fn(request)),
              ("request=", lambda: fn(request=request)))
    for label, call in styles:
        try:
            result = call()
        except TypeError as e:
            print(f"{method} style '{label}' not accepted: {e}")
            continue
        if result is not None:
            return result
        print(f"{method} style '{label}' returned None, last_error={mt5.last_error()}")
    print(f"{method} failed in every call style. MetaTrader5 {getattr(mt5, '__version__', '?')}, "
          f"numpy {np.__version__}, python {sys.version.split()[0]}. Request: {request}")
    return None


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
