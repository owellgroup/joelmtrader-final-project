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
TIMEFRAMES = ["D1", "H4", "H1", "M30", "M15", "M10", "M5", "M1"]
TF_SECONDS = {"M1": 60, "M5": 300, "M10": 600, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
SYMBOL_ALIASES = {"GOLD": "XAUUSD", "XAU": "XAUUSD", "XAUUSDM": "XAUUSD"}
UNIVERSE_VERSION = 2                                              # bump when the live symbol list changes
SCALP_MODE_VERSION = 3                                            # bump when default scalp risk profile changes

# Broker spellings we try before giving up (Headway, XM, IC Markets, Exness, …)
BROKER_NAME_TRIES = {
    "XAUUSD": ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.m", "XAUUSD.", "XAUUSD#", "XAUUSD.a", "XAUUSD.pro"],
    "GBPJPY": ["GBPJPY", "GBPJPYm", "GBPJPY.m", "GBPJPY.", "GBPJPY#", "GBPJPY.a", "GBPJPYmicro", "GBP/JPY"],
    "EURJPY": ["EURJPY", "EURJPYm", "EURJPY.m", "EURJPY.", "EURJPY#", "EURJPY.a", "EURJPYmicro", "EUR/JPY"],
    "EURUSD": ["EURUSD", "EURUSDm", "EURUSD.m", "EURUSD.", "EURUSD#", "EURUSD.a", "EURUSDmicro"],
    "GBPUSD": ["GBPUSD", "GBPUSDm", "GBPUSD.m", "GBPUSD.", "GBPUSD#", "GBPUSD.a", "GBPUSDmicro"],
}

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
    # ---- scalp basket mode (no classic SL/TP on orders) ----
    scalp_mode: bool = True                 # bulk 0.01 tickets; exit on basket $ profit
    scalp_lot: float = 0.01                 # every ticket uses this lot size
    scalp_equity_per_ticket: float = 22.0   # ~1 ticket per this many $ of equity
    scalp_min_tickets: int = 2
    scalp_max_tickets: int = 30
    scalp_min_profit_usd: float = 1.5       # bank at least this much basket profit
    scalp_profit_per_ticket: float = 0.12   # scales target with basket size
    scalp_profit_equity_pct: float = 0.15   # soft target floor vs equity
    scalp_protect_pct: float = 1.8          # soft emergency close if basket loss ≥ this % equity
    scalp_protect_floor_usd: float = 2.5
    scalp_protect_per_ticket: float = 0.35
    scalp_giveback_keep_pct: float = 55.0   # if peak hit target, close when only this % of peak remains
    scalp_max_spread_atr: float = 0.55      # legacy/unused as hard gate; pip ceilings decide
    scalp_mode_version: int = 0

    # ---- shared guards / analysis ----
    risk_per_trade_pct: float = 2.0         # legacy (charts); unused for scalp lot sizing
    micro_max_risk_pct: float = 7.0
    max_total_open_risk_pct: float = 8.0
    max_positions: int = 40                 # room for a full scalp basket
    max_same_usd_direction: int = 2
    max_same_jpy_direction: int = 2
    daily_loss_limit_pct: float = 8.0
    max_drawdown_pct: float = 25.0
    max_consecutive_losses: int = 4
    cooldown_minutes: int = 10
    symbol_cooldown_minutes: int = 3
    min_score: float = 63.0                 # quality floor for well-calculated scalps
    min_rr: float = 0.0                     # unused in scalp mode (no TP/SL)
    max_spread_to_sl: float = 0.20          # legacy path only
    news_before_min: int = 30
    news_after_min: int = 15
    break_even_r: float = 0.6
    trail_start_r: float = 1.0
    max_trade_minutes: int = 25             # dead basket time-stop (minutes)
    universe_version: int = 0
    trade_start_utc: int = 6
    trade_end_utc: int = 20
    close_before_news: bool = True
    min_entry_gap_seconds: int = 5          # fast re-entry after a banked basket
    allowed_symbols: list = field(default_factory=lambda: list(SYMBOLS))
    known_symbols: list = field(default_factory=lambda: list(SYMBOLS))


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
        self._ensure_universe()
        self._ensure_scalp_mode()

    def _ensure_universe(self):
        """Older saves listed only EURUSD/GBPUSD/XAUUSD, or marked JPY as 'known' then left them off.
        One migration turns every live symbol back on so GBPJPY and EURJPY are analysed and tradable."""
        ver = int(getattr(self.cfg, "universe_version", 0) or 0)
        if ver >= UNIVERSE_VERSION:
            return
        allowed = list(self.cfg.allowed_symbols or [])
        for s in SYMBOLS:
            if s not in allowed:
                allowed.append(s)
        self.update({"allowed_symbols": allowed, "known_symbols": list(SYMBOLS),
                     "universe_version": UNIVERSE_VERSION}, persist=True)

    def _ensure_scalp_mode(self):
        """One-time migrate saved risk settings onto the scalp basket profile."""
        ver = int(getattr(self.cfg, "scalp_mode_version", 0) or 0)
        if ver >= SCALP_MODE_VERSION:
            return
        self.update({
            "scalp_mode": True,
            "scalp_lot": 0.01,
            "scalp_equity_per_ticket": 22.0,
            "scalp_min_tickets": 2,
            "scalp_max_tickets": 30,
            "scalp_min_profit_usd": 1.5,
            "scalp_profit_per_ticket": 0.12,
            "scalp_profit_equity_pct": 0.15,
            "scalp_protect_pct": 1.8,
            "scalp_protect_floor_usd": 2.5,
            "scalp_protect_per_ticket": 0.35,
            "scalp_giveback_keep_pct": 55.0,
            "scalp_max_spread_atr": 0.55,
            "max_positions": 40,
            "min_score": 63.0,
            "min_rr": 0.0,
            "max_trade_minutes": 25,
            "min_entry_gap_seconds": 5,
            "max_consecutive_losses": 4,
            "cooldown_minutes": 10,
            "symbol_cooldown_minutes": 3,
            "scalp_mode_version": SCALP_MODE_VERSION,
        }, persist=True)

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
