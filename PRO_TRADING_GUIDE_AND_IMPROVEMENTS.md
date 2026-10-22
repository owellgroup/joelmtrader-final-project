# Trading Like a Pro: How the Bot Analyses, Sizes Risk, and What To Improve

This guide goes with `HOW_THE_BOT_WORKS.md`. That file is the short overview. This one goes deeper into **how a buy or sell is decided**, **why a $100 account still opens 0.01 lots**, **what happens when you change the risk settings**, **how long trades last**, and **a prioritised list of improvements**.

It is based on reading the engine code (`engine/app/analyzer.py`, `structure.py`, `indicators.py`, `bot.py`, `risk.py`, `config.py`, `marketdata.py`, `charts.py`) and the Flutter chart page. **No code was changed.**

> Dollar examples assume EURUSD/GBPUSD (about $10 per pip per 1.00 lot, so **$0.10 per pip at 0.01 lot**) and gold (XAUUSD) at about **$1 per $1 move at 0.01 lot**. Your broker's specs can differ slightly. The app's scan screen shows the real `lots`, `riskAmount` and `riskPctAtMinLot` per symbol.

---

## Table of contents

1. [The analysis pipeline: from Daily to the 1-minute trigger](#1-the-analysis-pipeline)
2. [How BUY vs SELL is decided](#2-how-buy-vs-sell-is-decided)
3. [How the entry, stop loss and take profit are built](#3-entry-stop-loss-and-take-profit)
4. [Why the chart always shows 5 minutes](#4-why-the-chart-always-shows-5-minutes)
5. [How long a trade is held](#5-how-long-a-trade-is-held)
6. [Risk management: every setting and how they interact](#6-risk-management-explained)
7. [Why $100 still opens 0.01 lots](#7-why-100-still-opens-001-lots)
8. [What happens if you raise the risk (with $12 and $100 examples)](#8-what-happens-if-you-raise-the-risk-settings)
9. [What can be improved (prioritised)](#9-what-can-be-improved)
10. [Suggested roadmap](#10-suggested-roadmap)

---

## 1. The analysis pipeline

**Yes, it starts with the Daily chart and works down to the 1-minute chart.** All seven timeframes are loaded for each of the three symbols (XAUUSD, EURUSD, GBPUSD). Each one has a different job:

```
D1  ─┐
H4  ─┤  DIRECTION BIAS      "Which side is the market on?"       (weighted 15/25/25/15/20)
H1  ─┤  + support/resistance zones, order blocks (H1)
M30 ─┤
M15 ─┘  + ADX trend strength, zones, order blocks

M5      SETUP + LOCATION    "Is price at a good place right now?"
        stop loss, take profit, ATR, pullback, RSI, MACD, VWAP, Bollinger

M1      TRIGGER             "Has the market just confirmed it?"
        candlestick pattern, micro break of structure, volume spike
```

### What is calculated on each timeframe

For every timeframe the bot builds a table of closed candles (the forming candle is ignored) and adds these indicators (`indicators.py`):

- EMA 9 / 20 / 50 / 200
- RSI(14), MACD(12,26,9), ATR(14), ADX(14) with +DI / -DI
- Bollinger Bands(20, 2), Stochastic(14,3)
- Volume average (tick volume) and session VWAP (resets at 00:00 UTC, intraday timeframes only)

Then the price-action layer (`structure.py`) finds:

- **Swing highs and lows**, and from them the **market structure**: higher highs/higher lows = uptrend, lower highs/lower lows = downtrend, otherwise range. It also flags BOS (break of structure) and CHoCH (change of character).
- **Support and resistance zones**, built from the last 12 swing highs and lows on D1, H4, H1, M30 and M15, merged into zones. Higher timeframes carry more weight (D1 3.0, H4 2.5, H1 2.0, M30 1.5, M15 1.0).
- **Order blocks** (the last opposite candle before a strong displacement move) on M5, M15 and H1, only if still unmitigated.
- **Fair value gaps** and **trendlines** (shown on the chart).
- **Candlestick patterns**: engulfing, pin bar, morning/evening star, momentum candle, inside-bar breakout.
- **Breakouts**: genuine breakout plus retest, and false breakouts (liquidity sweeps).

### Trend value per timeframe (-1 to +1)

```
trend = 0.25 x sign(close - EMA20)
      + 0.20 x sign(EMA20 - EMA50)
      + 0.15 x sign(EMA50 - EMA200)
      + 0.15 x sign(MACD histogram)
      + 0.25 x market structure (+1 / 0 / -1)
then multiplied by an ADX factor (0.3 to 1.0), so weak trends count for less
```

### Combined higher-timeframe bias

```
bias = 0.15 x D1 + 0.25 x H4 + 0.25 x H1 + 0.15 x M30 + 0.20 x M15
```

Positive bias favours buying, negative favours selling. **H4 and H1 matter most.**

### Data freshness

Candles are cached so MetaTrader is not hammered: M1 3 s, M5 8 s, M15 20 s, M30 45 s, H1 2 min, H4 7 min, D1 30 min. The whole scan repeats about every **5 seconds** while the bot is running (20 seconds when idle).

---

## 2. How BUY vs SELL is decided

The bot does **not** guess a direction from one timeframe. For every symbol it **scores both a BUY and a SELL from 0 to 100** with the same rules, then keeps the higher one.

| Component | Points | Timeframes used | What it checks |
|---|---|---|---|
| **A. Higher-timeframe alignment** | 30 | D1, H4, H1, M30, M15 | Does the trade side agree with `bias`? Against the bias: -12 penalty. |
| **B. Setup momentum** | 20 | M5, M15 | M5 trend, M5 RSI has room (BUY 45-68, SELL 32-55), M5 MACD accelerating, M15 ADX > 20 with +DI/-DI on our side. |
| **C. Location** | 20 | M5 + zones from D1-M15 | Pullback to M5 EMA20/50, sitting at a support (BUY) or resistance (SELL) zone, inside an order block, breakout retest, Bollinger band extreme, correct side of VWAP. Chasing a stretched price: -6. |
| **D. M1 trigger** | 15 | M1, M5 | Candle pattern, M1 EMA9/20 aligned, M1 micro break of structure, false-breakout reversal. |
| **E. Regime** | 10 | M15, M5 | ADX in a healthy range, volatility neither dead nor exploding. |
| **F. Volume** | 5 | M1, M5 | Tick volume above average. |

Then a small +3/-3/-8 adjustment from the last 20 results of that symbol and setup type.

### Which part is "big picture" and which is "small timeframe"?

Honest answer, from the point weights:

- **About 30 points (A)** come from the higher timeframes, plus some of the zone points in C.
- **About 65 points** (B, most of C, D, E, F) come from **M5, M1 and M15**.

So the **final score is weighted towards the short timeframes**. The big picture nudges the score, but it does **not** act as a veto. Example: a SELL against a bullish H4/H1 gets -12 and loses its alignment points, but if M5 and M1 are very strong it can still reach 62.

That is the most important design point to understand, and the first suggested improvement in section 9.

### Gates before a trade is allowed (all must pass)

- score >= 62 (a "momentum only" setup without pullback/zone needs 70)
- M1 trigger component >= 4 ("Waiting for M1 trigger")
- net reward:risk >= 1.5
- spread <= 25% of the stop distance
- no high-impact news for the relevant currencies (30 min before to 15 min after)
- affordable under the risk rules (section 6)
- symbol enabled, inside trading hours (06:00-20:00 UTC, weekdays)
- portfolio guards: max positions, one trade per symbol, USD-direction limit, total open risk

If several symbols pass, the best `rankScore` (score minus a spread penalty) is opened first.

---

## 3. Entry, stop loss and take profit

All built on **M5** in `build_plan`:

| Item | Rule |
|---|---|
| **Entry** | Market order at the current ask (buy) or bid (sell), only if price has not moved more than 0.3 x stop distance since the plan was made and the spread has not widened. |
| **Stop loss** | Behind the nearest M5 swing low (buy) / high (sell) of the last 40 bars, plus 0.3 x ATR. Clamped between 0.8 x ATR and 2 x ATR of M5 (never less than 4 x the spread). |
| **Take profit** | 2R by default. If a strong opposing zone lies ahead, the target is set before it (between 1.3R and 3R). If the zone is closer than 1.3R, the setup loses 8 points. |
| **Net R:R** | Includes half the spread on each side. Must be >= 1.5. |

Because the stop is only about 1 to 2 M5 ATRs, these are **short-term scalping/intraday trades**: typically **4 to 15 pips** on EURUSD/GBPUSD.

---

## 4. Why the chart always shows 5 minutes

This is only the app's default view. In `frontend/lib/pages/charts_page.dart` the chart starts with:

```dart
String _symbol = 'EURUSD', _tf = 'M5';
```

The page has buttons for `M1, M5, M15, M30, H1, H4, D1`, so you can switch. Every time the page is reloaded it goes back to M5, because it is hard-coded (the choice is not saved). M5 is also the timeframe the bot uses for stops and entries, so it is the most useful view. The bot itself reads all seven timeframes whatever the chart shows.

(A nice improvement: remember the last selected timeframe per user.)

---

## 5. How long a trade is held

There is **no fixed holding time**. A trade ends when one of these happens first:

| Exit | When |
|---|---|
| Take profit | price reaches the target |
| Stop loss | price reaches the stop (original, break-even or trailed) |
| **Time stop** | after **45 minutes**, if the trade is still **below +0.5R** |
| Momentum reversal | at +0.4R or better, if an opposing M1 candle pattern (strength >= 0.8) appears **and** M1 MACD turns against the trade |
| News | 3 minutes before a high-impact event |
| Weekend | Friday from 21:00 UTC |
| Risk halt | daily loss limit or max drawdown |

Realistically: **a losing or stalled trade is gone within about 45 minutes. A good trade usually finishes in 5 to 60 minutes**, and one that keeps moving with the trailing stop can run longer. Trades are never held overnight by design.

### Break-even and trailing (stop moves in profit)

"R" is the distance from entry to the original stop.

1. **+0.8R**: stop moves to entry + spread + 0.1R (break-even, tiny profit).
2. **+1.2R and above**: stop trails at **price - 0.7R**. It moves only when that improves the stop by more than 0.1R.
3. The take profit stays in place.

---

## 6. Risk management explained

| Setting | Default | What it does |
|---|---|---|
| `risk_per_trade_pct` | 2% | Target loss if the stop is hit = equity x 2%. |
| `micro_max_risk_pct` | 7% | Safety valve for small accounts (see below). |
| `max_total_open_risk_pct` | 8% | Sum of the risk of all open trades must stay under this. |
| `max_positions` | 3 | Max simultaneous trades. |
| `max_same_usd_direction` | 2 | EURUSD buy, GBPUSD buy and gold buy are all "short USD". Max 2 in the same dollar direction. |
| `daily_loss_limit_pct` | 8% | Halts trading until the next UTC day. |
| `max_drawdown_pct` | 25% | Kill switch from peak equity. |
| `max_consecutive_losses` / `cooldown_minutes` | 3 / 15 | Pause after 3 losses in a row. |
| `symbol_cooldown_minutes` | 5 | Symbol rests after a loss. |
| `min_score` / `min_rr` | 62 / 1.5 | Quality filters. |
| `max_spread_to_sl` | 25% | Cost filter. |
| `break_even_r` / `trail_start_r` | 0.8 / 1.2 | Profit protection. |
| `max_trade_minutes` | 45 | Time stop. |

### The sizing formula (`risk.py`)

```
risk $       = equity x risk_per_trade_pct
loss per lot = stop distance (in price) / tick size x tick value
lots         = risk $ / loss per lot       -> rounded DOWN to the lot step (0.01)
```

- If `lots` is at least the broker minimum (usually 0.01): **trade that size**.
- If `lots` is below the minimum:
  - the minimum lot's real risk <= `micro_max_risk_pct` of equity: **trade 0.01 anyway**, with more risk than 2%;
  - otherwise the trade is **skipped** ("Unaffordable").

This is why the bot behaves differently on a tiny account than on a large one.

---

## 7. Why $100 still opens 0.01 lots

It is correct behaviour, caused by **three things together**:

1. **2% of $100 is only $2.** With a stop of 12 pips, one full 0.01 lot already risks $1.20 (1.2%). The next step up, 0.02 lots, would risk $2.40, which is over the 2% target, so it is not used.
2. **Lots are always rounded DOWN** to the broker's step (0.01). 0.016 lots becomes 0.01, never 0.02.
3. **The stops come from M5 volatility**, and they are often 10 to 15 pips on GBPUSD and a few dollars on gold, so the dollar loss per lot is large.

Lots for EURUSD/GBPUSD at the default 2% risk (rounded down):

| Equity | 2% target | 6-pip stop | 10-pip stop | 15-pip stop |
|---|---|---|---|---|
| $12 | $0.24 | 0.01 *(min lot, real risk $0.60 = 5%)* | rejected *(0.01 = $1.00 = 8.3% > 7%)* | rejected *(12.5%)* |
| $50 | $1.00 | 0.01 | 0.01 | 0.01 *(real risk $1.50 = 3%)* |
| **$100** | **$2.00** | **0.03** | **0.02** | **0.01** |
| $250 | $5.00 | 0.08 | 0.05 | 0.03 |
| $500 | $10.00 | 0.16 | 0.10 | 0.06 |
| $1,000 | $20.00 | 0.33 | 0.20 | 0.13 |

So at $100 you see 0.01 whenever the stop is about 12 pips or wider, and on gold almost always (a $3 stop = $300 per full lot, so 2% = $2 allows only 0.0066 lots, which is rounded up to the 0.01 minimum at about 3% risk).

**Nothing is wrong.** The size scales with the account. You will see 0.02, 0.03 and so on as the balance grows or as stops get tighter.

---

## 8. What happens if you raise the risk settings

### Important: three limits work together

On small accounts, the binding limit is often **not** `risk_per_trade_pct`. Changing one number alone often has no effect, or blocks trades:

```
risk_per_trade_pct      -> how many lots you WANT
micro_max_risk_pct      -> the most a minimum lot may risk
max_total_open_risk_pct -> total of all open trades, usually the real ceiling at $12
daily_loss_limit_pct    -> how many losses until the bot stops for the day
```

### $12 account

Default: 2% = $0.24 target, 7% cap = $0.84, total open cap 8% = $0.96, daily limit 8% = $0.96.

| Change | Result |
|---|---|
| Nothing (defaults) | 0.01 lot, tight stops only (up to about 8 pips). One trade of $0.60 leaves only $0.36 of room, so a second trade needs a stop of about 3 pips. That is why you typically see 1 to 2 trades, and only when stops are small. Gold is out. |
| `risk_per_trade_pct` 2% to 5% ($0.60) | **No change in lots.** Still 0.01. Nothing is gained. |
| `risk_per_trade_pct` 2% to 10% ($1.20) | Tries 0.02 lots on a 6-pip stop, risk $1.20, which is **above the 8% total cap ($0.96)**, so the trade is **blocked**. Fewer trades, not more. |
| `micro_max_risk_pct` 7% to 15% | Allows 10-pip stops (0.01 lot = $1.00 = 8.3%), but the 8% total cap ($0.96) **still blocks it**. |
| Raise all four limits together (for example risk 10%, micro cap 15%, total open 20%, daily 15%) | Trades can open, but **one loss costs roughly $1 to $1.70 of $12 (8% to 14%)**. Two losses in a row = 20%+, close to the 25% kill switch ($3). One bad hour wipes out a quarter of the account. |

**Takeaway for $12:** raising risk does not make the bot trade "better", it only makes each loss hurt more. The real fix is more capital (or a cent account), not higher percentages.

### $100 account (10-pip stop on EURUSD, so $1 per 0.01 lot)

Default total cap 8% = $8, daily limit 8% = $8.

| `risk_per_trade_pct` | Lots | Loss if stopped | Win if 2R TP hit | Trades at once (8% cap) | Losses to hit the 8% daily halt |
|---|---|---|---|---|---|
| 1% ($1) | 0.01 | $1.00 | +$2.00 | 3 (limited by `max_positions`) | 8 |
| **2% ($2) default** | **0.02** | **$2.00** | **+$4.00** | **3** ($6 total, limited by `max_positions`) | **4** |
| 3% ($3) | 0.03 | $3.00 | +$6.00 | 2 | 3 |
| 5% ($5) | 0.05 | $5.00 | +$10.00 | 1 | 2 |
| 10% ($10) | 0.10 | $10.00 | +$20.00 | **0 (blocked by the 8% cap)** | n/a |

Rules of thumb:

- Higher risk does not change the **win rate**. It only magnifies both wins and losses.
- Lose 5 trades in a row at **2%** and you are down about 10%. At **5%** you are down about 23%, near the 25% kill switch. With a 40-45% win rate, a run of 5 losses is normal (roughly 1 in 20 sequences), not rare.
- If you raise `risk_per_trade_pct`, **also raise `max_total_open_risk_pct` and review `daily_loss_limit_pct`**, otherwise trades are blocked or the bot halts after one or two losses.
- Professionals typically risk **0.5% to 1%** per trade, rarely more than 2%.

---

## 9. What can be improved

Ordered by impact. "Settings" means it can be done from the app. "Code" means development work.

### A. Capital and execution reliability (biggest wins)

| # | Improvement | Why | Type |
|---|---|---|---|
| 1 | **Use a larger balance or a cent account** | At $12 the minimum lot forces 3-7% risk and 1 to 2 trades. At $100+ the 2% rule starts to work, and at $500+ it works properly. | Account |
| 2 | **Run MT5 and the bridge on a VPS, not a home PC** | Today the bot trades only while your PC is on, logged in, with internet and MT5 open. A sleep, reboot or router glitch leaves open trades unmanaged (no trailing). A Windows VPS near the broker also gives lower latency. | Infra |
| 3 | **Remove secrets from the repository** | `config.py` and `mt5_bridge.py` contain default API keys (`ENGINE_API_KEY`, `INTERNAL_API_KEY`). If the repo is, or ever becomes, public or shared, anyone could control the engine. Move them to environment variables only, **rotate the current keys**, and fail to start if a key is missing. | Code / security |
| 4 | **Heartbeat alert when the bridge goes offline** | The engine already alerts on disconnect, but also stop opening new trades and notify immediately when open trades cannot be managed. | Code |

### B. Smarter analysis ("trade like a pro")

| # | Improvement | Why | Type |
|---|---|---|---|
| 5 | **Make the H4 + H1 trend a hard filter** | Today the higher timeframes only contribute about 30 of 100 points, so counter-trend trades can still pass. Require "no trade against H4 and H1 bias" (allow exceptions only for a confirmed false breakout at a major D1/H4 zone). Fewer, higher-quality trades. | Code |
| 6 | **Use limit/pending orders at the pullback zone** | Now the bot sends market orders at the current price. Placing a limit order at the zone/EMA retest gives a better entry price, a tighter stop and a higher R:R, and it pays less spread. | Code |
| 7 | **Partial take-profit** | Close 50% at +1R, move the stop to break-even, let the rest run to 2R-3R. Lifts the win rate and smooths the equity curve. | Code |
| 8 | **ATR/structure-based trailing** | The trail is a fixed 0.7R behind price. Trailing under the latest M5/M15 swing or by a multiple of ATR avoids being shaken out by normal noise. | Code |
| 9 | **Session awareness per symbol** | Gold and GBP are most active in the London and New York sessions. The bot trades 06:00-20:00 UTC. Restrict to **07:00-16:00 UTC** (London plus overlap) and avoid the first and last hour of illiquid periods. | Settings |
| 10 | **Add "market regime" detection** | Trending vs ranging markets need different logic. Range = fade the zone edges, trend = pullback entries. Currently one style is applied to both, with only ADX/ATR scoring. | Code |
| 11 | **Stricter cost filter** | `max_spread_to_sl` 25% means a spread can eat up to 0.25R per trade. With a 6-pip stop and a 1.5-pip spread, 0.25R is gone before the trade moves. Use **15%** and prefer wider, better-located stops. | Settings |
| 12 | **Higher quality thresholds** | `min_score` 62 to 68-70 and `min_rr` 1.5 to 1.8. Fewer trades, better ones. Validate on demo first. | Settings |
| 13 | **Correlation-aware sizing** | EURUSD and GBPUSD in the same direction are nearly one position. Count them as one bet for risk, not two. | Code |
| 14 | **More instruments** | Adding other liquid pairs (USDJPY, AUDUSD, USDCAD) gives more independent opportunities, so the bot waits less. Needs symbol mapping and news currency mapping. | Code |
| 15 | **Multi-timeframe confirmation of the trigger** | Require M1 trigger plus M5 candle close in the same direction before entering, to avoid M1 noise. | Code |

### C. Risk management upgrades

| # | Improvement | Why | Type |
|---|---|---|---|
| 16 | **Dynamic risk** | Reduce risk to 1% after 2 losses or a drawdown over 10%, return to 2% after recovery. Never increase beyond a fixed ceiling. | Code |
| 17 | **Daily profit lock** | Stop trading for the day after +2R to +3R total. Protects good days from being given back. | Code |
| 18 | **Max trades per day** | Prevents over-trading in choppy conditions. | Code |
| 19 | **Pre-trade margin and "risk after stop" display** | Show in the app the real risk in $ and % *before* the bot opens (the scan already has `riskAmount` and `riskPctAtMinLot`; surface them clearly). On small accounts it shows that 0.01 is above the 2% target. | App |
| 20 | **Respect symbol rules** | Use broker `trade_stops_level`, freeze level and per-symbol commission in the plan and R:R. | Code |

### D. Measurement (what separates pros from hobbyists)

| # | Improvement | Why | Type |
|---|---|---|---|
| 21 | **Store the score components with every trade** | You can then see which components (HTF, location, trigger...) actually predict wins and tune the weights with data, not feelings. | Code |
| 22 | **Backtest/replay engine** | There is a paper broker, but no historical replay. Replaying 6-12 months of M1/M5 data lets you test `min_score`, `min_rr`, trailing and sessions safely, with walk-forward validation. | Code |
| 23 | **Better performance tracker** | It uses the last 20 trades of each setup. That is too few to be reliable and can swing scores by chance. Use larger samples and shrink towards neutral. | Code |
| 24 | **Equity curve, expectancy, max drawdown and profit factor dashboard** | A bot is judged by expectancy (average R per trade), not by individual wins. | App |
| 25 | **Automated tests** | There is only a smoke test. Add unit tests for sizing, trailing, structure and the news filter. | Code |

### E. App quality-of-life

| # | Improvement | Type |
|---|---|---|
| 26 | Remember the selected chart timeframe and symbol (currently resets to M5/EURUSD) | App |
| 27 | Show "why no trade" (the blocked reasons) in a simple banner on the home screen | App |
| 28 | Show per-timeframe bias arrows (D1, H4, H1, M30, M15, M5, M1) so you can see the top-down picture the bot sees | App |
| 29 | Push notification with the full plan before the entry (already partly done with the "TRADE_FOUND" event) | App |

---

## 10. Suggested roadmap

**Phase 1: Safe settings (today, no code)**

- Keep trading **demo** (or a very small live balance) while you gather data.
- Allow only EURUSD and GBPUSD while the balance is under ~$100.
- `max_positions` 2, `min_score` 66-68, `min_rr` 1.8, `max_spread_to_sl` 0.15.
- `trade_start_utc` 7, `trade_end_utc` 16.
- Do **not** raise `risk_per_trade_pct` above 2% until the balance supports it (section 8).

**Phase 2: Reliability and security (1 to 2 days)**

- Remove default keys from the code, rotate them, move to environment variables.
- Put MT5 and the bridge on a VPS.

**Phase 3: Smarter trades (about 1 to 2 weeks)**

- H4/H1 hard filter, partial take-profit, structure-based trailing, daily trade cap.
- Log score components for every trade.

**Phase 4: Prove it (ongoing)**

- Build a backtest/replay tool. Run it for 6 to 12 months of data and change a setting only if it improves expectancy over 100+ trades.
- Add pending-order entries and regime detection once the basics are stable.

---

### A reality check

- No setting guarantees profit. Short-term scalping is cost-sensitive (spread, slippage) and any bot can have long losing streaks.
- Small accounts amplify every weakness: the minimum lot, the spread and a single loss are all a big percentage of $12.
- The strategy you like (top-down bias, M5 pullback, M1 trigger) is a sound structure. The most valuable next steps are **more capital, tighter quality filters, a hard higher-timeframe filter, and measuring results with data** before increasing risk.
