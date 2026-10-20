"""Silent launcher for mt5_bridge.py (runs under pythonw, no window).
Logs to C:\\MT5Bridge\\logs\\bridge.log and allows only one copy at a time."""
import asyncio
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler

BASE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)

handler = RotatingFileHandler(os.path.join(BASE, "logs", "bridge.log"),
                              maxBytes=1_000_000, backupCount=3, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log = logging.getLogger("bridge")
log.setLevel(logging.INFO)
log.addHandler(handler)


class LogStream:
    def write(self, text):
        text = text.strip()
        if text:
            log.info(text)

    def flush(self):
        pass


sys.stdout = sys.stderr = LogStream()

# single-instance guard
_lock = socket.socket()
try:
    _lock.bind(("127.0.0.1", 18999))
except OSError:
    log.info("Bridge already running, exiting this copy.")
    sys.exit(0)

sys.path.insert(0, os.path.join(BASE, "scripts"))
import mt5_bridge  # noqa: E402

log.info("Bridge service starting")
try:
    asyncio.run(mt5_bridge.serve())
except Exception as e:  # noqa: BLE001
    log.info(f"Bridge crashed: {type(e).__name__}: {e}")
    sys.exit(1)  # non-zero exit makes Task Scheduler restart it
