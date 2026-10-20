# Run the bot

The app already runs on the server `145.241.187.174`. This Windows PC only runs MetaTrader 5 and a small bridge. The bridge calls the server. The server sends prices and orders back down that call.

## Addresses

| Name | Value | What you do with it |
|---|---|---|
| Server | `145.241.187.174` | Already written in the project. The browser and the bridge use it. |
| Website and bridge port | `8088` | Already open on the server. |
| This PC's public IP | The number a "what is my IP" site shows | Nothing. Leave it off Dokploy, off `.env`, and off the bridge. |
| `MT5_RPYC_HOST` | Empty | Leave it empty. There is no place to look it up. |
| `MT5_RPYC_PORT` | `18812` | Leave it, or delete the variable. Nothing listens on it. |

`MT5_RPYC_HOST` is an old name still listed in Dokploy. The engine reads it and then ignores it. The live link is already inside `scripts\mt5_bridge.py`:

`ws://145.241.187.174:8088/mt5-bridge`

## 1. Before you deploy

In Dokploy, set only the rows that differ from the defaults. The compose file already fills the rest.

| Variable | Set it to |
|---|---|
| `MT5_RPYC_HOST` | Empty |
| `MT5_RPYC_PORT` | `18812`, or delete it |
| `BROKER_MODE` | `mt5` |
| `SYMBOL_SUFFIX` | Empty, unless Market Watch shows names like `EURUSDm` (then `m`) or `EURUSD.a` (then `.a`) |
| `ENGINE_API_KEY` | Leave the default, unless you already changed it on the server |

Leave `MT5_LOGIN`, `MT5_PASSWORD`, and `MT5_SERVER` empty. You type those in the app after deploy.

Deploy these three containers: `forexbot-api`, `forexbot-engine`, `forexbot-web`. There is no MT5 container.

If Connect MT5 later mentions a host named `mt5`, port `8001`, or port `18812`, the server is on an old build. Redeploy the engine and the web container, then continue.

## 2. Log in to MetaTrader 5

1. Open MetaTrader 5 on this PC.
2. **File → Login to Trade Account**. Use a demo account the first time.
3. Write down the account number and the server name from the bottom of the window. Example server: `Exness-MT5Trial`.
4. **Tools → Options → Expert Advisors**. Tick **Allow algorithmic trading**.
5. Click **Algo Trading** on the toolbar until it is green.
6. Press Ctrl+M. Confirm `XAUUSD`, `EURUSD`, and `GBPUSD` are in Market Watch. Right-click the list and choose **Show All** if one is missing.
7. Leave the MT5 window open.

The password you need later is the trading password from the broker, the one that can place trades. The investor password is read-only.

## 3. Start the bridge

Do this after MT5 is logged in.

1. Install Python 3 from https://www.python.org/downloads/windows/ if `python` is not on PATH. Tick **Add python.exe to PATH**.
2. Double-click `scripts\mt5-bridge-windows.bat`.
3. The first run installs packages. Wait until it finishes.
4. The window should print `Connecting to ws://145.241.187.174:8088/mt5-bridge ...` and then `Connected to the server. Leave this window open.`
5. Leave that window open.

You do not type an IP before this step. If you changed `ENGINE_API_KEY` on the server, put the same value in a `.env` file in the project folder (`ENGINE_API_KEY=...`) before you start the `.bat` file. Otherwise skip that file.

## 4. Log in to the Flutter app

1. Open http://145.241.187.174:8088
2. If **Server settings** is visible, set the server to `http://145.241.187.174:8088`
3. Sign in:
   - Username: `joel@wayaspot.com`
   - Password: `Kalimbwejoel@01`

## 5. Connect the MT5 account in the app

On the dashboard card **Log in to your MT5 account** (the same form is under **Settings → Broker account**):

| Field | Value |
|---|---|
| MT5 login | Account number from the bottom of the MT5 window |
| Broker server | Server name from the bottom of the MT5 window, copied exactly |
| Trading password | The broker trading password |

Press **Connect MT5**. You should see **Connected to MT5**, then a green **CONNECTED** pill and a **DEMO** tag.

After a restart of MT5 or the bridge, press **Reconnect** on the Settings page.

## 6. Trade

Press **Trade Now** on the dashboard. New trades show on the dashboard and in the MT5 **Trade** tab. **Stop trade** stops the loop.

## What has to stay open

| Leave this open | If you close it |
|---|---|
| This PC | The server cannot reach MT5 |
| The MetaTrader 5 window | Prices and orders stop |
| The bridge window | The app says the bridge is not connected |
| Algo Trading, green | Orders are rejected |
| The three server containers | The app or the bot stops |

You can close the browser. The bot keeps running. If the bridge window closes, start `scripts\mt5-bridge-windows.bat` again and wait for `Connected to the server`, then press **Reconnect**.

## If it does not connect

| What you see | What to do |
|---|---|
| Timeout mentioning port `18812` | Redeploy the engine and the web container. Keep `MT5_RPYC_HOST` empty. Start the `.bat` file again. |
| Bridge window keeps saying `Not connected` on `8088/mt5-bridge` | The web container is missing `/mt5-bridge`. Redeploy, then start the bridge again. |
| `initialize() failed` | The server name does not match the MT5 window, or you used the investor password. |
| `Terminal started but no account is logged in` | Log in inside MT5, then press **Reconnect**. |
| `TRADING DISABLED IN TERMINAL` | Turn **Algo Trading** green and tick **Allow algorithmic trading**. |
| Connected, but no prices | Market Watch names have a suffix. Set `SYMBOL_SUFFIX`, restart the engine, press **Reconnect**. |
