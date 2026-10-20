# Set up the MT5 desktop on this PC

Java, Python, and the Flutter app are already running on the server. This guide is the remaining piece: the MetaTrader 5 program on this Windows PC, and the small bridge program that links that window to the server.

You do not install MT5 on the server. You do not open port 3009. You do not open port 18812. You do not type this PC's public IP address into Dokploy, into `.env`, or into the `.bat` file. The MT5 window on this PC is the terminal the bot trades through.

## How each address and port is used

Every number in the notes belongs to one of two paths. The path that runs today is the bridge on this PC calling the VPS. The other path is a leftover pair of environment variables. The home router only carries the first path, and it does that with no settings from you.

### Values the running system uses

| Value | Where it is written | Who uses it | What it does |
|---|---|---|---|
| `145.241.187.174` | `scripts\mt5_bridge.py`, the Flutter app, `docker-compose.yml` | The bridge, your browser | Public IP of the VPS. This is the machine you connect to |
| `8088` | `docker-compose.yml` (`"8088:80"`), `.env.example` `WEB_PORT` | The VPS firewall and the web container | Public port of the website. The bridge and the Flutter app both use it |
| `/mt5-bridge` | `frontend\nginx.conf`, then `engine\app\main.py` | Nginx, then the Python engine | The path the bridge opens. Nginx passes that socket through to the engine |
| `8000` | Engine process inside Docker. `docker-compose.yml` only `expose`s it | Nginx, on the private Docker network | The engine's own port. It is reachable as `engine:8000` from the web container. It is not published on the VPS public IP |
| `8080` | `docker-compose.yml` (`"8080:8080"`) | The Flutter app, through the browser | Java API. The website also proxies `/api/` to it, so normal use of the app goes through port `8088` |
| `ENGINE_API_KEY` | Server environment, and `.env` in this project folder when that file exists | The bridge sends it as the header `X-Api-Key`. The engine compares it | Proves the bridge is allowed to attach. The default in the script matches the default on the server |

The line the `.bat` file actually dials is in `scripts\mt5_bridge.py`:

```
SERVER = os.environ.get("MT5_BRIDGE_URL", "ws://145.241.187.174:8088/mt5-bridge")
```

`MT5_BRIDGE_URL` is optional. When it is unset, the script uses the address in quotes. Leave it unset while the VPS stays at `145.241.187.174`. If that VPS address changes, either edit the quoted address or set `MT5_BRIDGE_URL` to `ws://NEW_VPS_IP:8088/mt5-bridge` before starting the `.bat` file.

After the bridge connects, the pieces hand the socket along like this:

1. This PC opens a connection to `145.241.187.174` port `8088`.
2. The VPS accepts it because port `8088` is already published for the website.
3. Nginx, inside the web container, sees the path `/mt5-bridge` and forwards the same connection to `engine:8000`.
4. The Python engine keeps that socket open. When it wants a price or an order, it sends the request back down the socket. The bridge runs it in the local MetaTrader 5 window and sends the answer back.

### Values that are loaded and then ignored

These two names still exist. They do not choose where the bridge connects.

| Name | Where it is written | Value in this project | What the code does with it |
|---|---|---|---|
| `MT5_RPYC_HOST` | `docker-compose.yml`, `.env.example`, `engine\app\config.py` | Empty. The comment in `docker-compose.yml` shows a sample, `203.0.113.10` | Copied into the engine setting `mt5_rpyc_host`, then passed into `RemoteMetaTrader5`. That object does not keep the host |
| `MT5_RPYC_PORT` | Same three files | `18812` when the variable is missing | Copied into `mt5_rpyc_port`, then passed in as the port. That object does not keep the port |

The hand-off in code is:

1. Dokploy, or the `.env` file on the server, supplies `MT5_RPYC_HOST` and `MT5_RPYC_PORT` to the `forexbot-engine` container.
2. `engine\app\config.py` reads them. An empty host stays empty. A missing port becomes `18812`.
3. On the VPS the engine is Linux, so `engine\app\broker\mt5_broker.py` builds `RemoteMetaTrader5(host=Settings.mt5_rpyc_host, port=Settings.mt5_rpyc_port)`.
4. `RemoteMetaTrader5` accepts those two arguments and does not store them. Every MetaTrader call goes through the websocket that the bridge already opened.

So `18812` is only the fallback number in `int(env("MT5_RPYC_PORT", "18812"))`. Nothing on this PC listens on `18812`. The `.bat` file never prints it. Filling `MT5_RPYC_HOST` does not point the engine at this PC.

`105.232.129.56` is not stored anywhere as `MT5_RPYC_HOST`. No `.env` line sets `MT5_RPYC_HOST=105.232.129.56`. That IP appeared only as an example in an older troubleshooting sentence in this file, written next to port `18812` (`105.232.129.56:18812`). It is an illustration of the old "call inward" address. It is not a value to copy into Dokploy.

Leave `MT5_RPYC_HOST` empty. Leave `MT5_RPYC_PORT` at `18812` or delete it. The live link stays `ws://145.241.187.174:8088/mt5-bridge`.

### How the home router is involved

This PC has two addresses at once:

| Address | Example shape | Who assigned it | Who on the internet can use it |
|---|---|---|---|
| Private address of this PC | `192.168.0.25` or `192.168.1.50` | Your home or office router | Only devices on the same Wi-Fi or LAN |
| Public address of the router | Whatever a "what is my IP" site shows | Your internet provider, on the router's WAN port | The outside world sees this one address for every device in the house |

The router sits between them. It has two different jobs. Only one of them happens for this project.

**Job the router does by itself: outbound NAT.** When the bridge (or a browser) connects to `145.241.187.174:8088`, the router lets that outgoing call through. It remembers the conversation, and it sends the VPS replies back to this PC. You do not create a rule for that. The same thing happens when you open the Flutter app in a browser. If the website loads, the path the bridge needs is already allowed out.

```
This PC                         Home router                      VPS
private 192.168.x.x             public address on the WAN        145.241.187.174
     │                                │                                │
     │  bridge connects to :8088      │                                │
     └──────────────► NAT remembers this conversation ───────────────►│ :8088
                      replies travel back on the same conversation
```

There is no screen in the router where you type `145.241.187.174`, `8088`, `18812`, or this PC's public IP. Closing the bridge window ends the conversation. Starting the `.bat` file opens a new one.

**Job you leave unused: a port forward.** A port forward is an inbound rule. It says "when a stranger on the internet connects to my public IP on this port, hand that connection to one private address inside the house." The old design needed that, because the VPS tried to open the connection itself, toward this house, on port `18812`. A forward for that would have looked like:

| Router field | What the old design would have required |
|---|---|
| External port | `18812` |
| Internal IP | This PC's private address, such as `192.168.0.25`, read from the router client list or from `ipconfig` |
| Internal port | `18812` |
| Protocol | TCP |
| Plus, on the PC | A Windows Firewall inbound allow for `18812` |
| Plus, in Dokploy | `MT5_RPYC_HOST` set to the router's public IP, and `MT5_RPYC_PORT=18812` |

That forward is not part of the setup. The current engine never dials the router's public IP, so a rule for `18812` would sit unused. The public IP from the provider also changes when the router restarts, which is why an inbound address goes stale. The outbound bridge avoids both problems: this PC places the call, and the VPS answers on the website port it already has open.

On the VPS, the only inbound ports this setup publishes are `8088` (website and bridge) and `8080` (Java, also reachable through the website proxy). Port `8000` stays on the Docker network. Port `18812` is not opened on the VPS and not opened on the home router.

### Order of work before the .bat file

Do these in this order. Nothing in the list asks for your public IP or for port `18812`.

1. On the VPS, in Dokploy, confirm the deployed build is this project. The running containers are `forexbot-api`, `forexbot-engine`, and `forexbot-web`. There is no MT5 container. If Connect MT5 in the app mentions a host named `mt5`, port `8001`, or a timeout to some address on port `18812`, the VPS is still on the old build. Push this project, redeploy the engine and the web container, and only then continue.
2. In Dokploy environment variables, leave `MT5_RPYC_HOST` empty. Leave `MT5_RPYC_PORT` at `18812` or delete the variable. Do not type this PC's public IP there.
3. On this PC, install MetaTrader 5 from your broker if it is not installed yet. Log in to a demo account. The steps are in section 1 below. Leave that window open.
4. Install Python 3 if `python` is not already on PATH. The steps are in section 2 below.
5. Do not create a `.env` on this PC for the bridge. The bridge reads `ENGINE_API_KEY` from the project `.env` when that file exists, and otherwise uses the same default key the server already uses (`a293bc338ba95dbd8bcfb55aa4ab99a13f51351f712d034c`). You only need a matching `.env` on this PC if you changed `ENGINE_API_KEY` on the server to a different value. In that case copy that one line into a file named `.env` in the project root (the folder that contains `scripts`), as `ENGINE_API_KEY=the-same-value-as-the-server`.
6. Double-click `scripts\mt5-bridge-windows.bat`, as in section 2. The window should print `Connecting to ws://145.241.187.174:8088/mt5-bridge ...` and then `Connected to the server. Leave this window open.`

There is no IP field to fill in between step 5 and step 6.

## What is already running

| Piece | Address | You do this |
|---|---|---|
| Flutter app | http://145.241.187.174:8088 | Open it in a browser and sign in |
| Java API | http://145.241.187.174:8080 | Nothing. The app talks to it for you |
| Python engine | inside Docker on port 8000, not open on the internet. The bridge reaches it through port 8088 | Nothing. Start the bridge on this PC and it dials `8088` |
| Database | `84.8.131.140`, database `forex2` | Nothing |

Sign in to the app with the same admin account you already use (`joel@wayaspot.com`).

## How a trade reaches the broker

```
This Windows PC                         Server 145.241.187.174
────────────────────────                ─────────────────────────────────
MetaTrader 5 (the EXE)                  Flutter app  :8088
        ▲                                    │
        │ official MT5 library               │  you press Connect MT5
Bridge window                                ▼
        │                               Java API     :8080
        │  dials out to :8088/mt5-bridge     │  stores the password encrypted
        └──────────────────────────────► Python engine
             this PC calls the server        scans XAUUSD, EURUSD, GBPUSD
                                             and sends orders back down that link
```

The Flutter app never talks to MetaTrader. It sends the account number, server name, and trading password to Java. Java sends them to Python. The bridge on this PC keeps a connection open to the server, and Python sends the MT5 calls back down that connection.

That open connection is the outbound call described above. It leaves this PC, crosses the home router by NAT, and lands on the VPS at port `8088`. The router remembers the conversation and returns the engine's replies to the bridge. No port-forward screen is filled in. `MT5_RPYC_HOST` and port `18812` are not part of this path.

## Information you will need

Collect these before you start. Each one comes from a specific place.

| What | Where you get it | Where you type it |
|---|---|---|
| MT5 account number | Bottom of the MT5 window, left side. It is a number such as `12345678`. The same number is in the broker email that opened the account, and under **Navigator → Accounts**. | Flutter dashboard, field **MT5 login** |
| Broker server name | Bottom of the MT5 window, next to the account number. Also under **File → Login to Trade Account**. Copy it exactly, including capital letters and hyphens. Example: `Exness-MT5Trial`. | Flutter dashboard, field **Broker server** |
| Trading password | The password you chose when the broker created the account. It is the password that can place trades. The **investor** password is read-only and will not work. If you forgot it, reset it in the broker's website, not inside this project. | Flutter dashboard, field **Trading password** |
| Symbol names | MT5 **Market Watch** (Ctrl+M). Look for `XAUUSD`, `EURUSD`, `GBPUSD`. | Only if the names have an extra ending. See the symbol section below. |

## Before the first Connect MT5

The server must already be on the build described above. If Connect MT5 reports a host named `mt5`, port `8001`, or a timeout that ends in `:18812`, stop and redeploy. Do not answer that error by typing a public IP into `MT5_RPYC_HOST`.

After the redeploy, the running services are only `forexbot-api`, `forexbot-engine`, and `forexbot-web`. There is no MT5 container.

## 1. Prepare the MT5 window

1. Open the MetaTrader 5 you already installed.
2. **File → Login to Trade Account**. Use a **demo** account the first time.
3. After it connects, read the account number and server name from the bottom of the window. Write them down. Those are the two values the Flutter form needs.
4. **Tools → Options → Expert Advisors**. Tick **Allow algorithmic trading**. Press OK.
5. On the toolbar, click **Algo Trading** until the button is green. If this stays red, the bot can see prices but the broker will reject every order. The app then shows `TRADING DISABLED IN TERMINAL`.
6. Press Ctrl+M to open **Market Watch**. Confirm `XAUUSD`, `EURUSD`, and `GBPUSD` are listed. Right-click the list and choose **Show All** if one is missing. Some brokers name gold `GOLD` and add a suffix such as `m` or `.a` (`EURUSDm`). See the symbol section if that is the case.
7. Leave this window open. Minimizing it is fine. Closing it stops the bot.

## 2. Install Python, then start the bridge

The bridge is a small program on this PC. The cloud engine uses it to reach the MT5 window.

1. If `python` is not installed, download Python 3 from https://www.python.org/downloads/windows/ and run the installer. On the first screen, tick **Add python.exe to PATH**.
2. Close any old Command Prompt windows so they see the new Python.
3. You do not edit an IP address or a port before this step. `MT5_RPYC_HOST` stays empty. Port `18812` stays unused. The server address is already inside `scripts\mt5_bridge.py`.
4. In File Explorer, open the project folder and double-click:

   `scripts\mt5-bridge-windows.bat`

5. The first run creates a folder named `.venv-bridge` next to the script and installs `MetaTrader5`, `websockets`, and `numpy`. Wait until that finishes. This can take a few minutes. Do not close the window while packages are installing.
6. The window prints `Connecting to ws://145.241.187.174:8088/mt5-bridge ...`
7. It then prints `Connected to the server. Leave this window open.`
8. Leave the black window open. Closing it disconnects the server from MT5.

If the window repeats `Not connected` and the message mentions port `18812`, you started an old script, or the VPS is still on the old build. The current script never prints `18812`. It only prints the `8088/mt5-bridge` address.

The VPS must already be running the build that accepts `/mt5-bridge` before this window can stay connected. Redeploy the engine and the web container first if you have not done that yet.

## 3. Connect the account from the app

1. Open http://145.241.187.174:8088 and sign in.
2. On the dashboard, the card **Log in to your MT5 account** is shown until the terminal is connected.
3. Fill the three fields with the values from the table at the top of this guide.
4. Press **Connect MT5**. Only the super admin can press it.

What you should see:

- A toast **Connected to MT5**.
- The card goes away.
- **Settings → Broker account (MetaTrader 5)** shows a green **CONNECTED** pill, the login, the server name, and a **DEMO** tag.

The same form is on that Settings page, with **Save & connect** and **Reconnect**. Use **Reconnect** after you restart the bridge or the MT5 window. Java also retries the saved login about once a minute.

The trading password is encrypted on the server. It is not shown again. To change it, type a new one and press **Save & connect**. Leaving the password box empty keeps the saved one.

## 4. Start trading

On the dashboard, press **Trade Now**.

The engine reads candles from the MT5 window for `XAUUSD`, `EURUSD`, and `GBPUSD`, and sends an order only when its score and risk rules pass. A new trade shows on the dashboard within a few seconds, and it also appears in the MT5 **Trade** tab on this PC.

**Stop trade** stops the loop. If you leave “close open positions” ticked, the engine closes them through the same MT5 window.

## Symbol names

The engine looks for `XAUUSD`, `EURUSD`, and `GBPUSD`.

| What Market Watch shows | What to set in Dokploy |
|---|---|
| `EURUSD`, `GBPUSD`, `XAUUSD` | Leave `SYMBOL_SUFFIX` empty |
| `EURUSDm`, `GBPUSDm`, `XAUUSDm` | `SYMBOL_SUFFIX=m` |
| `EURUSD.a` | `SYMBOL_SUFFIX=.a` |
| Gold is only listed as `GOLD` | Add `XAUUSD` from the broker's symbol list, or the scan for gold will stay empty |

After changing `SYMBOL_SUFFIX`, restart the engine and press **Reconnect** in Settings.

## What has to stay on

| Thing | If you close it |
|---|---|
| This PC | The server cannot reach MT5 |
| The MetaTrader 5 window | Orders and prices stop |
| The black bridge window | The engine reports that it cannot connect |
| Algo Trading, green | Orders are rejected. Prices still work |
| `forexbot-api`, `forexbot-engine`, `forexbot-web` | The app or the bot stops |

You can close the browser. The bot keeps running on the server while this PC, the MetaTrader 5 window, and the bridge window stay open, and while the three server containers stay up. The home router keeps the bridge's outbound conversation alive for as long as that window stays connected. Restarting the router drops it. Start `scripts\mt5-bridge-windows.bat` again and wait for `Connected to the server`.

## Check that it worked

1. Bridge window shows `Connected to the server. Leave this window open.`
2. Settings in the app shows **CONNECTED**, the right login, and **DEMO**.
3. The tag `TRADING DISABLED IN TERMINAL` is absent.
4. Press **Trade Now**. The dashboard status becomes running.
5. In MT5, **Toolbox → Trade** shows the same positions the dashboard shows.

## If it does not connect

| Message or symptom | What to do |
|---|---|
| `laptop bridge is not connected` or a timeout to some address on port `18812` | The engine on the VPS is still using the old inward call. The address in that message is whatever was stored in `MT5_RPYC_HOST`, plus the default port `18812`. `105.232.129.56:18812` was only an example of that shape in an older note. It is not a setting in this project. Leave `MT5_RPYC_HOST` empty, do not add a router forward for `18812`, redeploy the engine and the web container, then start `scripts\mt5-bridge-windows.bat` until it says `Connected to the server` |
| `Not connected` repeating in the bridge window, and the line mentions `8088/mt5-bridge` | The web container is not deployed yet, so port `8088` has no `/mt5-bridge`. Redeploy, then start the bridge again. This is not fixed by typing a public IP anywhere |
| `initialize() failed` with an auth error | The server name does not match the bottom of the MT5 window, or the password is the investor password |
| `Terminal started but no account is logged in` | Open MT5 and log in, then press **Reconnect** |
| `TRADING DISABLED IN TERMINAL` | Turn **Algo Trading** green, and tick **Allow algorithmic trading** |
| Connected, but no gold or forex prices | The Market Watch names do not match. Set `SYMBOL_SUFFIX` |
| `Saved, but MT5 did not connect` | Read the rest of that toast. It is the engine's reason |

A working bridge window stays on the line `Connected to the server`. The real test is **Connect MT5** in the app.
