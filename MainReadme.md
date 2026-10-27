# WayaSpot FX Bot — XAUUSD · EURUSD · GBPUSD auto-trader

A complete, self-hosted trading system:

| Part | Tech | Folder |
|---|---|---|
| **API** – login, admins, trades, ledger, e-mails, bot control | Java 17 · Spring Boot 3 · PostgreSQL | `backend/api` |
| **Engine** – market scan, analysis, risk, order execution via MetaTrader 5 | Python 3.12 · FastAPI · pandas | `backend/engine` |
| **App** – Windows / Web / Android dashboard (white + black theme) | Flutter | `frontend` |

```
 Flutter app ──HTTPS──► Spring Boot API ──HTTP (internal)──► Python engine ──► MetaTrader 5 ──► your broker
 (Windows/Web/Mobile)       │  ▲                                  │
                            ▼  └────── events (trades, scans) ────┘
                        PostgreSQL            Resend SMTP (e-mails)
```

When you press **Trade Now**: app → API (`/api/bot/start`) → engine starts its loop → the engine analyses all 3 pairs, picks
the best, sizes the position, and sends the order to **your MT5 account**. It keeps doing this until you press **Stop trade**.
If the engine/server restarts, a watchdog in the API restarts the loop automatically while a session is "running".

---

## 0. Read this first (honest expectations)

* **No bot can guarantee profit.** This one is built to *protect capital first* (strict risk rules, kill-switches, news
  avoidance, "no trade" is a valid decision) and to take only high-scoring setups. Expect quiet periods and losing trades.
  **Always start on a DEMO account** for at least 2–4 weeks and read the trade log/“why” before risking real money.
* **A $12 account is extremely tight.** The smallest lot is 0.01. On a standard account:
  * **Gold (XAUUSD)**: a 0.01 lot with a normal stop risks roughly **$1.5–$3 → 12–25 % of $12**. The bot will therefore
    *skip gold* (it shows “Unaffordable: min lot would risk …” on the dashboard) and trade EURUSD/GBPUSD (~3–7 % risk per trade).
  * Margin also limits you to 1–3 positions. **Strong recommendation:** open a **cent/micro account** (Exness Cent,
    XM Micro, FBS Cent, …) where 0.01 lot is 100× smaller, so the 2 % risk rule works as designed. The bot supports it —
    just link that account.
  * Risk caps are adjustable in **Settings → Risk management**.
* **What was tested:** the Python engine (indicators, scanner, scoring, sizing, entries, trailing/BE/time stops, closing,
  halts, event delivery, chart payloads) was run end-to-end against the built-in simulator. The Java API and Flutter app were
  written carefully but **could not be compiled in the build environment** (no Maven/Flutter access there). Expect to fix at most a few
  small compile warnings/typos on first build; they are straightforward. The MT5 connector follows the official `MetaTrader5`
  Python API but needs a live terminal, so **test it on a demo account first**.
* The DB and SMTP credentials you pasted in chat are in `.env.example` as defaults. **Rotate them** (new DB password,
  new Resend API key) before real use, and change `JWT_SECRET`, `APP_ENCRYPTION_KEY`, `ENGINE_API_KEY`, `INTERNAL_API_KEY`.

---

## 1. Folder layout

```
forex-bot/
├─ README.md                  ← this file
├─ backend/                   ← deploy this (Java + Python together)
│  ├─ docker-compose.yml      ← api + engine (+ optional mt5-in-Wine)
│  ├─ .env.example            ← copy to .env
│  ├─ api/                    ← Spring Boot (Maven)
│  ├─ engine/                 ← Python engine (FastAPI) + tests/smoke_test.py
│  └─ scripts/                ← run-engine-windows.bat, run-api-windows.bat, run-engine-linux.sh
└─ frontend/                  ← Flutter app (run setup.bat once)
```

---

## 2. Quick test in 5 minutes (PAPER mode – no MT5 needed)

The engine has a built-in market simulator (`BROKER_MODE=paper`, starting balance `PAPER_BALANCE=12`). Use it to see the
whole system work before touching a broker.

**With Docker (any OS):**
```bash
cd backend
cp .env.example .env            # edit secrets; BROKER_MODE=paper is the default
docker compose up -d --build
# API:    http://localhost:8080/actuator/health   → {"status":"UP"}
```
Then run the Flutter app (section 5), sign in with `joel@wayaspot.com` / `Kalimbwejoel@01`, press **Trade Now**.
In paper mode set `PAPER_SPEED=60` in `.env` to make the simulated market run 60× faster so you see trades quickly.

**Engine only (no Java/DB needed) – proves the Python side:**
```bash
cd backend/engine
pip install -r requirements.txt
PYTHONPATH=. PAPER_SPEED=300 python -m tests.smoke_test
```
It scans the 3 pairs, prints the ranking, builds chart overlays, runs the bot, opens/manages/closes simulated trades, and
checks events are delivered.

---

## 3. Connect your real MT5 account (Windows PC) — step by step

MT5 and the Python `MetaTrader5` package only work on **Windows**, so the simplest first setup is: *everything on your Windows PC*.

### 3.1 Install the pieces
1. **MetaTrader 5 terminal** – download from your broker's website (recommended; it comes pre-configured with their
   servers) or from metatrader5.com. Install it.
2. Open MT5 → **File → Open an Account / Login to Trade Account** → log in to a **DEMO** account first
   (login number, password, broker server name, e.g. `Exness-MT5Trial`). Confirm you see live quotes.
3. **Allow algo trading:** MT5 → **Tools → Options → Expert Advisors** → tick **Allow algorithmic trading**. Click the
   **Algo Trading** button in the toolbar until it is **green**.
4. **Market Watch:** right-click → *Symbols* → make sure `XAUUSD` (some brokers call it `GOLD`), `EURUSD`, `GBPUSD` exist.
   If your broker uses suffixes (`EURUSDm`, `XAUUSD.a`…) set `SYMBOL_SUFFIX` in `.env` (e.g. `m`). The engine also
   auto-detects names starting with the base symbol.
5. Install **Python 3.12 (64-bit)** from python.org (tick *Add to PATH*), **JDK 17+** (Temurin) and **Maven**
   (or use Docker Desktop for the API), and a **PostgreSQL** you can reach (your server's DB from `.env`).
6. Install **Flutter** (flutter.dev → Windows install). Run `flutter doctor` until Windows desktop is ticked
   (needs *Visual Studio 2022 with “Desktop development with C++”*).

### 3.2 Configure
```bat
cd forex-bot\backend
copy .env.example .env
notepad .env
```
Set at least:
```
BROKER_MODE=mt5
PAPER_BALANCE=12          (ignored in mt5 mode)
SYMBOL_SUFFIX=            (only if your broker needs it)
```
Optional: put `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` here, **or** (nicer) leave them empty and link the account
later from the app's **Settings** page.

### 3.3 Run (two terminals)
```bat
:: Terminal 1 – Python engine (talks to the open MT5 terminal)
scripts\run-engine-windows.bat

:: Terminal 2 – Spring Boot API
scripts\run-api-windows.bat
```
Check: http://localhost:8000/health (engine) and http://localhost:8080/actuator/health (API).
*(Alternative for the API: `docker compose up -d --build api` — then set `ENGINE_URL_OVERRIDE=http://host.docker.internal:8000`
and `JAVA_EVENTS_URL` stays `http://localhost:8080/internal/events` because the engine runs on the host.)*

### 3.4 Use the app
1. Run the Flutter app (section 5) → sign in.
2. **Settings → Broker account**: enter MT5 *login*, *server* and *trading password* → **Save & connect**. You should see
   **CONNECTED**, your account number, DEMO/LIVE tag.
3. **Dashboard → Trade Now.** The status goes `SCANNING` → `IN_TRADE`. Watch **Opportunity ranking** (why a pair was
   chosen or why none is), **Charts & Analysis**, **Trades**, **Transactions**.
4. **Stop trade** when you want to finish. You'll get the summary e-mail.

> MT5 must stay open and logged in on that PC (it is the bridge to your broker). A cheap Windows VPS is the usual way to
> run it 24/7 — see 4B.

---

## 4. Deploy with Docker on Dokploy (your server)

Push this repo to GitHub. In Dokploy create a **Compose** project (Compose Type = Docker Compose) with
**Compose Path** `./docker-compose.yml` at the repo root. Add the variables from `.env.example` in the
**Environment** tab. Do not set `container_name` in compose (Dokploy cannot list those containers). Deploy /
Rebuild until you see services `api`, `engine`, and `web`. Add a **domain** if you want
(e.g. `api.yourdomain.com` → service `api`, port `8080`, HTTPS on).

Postgres: the compose file uses your external DB (`DB_URL`…). To use a Dokploy-managed Postgres instead, create it in
Dokploy and point `DB_URL` at its internal host.

**Where does MT5 run? (MT5 is a Windows program — pick one)**

**4A. Same Linux server (MT5 under Wine in Docker)**
```
BROKER_MODE=mt5
COMPOSE_PROFILES=mt5
MT5_VNC_USER=admin
MT5_VNC_PASSWORD=<strong password>
```
This starts the extra `mt5` container (image `gmag11/metatrader5_vnc`). Open `http://SERVER_IP:3000` (web VNC), log in to your
broker inside MT5 once (and enable algo trading), then **close port 3000 in your firewall**. The engine reaches MT5 through
`mt5linux` (rpyc, port 8001, internal). *This image is community-maintained; if it misbehaves use 4B.*

**4B. Windows VPS for MT5 + engine, Dokploy for the API (most reliable for 24/7)**
1. On the Windows VPS: install MT5 + Python, copy `backend`, set `.env` (`BROKER_MODE=mt5`,
   `JAVA_EVENTS_URL=https://api.yourdomain.com/internal/events`, same `ENGINE_API_KEY`/`INTERNAL_API_KEY`), run
   `scripts\run-engine-windows.bat` (set it to auto-start with Task Scheduler). Allow inbound TCP 8000 **only from your Dokploy server IP**.
2. In Dokploy set `ENGINE_URL_OVERRIDE=http://WINDOWS_VPS_IP:8000`. (You can ignore/remove the `engine` service.)

**Security checklist:** HTTPS only · change all secrets · DB reachable only from the server · never expose port 8000/8001/3000 publicly.

---

## 5. The Flutter app

```bat
cd forex-bot\frontend
setup.bat            :: one time: creates windows/web/android folders around lib/ and runs pub get
flutter run -d windows
```
* **Logo:** replace `frontend/assets/images/logo.png` with your logo (square PNG ~512 px). It is used on the login page and
  the drawer. For **e-mails**, upload the logo to any public HTTPS URL and set `LOGO_URL` in `.env`.
* **Server URL:** on the login screen tap *Server settings* (default `http://localhost:8080`). For production use
  `https://api.yourdomain.com`. You can bake it in: `flutter run --dart-define=API_URL=https://api.yourdomain.com`.
* **Stays signed in:** the token (valid 365 days) is stored on the device; you only sign out by pressing *Log out* (or if the super admin deletes/disables you).
* **Build the Windows .exe:** `flutter build windows --release --dart-define=API_URL=https://api.yourdomain.com`
  → `build\windows\x64\runner\Release\` (zip/ship that whole folder; run `waya_fx_bot.exe`).
* **Web:** `flutter build web --release --dart-define=API_URL=https://api.yourdomain.com` → host `build/web` anywhere
  (must be HTTPS if the API is HTTPS).  **Android:** `flutter build apk --release`.

**Pages (drawer):** Dashboard (Trade Now / Stop, KPIs, opportunity ranking with “why”, equity curve, live quotes, activity,
news, recent trades) · Charts & Analysis (candlesticks with EMAs, Bollinger, VWAP, S/R zones, bold trendlines, order blocks,
fair-value gaps, swings, breakout markers, entry/SL/TP — toggleable, any pair/timeframe) · Trades (open with live P/L and
manual close; closed with WIN/LOSS, closing remark, net P/L, balance before→after) · Transactions (full ledger) · Reports
(sessions + e-mail resend) · Market News (calendar + headlines + per-pair “blocked by news” status) · Admins ·
Settings (theme, MT5 link, risk, server, test e-mail, logout).

---

## 6. How the bot thinks

**Scan loop (every ~5 s while running):** for each of XAUUSD, EURUSD, GBPUSD it builds a top-down picture
**D1 → H4 → H1 → M30 → M15 → M5 → M1** and scores BUY and SELL (0–100):

| Component | Max | What it measures |
|---|---|---|
| Higher-TF alignment | 30 | EMA stack, MACD, ADX-weighted trend and HH/HL structure on D1/H4/H1/M30/M15 |
| Setup momentum | 20 | M5 trend, RSI room-to-run (penalises exhaustion), MACD acceleration, M15 ADX/DI |
| Location | 20 | pullback to EMA20/50 value, support/resistance zones, order blocks, breakout-retest, Bollinger extreme, VWAP side |
| M1 trigger | 15 | engulfing / pin bar / morning-evening star / inside-bar break, M1 micro BOS, **false-breakout (liquidity sweep) reversal** |
| Regime | 10 | ADX range, ATR vs average (rejects dead markets and volatility spikes) |
| Volume | 5 | tick-volume expansion |

Penalties: counter-trend vs higher TFs, chasing extended price, opposing S/R zone too close, poor recent performance of that
setup (self-adjusting from the last 20 trades). **Hard filters:** high-impact news (30 min before / 15 after), spread
> 25 % of the stop, no M1 trigger yet, score < 62, R:R < 1.5, momentum-only setups need a higher score, trading outside
06:00–20:00 UTC, correlation guard (max 2 positions on the same USD direction), one position per pair.
The best-ranked tradable pair wins; if none qualifies the bot **waits** and tells you why.

**Entry & exits:** market order with SL beyond the nearest protective swing (bounded by ATR) and TP before the next
meaningful S/R zone (2–3 R). Then: **break-even at +0.8 R**, **trailing stop from +1.2 R**, **momentum-reversal exit**
when a strong opposite candle + MACD flip appears in profit, **time stop** (45 min without follow-through), **close
before high-impact news**, **weekend close**.

**Risk management:** lot size = (equity × risk %) / loss-at-stop, rounded **down** to the broker lot step; if the minimum lot
overshoots, it's accepted only below the micro-account cap (default 7 %), else skipped. Total open risk ≤ 8 %,
max 3 positions, margin check (≤ 60 % of free margin per order), **daily loss limit 8 %** (halts until next UTC day),
**max drawdown 25 %** (kill-switch: closes all, halts, e-mails you), **cool-down after 3 straight losses**, per-pair cooldown after a loss.

**Charts:** the engine draws trendlines (best-fit through swing points, must never be closed through), S/R zones
clustered from D1/H4/H1/M30/M15 swings, unmitigated order blocks, fair-value gaps, swings, BOS/CHoCH, false-breakout and
retest markers, and the planned entry/SL/TP; the app renders them on candlesticks.

---

## 7. E-mails (Resend SMTP)

* **When you press Stop trade** – session summary: opening/closing balance, net P/L, win rate, profit factor, per-pair table, every trade with remark.
* **Daily digest** at 23:55 UTC (`DAILY_REPORT_CRON`) – only if trades closed that day.
* **Important alerts immediately** – risk halt/kill-switch, MT5 disconnected, engine unreachable >5 min.
* Not sent after every single trade. HTML design uses your logo (`LOGO_URL`) and brand name.

---

## 8. Configuration reference (`backend/.env`)

| Variable | Meaning |
|---|---|
| `DB_URL / DB_USERNAME / DB_PASSWORD` | PostgreSQL (tables auto-created) |
| `MAIL_*`, `MAIL_FROM`, `REPORT_TO`, `LOGO_URL`, `BRAND_NAME` | SMTP & e-mail branding |
| `ADMIN_USERNAME / ADMIN_PASSWORD` | Super admin created on first start (only if none exists) |
| `JWT_SECRET`, `JWT_EXPIRY_DAYS` | Login tokens (365 days default → stays logged in) |
| `APP_ENCRYPTION_KEY` | Encrypts the stored MT5 password |
| `ENGINE_API_KEY`, `INTERNAL_API_KEY` | Shared secrets API↔engine |
| `BROKER_MODE` | `paper` (simulator) or `mt5` |
| `SYMBOL_SUFFIX`, `MAGIC_NUMBER` | Broker symbol suffix; id used to tag the bot's orders |
| `MT5_LOGIN/PASSWORD/SERVER/PATH` | Optional auto-login (Windows `PATH` = terminal64.exe) |
| `MT5_RPYC_HOST/PORT`, `COMPOSE_PROFILES=mt5` | MT5-under-Wine on Linux |
| `ENGINE_URL_OVERRIDE` | Engine running elsewhere (Windows VPS) |

Risk numbers live in the app (**Settings → Risk management**) and are stored by the engine (`/data/risk_config.json`).

**REST API (all `/api/**` need `Authorization: Bearer <token>`):**
`POST /api/auth/login` · `GET /api/auth/me` · `GET|POST|PUT|DELETE /api/admins` (super admin) · `GET /api/bot/status` ·
`POST /api/bot/start` · `POST /api/bot/stop {closePositions}` · `GET /api/trades/open|closed|stats` · `GET /api/transactions` ·
`GET /api/dashboard` · `GET /api/market/quotes|scan|news|analysis/{symbol}?tf=M5` · `GET|PUT /api/settings/mt5|risk` ·
`GET /api/reports/sessions`.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| App: “Cannot reach the server” | Wrong URL; API not running; https page calling http API (web) |
| Settings shows NOT CONNECTED | MT5 terminal closed / not logged in / wrong server name / password is *investor* password / Python is 32-bit |
| `initialize() failed` | Start MT5 manually once, enable algo trading, set `MT5_PATH` to terminal64.exe |
| Order rejected “Trade disabled / Invalid stops” | Algo trading off in terminal or on the account; broker min stop distance (engine respects `stops_level`) |
| Pair never trades | Open Dashboard → ranking → expand the pair: it lists exact blockers (spread, score, unaffordable, news…) |
| `Unaffordable: min lot would risk…` | Balance too small for that pair → use a cent/micro account or raise the micro cap (carefully) |
| No e-mails | Check Resend key, `MAIL_FROM` domain verified in Resend, use **Settings → Send test e-mail** |
| API fails to start | DB unreachable / wrong `DB_URL`; check `docker logs forexbot-api` |

---

## 10. Ideas for next steps
* Run 2–4 weeks on demo; review **Reports** and the per-setup performance the bot keeps; tighten `min_score` if too many marginal trades.
* Add a backtest runner on exported MT5 history (the analyzer is a pure function of candles).
* Telegram push notifications; a position-size “cent account” preset; multi-account support.
