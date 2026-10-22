"""Central configuration: environment settings + live-editable risk configuration."""
import json
import os
import threading
from dataclasses import dataclass, field, asdict, fields

PRIORITY_SYMBOLS = ["XAUUSD", "GBPJPY", "EURJPY"]               # always checked (and traded) first
OTHER_SYMBOLS = ["EURUSD", "GBPUSD"]
SYMBOLS = PRIORITY_SYMBOLS + OTHER_SYMBOLS                        # scan order: priority first
LEGACY_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]                   # what older saved settings knew about
USD_QUOTED = {"XAUUSD", "EURUSD", "GBPUSD"}                       # long = short USD
JPY_CROSSES = {"GBPJPY", "EURJPY"}                                # long = short JPY
TIMEFRAMES = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}

DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)


def env(name, default=None):
    v = os.getenv(name)
    return v if v not in (None, "") else default


class Settings:
    broker_mode = env("BROKER_MODE", "mt5").lower()            # paper | mt5
    api_key = env("ENGINE_API_KEY", "a293bc338ba95dbd8bcfb55aa4ab99a13f51351f712d034c")
    events_url = env("JAVA_EVENTS_URL", "http://api:8080/internal/events")
    internal_key = env("INTERNAL_API_KEY", "f262fe05a3c754a7aa5f5457ad3b4f5fabfe9487fb2b4adc")
    mt5_login = env("MT5_LOGIN")
    mt5_password = env("MT5_PASSWORD")
    mt5_server = env("MT5_SERVER")
    mt5_path = env("MT5_PATH")                                  # Windows: path to terminal64.exe (optional)
    mt5_rpyc_host = env("MT5_RPYC_HOST", "")                    # public IP of the Windows PC running the MT5 desktop
    mt5_rpyc_port = int(env("MT5_RPYC_PORT", "18812"))
    symbol_suffix = env("SYMBOL_SUFFIX", "")                    # e.g. "m" for EURUSDm
    magic = int(env("MAGIC_NUMBER", "26101801"))
    paper_balance = float(env("PAPER_BALANCE", "12"))
    paper_speed = float(env("PAPER_SPEED", "1"))
    paper_commission_per_lot = float(env("PAPER_COMMISSION_PER_LOT", "6"))
    loop_seconds = float(env("LOOP_SECONDS", "2"))
    scan_seconds_running = float(env("SCAN_SECONDS", "5"))
    scan_seconds_idle = float(env("SCAN_SECONDS_IDLE", "20"))


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 2.0         # % of equity risked per trade
    micro_max_risk_pct: float = 7.0         # hard cap when the broker's minimum lot forces more risk
    max_total_open_risk_pct: float = 8.0    # sum of risk of all open trades
    max_positions: int = 3
    max_same_usd_direction: int = 2         # correlation guard (EURUSD/GBPUSD/XAUUSD all share USD)
    max_same_jpy_direction: int = 2         # correlation guard (GBPJPY/EURJPY share JPY)
    daily_loss_limit_pct: float = 8.0       # halts trading until next UTC day
    max_drawdown_pct: float = 25.0          # from session peak equity -> kill switch
    max_consecutive_losses: int = 3
    cooldown_minutes: int = 15
    symbol_cooldown_minutes: int = 5
    min_score: float = 62.0                 # minimum opportunity score (0-100)
    min_rr: float = 1.5                     # minimum net reward:risk
    max_spread_to_sl: float = 0.25          # spread must be <= 25% of the stop distance
    news_before_min: int = 30
    news_after_min: int = 15
    break_even_r: float = 0.8
    trail_start_r: float = 1.2
    max_trade_minutes: int = 45
    trade_start_utc: int = 6
    trade_end_utc: int = 20
    close_before_news: bool = True
    min_entry_gap_seconds: int = 20
    allowed_symbols: list = field(default_factory=lambda: list(SYMBOLS))
    known_symbols: list = field(default_factory=lambda: list(SYMBOLS))   # symbols the saved settings already knew about


class ConfigStore:
    path = os.path.join(DATA_DIR, "risk_config.json")

    def __init__(self):
        self._lock = threading.Lock()
        self.cfg = RiskConfig()
        try:
            with open(self.path) as f:
                self.update(json.load(f), persist=False)
        except Exception:
            pass

    def update(self, data: dict, persist=True):
        with self._lock:
            kinds = {f.name: f.type for f in fields(RiskConfig)}
            data = dict(data or {})
            if "allowed_symbols" in data:
                # Settings saved before a symbol existed do not list it. Switch new symbols ON once,
                # then respect whatever the user chooses afterwards (known_symbols records what they saw).
                known = data.get("known_symbols")
                known = LEGACY_SYMBOLS if known is None else known
                allowed = list(data["allowed_symbols"] or [])
                data["allowed_symbols"] = allowed + [s for s in SYMBOLS if s not in known and s not in allowed]
                data["known_symbols"] = list(SYMBOLS)
            for k, v in data.items():
                if k not in kinds:
                    continue
                cur = getattr(self.cfg, k)
                try:
                    if isinstance(cur, bool):
                        v = bool(v)
                    elif isinstance(cur, int):
                        v = int(float(v))
                    elif isinstance(cur, float):
                        v = float(v)
                    elif isinstance(cur, list):
                        v = [s for s in v if s in SYMBOLS]
                except Exception:
                    continue
                setattr(self.cfg, k, v)
            if persist:
                try:
                    with open(self.path, "w") as f:
                        json.dump(asdict(self.cfg), f, indent=2)
                except Exception:
                    pass
        return asdict(self.cfg)

    def as_dict(self):
        return asdict(self.cfg)


config_store = ConfigStore()
