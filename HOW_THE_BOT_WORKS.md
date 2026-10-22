# How the Forex Bot Works

This document explains the trading engine in `engine/app/` as the code currently behaves. It is written from reading the code (`config.py`, `analyzer.py`, `bot.py`, `risk.py`, `structure.py`, `marketdata.py`, `news.py`). **Nothing in the code was changed to produce it.**

> Numbers marked "approx." depend on your broker's contract specs and live volatility. Check the real values in the app's scan screen (`riskPctAtMinLot`, `blockedReasons`, `lots`, `riskAmount`).

---

## 1. Short answers to your questions

| Question | Answer |
|---|---|
| Does it look at D1, H4, H1, M30, M15 and then M5, or only M5? | **All of them.** It loads 7 timeframes (D1, H4, H1, M30, M15, M5, M1) for every symbol. The higher timeframes decide the *direction bias*. M5 decides the *setup, stop loss and target*. M1 is the *trigger*. |
| Why does the chart always show 5 minutes? | M5 is the main working timeframe (stops, ATR, entries are measured on it), so it is the natural chart to display. It does not mean the bot ignores the others. |
| Is risk a percentage? | Yes: **2% of equity per trade** by default, but on a very small account the broker's minimum lot forces a higher real risk (see section 5). |
| Does the stop loss trail when in profit? | **Yes.** Break-even at +0.8R, then a trailing stop from +1.2R (section 6). |
| How long does a trade last? | Typically a few minutes to about 45 minutes. A trade that has not reached +0.5R after 45 minutes is closed. Trades that are working can run longer. |
| Why only 2 trades on $12? | Several guards stack up: only 2 symbols are affordable, one trade per symbol, a USD-correlation limit of 2, and an 8% total open-risk cap (section 7). |

---

## 2. The big picture (one loop, every few seconds)

```
every ~2 s  : _tick()  -> manage open trades, check halts, maybe open a trade
every ~5 s  : _scan()  -> (when the bot is running) rescore all 3 symbols
every ~20 s : _scan()  -> (when the bot is stopped, display only)
```

1. **Scan** XAUUSD, EURUSD and GBPUSD. For each one, build all 7 timeframes with indicators, market structure and support/resistance zones.
2. **Score** both directions (buy and sell) from 0 to 100 and keep the better one.
3. **Build a trade plan** (entry, stop loss, take profit) and size the position.
4. **Block** the candidate if any rule fails (news, spread, score, R:R, affordability, and so on).
5. **Rank** the symbols and open the best tradable one that passes the portfolio guards.
6. **Manage** the open trade: break-even, trailing, time stop, news and reversal exits.

---

## 3. How the timeframes are used

### 3.1 Top-down bias (soft filter, not a hard gate)

For each timeframe the bot computes a **trend value** from -1 to +1 using:

- price vs EMA20 (25%)
- EMA20 vs EMA50 (20%)
- EMA50 vs EMA200 (15%)
- MACD histogram sign (15%)
- market structure, i.e. higher highs/higher lows or lower highs/lower lows (25%)
- all scaled by trend strength (ADX), so weak or choppy trends count for less

The timeframes are then combined into one **bias**:

| Timeframe | Weight |
|---|---|
| D1 | 15% |
| H4 | 25% |
| H1 | 25% |
| M30 | 15% |
| M15 | 20% |

So the **H4 and H1 matter most**, then M15, then D1 and M30. M5 and M1 are not part of the bias. They are used for the setup and the trigger.

### 3.2 The 100-point score

A direction is scored from six components:

| Component | Max | What it measures |
|---|---|---|
| **A. Higher-timeframe alignment** | 30 | Does the trade agree with the bias above? If it is clearly against the bias, -12 is applied. |
| **B. Setup momentum** | 20 | M5 trend, M5 RSI "room to run", M5 MACD accelerating, M15 ADX confirming. |
| **C. Location** | 20 | Pullback to the M5 EMA20/50, sitting at a support/resistance zone, inside an order block, breakout-retest, Bollinger extreme, right side of VWAP. Chasing an extended price is penalised. |
| **D. M1 trigger** | 15 | A candle pattern on M1 or M5 (engulfing, pin bar, stars, momentum candle, inside-bar breakout), M1 EMA alignment, M1 micro break of structure, false-breakout reversal. |
| **E. Market regime** | 10 | ADX in a healthy range and volatility neither dead nor spiking. |
| **F. Volume** | 5 | M1 and M5 tick volume above average. |

Then a small **performance adjustment** is added from the last 20 results of that symbol and setup type: -8 if the win rate is under 30%, -3 under 40%, +3 over 60%.

### 3.3 The entry gates

A candidate is `tradable` only if **all** of these pass (`analyzer.py`):

- score >= **62** (a "momentum only" setup with no pullback or zone needs **70**)
- **M1 trigger component >= 4** ("Waiting for M1 trigger" otherwise)
- net reward:risk >= **1.5**
- spread <= **25%** of the stop distance
- no high-impact news (30 minutes before to 15 minutes after) for the relevant currencies
- the position is **affordable** (section 5)
- the symbol is enabled in settings

So the bot waits for the big picture to agree, then for M5 to give a good location, and finally for M1 to confirm. That is why it can sit idle for a long time.

Important: because the higher-timeframe bias is **a score, not a veto**, a trade against the bias can still pass if M5/M1 are very strong. It costs -12 points plus lost alignment points, so it is hard but not impossible.

---

## 4. Stop loss, take profit and trade length

Stops and targets are built on **M5** (`build_plan`):

- **Stop loss** sits behind the nearest M5 swing low (buy) or high (sell) from the last 40 bars, plus 0.3 x ATR. It is clamped between about 0.8 x ATR(M5) (or 4 x spread) and 2 x ATR(M5).
- **Take profit** is **2R** by default (twice the stop distance).
- If a meaningful S/R zone lies ahead, the target is placed just before it, between 1.3R and 3R. If the zone is too close (under 1.3R), the setup loses 8 points and usually fails the R:R rule.

Because stops are about 1 to 2 M5 ATRs, trades are **short-term scalps/intraday moves**, usually a few pips on forex and a few dollars on gold.

### How long it stays in a trade

There is no fixed duration. A trade ends when one of these happens:

| Exit | Rule |
|---|---|
| Take profit | Price reaches the 2R (or zone-limited) target. |
| Stop loss | Price hits the original or trailed stop. |
| **Time stop** | After **45 minutes** (`max_trade_minutes`) if the trade is **below +0.5R**, it is closed. |
| Momentum reversal | At +0.4R or more, if an opposite M1 candle pattern (strength >= 0.8) appears **and** M1 MACD turns against the trade, the profit is taken. |
| News | Closed 3 minutes before a high-impact news event. |
| Weekend | Closed on Friday from 21:00 UTC. New entries stop on Friday from 20:00 UTC. |
| Risk halt | Daily loss limit or max drawdown triggers a close of everything. |

A trade that is already above +0.5R when 45 minutes pass is **not** forced out, so a good trade can run longer under the trailing stop.

---

## 5. Risk management: the default settings

These are the defaults in `RiskConfig` (`config.py`). They can be changed live from the app and are saved to `data/risk_config.json` on the server.

| Setting | Default | Meaning |
|---|---|---|
| `risk_per_trade_pct` | **2.0%** | Target money risked per trade = equity x 2%. |
| `micro_max_risk_pct` | **7.0%** | Small-account exception: if the minimum lot risks more than 2%, it is still allowed up to 7%. |
| `max_total_open_risk_pct` | **8.0%** | Sum of the risk of all open trades. |
| `max_positions` | 3 | Maximum simultaneous trades. |
| `max_same_usd_direction` | 2 | Max 2 trades betting the same way on the dollar. |
| `daily_loss_limit_pct` | 8.0% | Halts trading until the next UTC day. |
| `max_drawdown_pct` | 25.0% | Kill switch from the session's peak equity. |
| `max_consecutive_losses` | 3 | Then a cooldown. |
| `cooldown_minutes` | 15 | Pause after 3 losses in a row. |
| `symbol_cooldown_minutes` | 5 | Pause on a symbol after it loses. |
| `min_score` | 62 | Minimum opportunity score. |
| `min_rr` | 1.5 | Minimum net reward:risk. |
| `max_spread_to_sl` | 25% | Spread vs stop distance. |
| `news_before_min` / `news_after_min` | 30 / 15 | News blackout window. |
| `break_even_r` | 0.8 | Move stop to break-even at +0.8R. |
| `trail_start_r` | 1.2 | Start trailing at +1.2R. |
| `max_trade_minutes` | 45 | Time stop (if under +0.5R). |
| `trade_start_utc` / `trade_end_utc` | 6 / 20 | Only open trades from 06:00 to 20:00 UTC. |
| `min_entry_gap_seconds` | 20 | Minimum gap between entries. |

### Position sizing (`risk.py`)

```
risk $        = equity x risk_per_trade_pct / 100
loss per lot  = stop distance / tick size x tick value
lots          = risk $ / loss per lot   (rounded DOWN to the broker's lot step)
```

If `lots` rounds below the broker's minimum lot:

- if the **minimum lot's risk is <= 7% of equity**, it trades the **minimum lot** anyway;
- otherwise the trade is **skipped** ("Unaffordable: min lot would risk ...").

The percentage is calculated on **equity**, so it shrinks and grows with your account.

---

## 6. When you are in profit: break-even and trailing

"R" means the stop distance. If you risked 6 pips, then +1R = +6 pips. The check runs every ~2 seconds.

1. **+0.4R**: the "momentum reversal" exit becomes active (see section 4).
2. **+0.8R: break-even.** The stop moves to entry + spread + 0.1R, so a reversal costs nothing or gives a tiny profit.
3. **+1.2R and above: trailing stop.** The stop is set to **price - 0.7R** (for a buy) and only moves when it improves by more than 0.1R. So once at +1.2R the stop locks about +0.5R, and it follows price up as it keeps moving.
4. The take profit stays at the original target. If price reaches it, the trade closes with the full gain.

In the app, a stop-out after break-even is labelled "Break-even/trailing stop hit".

---

## 7. What happens with a $12 account (and why only 2 trades)

### 7.1 The real risk is not 2%

- 2% of $12 = **$0.24** target risk.
- The smallest lot (0.01) usually risks more than that. Approx. for forex, 0.01 lot is about **$0.10 per pip**. A 6-pip stop = about $0.60 = **5% of $12**.
- Because the minimum lot is below the 7% cap ($0.84), the bot **accepts the minimum lot** at roughly 3% to 7% risk per trade. That is above the intended 2%.
- At 0.01 lot, a forex stop wider than about **8 pips** (approx. 0.84 / 0.10) is **rejected** as unaffordable.

### 7.2 Gold is practically blocked

On most brokers 0.01 lot of XAUUSD is about 1 ounce, so about $1 of loss per $1 of price move. A normal M5 stop on gold (about $1 to $5) risks **8% to 40%** of $12, above the 7% cap. So gold is almost always "Unaffordable" at this size. The bot therefore only trades **EURUSD and GBPUSD**.

### 7.3 Why you only saw 2 open trades

Several limits stack:

1. **Only 2 symbols are affordable** (EURUSD, GBPUSD), and the bot allows **one open trade per symbol**.
2. **USD-correlation guard**: EURUSD, GBPUSD and XAUUSD all move against the dollar, so at most 2 trades in the same USD direction are allowed.
3. **Total open risk cap**: 8% of $12 = **$0.96**. Two minimum-lot trades at roughly $0.45 each already use it, so a third would be refused anyway.
4. Even a free slot still needs score >= 62, an M1 trigger, spread, news and R:R checks to pass, between 06:00 and 20:00 UTC on weekdays.
5. After a loss, that symbol rests for 5 minutes. After 3 losses in a row, everything rests for 15 minutes.
6. Daily loss limit: 8% of $12 = **$0.96**. That is only about two losing minimum-lot trades, after which the bot is halted until the next UTC day.
7. The drawdown kill switch is at 25% = **$3**.

In short, **$12 is below the size the risk model was designed for**. It works as a demo of the logic, but it has no room for a normal losing streak.

### 7.4 When does the 2% rule really start working?

Roughly when `equity x 2% >= 0.01-lot risk`. For a typical 6-pip to 10-pip forex stop (0.01 lot = $0.60 to $1.00 risk), that is around **$30 to $50 of equity**. For comfortable operation, $100 or more (and then gold becomes affordable at larger balances).

---

## 8. Other safety features

- **News**: avoids high-impact USD/EUR/GBP events, and closes 3 minutes before one.
- **Spread**: skips the trade if the spread widens before entry (also re-checks the price has not moved more than 0.3 x stop since the plan).
- **Margin**: skips if the required margin is more than 60% of free margin.
- **Trading hours**: 06:00 to 20:00 UTC, weekdays only, closes before the weekend.
- **Self-learning nudge**: each symbol/setup's last 20 results adjust its score slightly.
- **Disconnect handling**: status becomes DISCONNECTED with an alert, and it retries.

---

## 9. How to improve risk, trade quality and "smart trades"

Everything below is a **suggestion**. Items in 9.1 can be changed live in the app's risk settings. Items in 9.2 would need code changes.

### 9.1 Settings (no code changes)

1. **Fund the account properly, or use a cent account.** This is the biggest improvement. With $12, minimum-lot risk is 3% to 7% per trade no matter what you set. A cent account (if your broker offers one) or a balance of $50 to $100 lets the real risk match the 2% setting.
2. **Always test on a demo account** with the same balance first.
3. **Keep `micro_max_risk_pct` low.** Do not raise it just to get more trades. It increases how much of $12 is at stake per trade. If you want to be stricter, lowering it to about 5% will skip wide-stop setups.
4. **Stricter quality**: raise `min_score` to about 68-70 and `min_rr` to about 1.8. You get fewer trades but better ones.
5. **Best hours**: set `trade_start_utc` to 7 and `trade_end_utc` to 16. That covers London and the London/New York overlap, where EURUSD and GBPUSD have the best liquidity and tightest spreads. Avoid the quiet late session.
6. **Keep `max_positions` at 2** on a small account, so it matches the real capacity.
7. **Trail earlier if you want to protect profit**: `break_even_r` 0.8 to 0.7, `trail_start_r` 1.2 to 1.0. This protects more winners but also stops out some trades that would have reached TP. Test on demo.
8. **Time stop**: 45 minutes suits the M5/M1 style. Do not lengthen it, because slow trades just tie up the limited risk budget.
9. **Check `Allowed symbols`**: with a small balance, leave only EURUSD and GBPUSD enabled so gold never wastes a scan slot.
10. **Watch the scan screen's "blocked reasons"**. They tell you exactly why no trade is taken: spread, score, M1 trigger, unaffordable, news.

### 9.2 Code-level ideas (not done, for future work)

- **Make the higher-timeframe bias a hard filter**: do not allow trades against the H4/H1 trend at all.
- **Partial take profit**: close half at +1R, move the rest to break-even and let it run.
- **ATR-based trailing** instead of a fixed 0.7R.
- **Session-aware spread rules**: a stricter spread limit around the rollover (about 21:00 to 23:00 UTC).
- **Dynamic risk**: lower the risk after a loss streak and raise it slightly after a winning streak, with a fixed ceiling.
- **Correlation-aware sizing**: treat EURUSD plus GBPUSD in the same direction as one larger bet, not two.
- **Backtest and walk-forward** the min score and R:R values on your broker's historical data before changing defaults.
- **Daily trade-count cap** and a "stop after a daily profit target" option.
- **Journal export**: record the score components of every trade, so you can see which components actually predict wins.

### 9.3 Realistic expectations

- It is a rules-based scalper. There is no guarantee of profit, and a 12-dollar account can be wiped by a bad streak, spreads, slippage or news spikes.
- Higher win rate and R:R are *tested*, not assumed. Let the bot run on demo for at least 50 to 100 trades before trusting any settings change.
- Never risk money you cannot afford to lose.

---

## 10. Quick reference: where things live

| What | File |
|---|---|
| Settings and defaults | `engine/app/config.py` |
| Multi-timeframe scoring, trade plan, entry gates | `engine/app/analyzer.py` |
| Swings, structure, zones, order blocks, candle patterns, breakouts | `engine/app/structure.py` |
| Position sizing | `engine/app/risk.py` |
| Main loop, entries, break-even, trailing, exits, halts | `engine/app/bot.py` |
| News filter | `engine/app/news.py` |
| Timeframe data and caching | `engine/app/marketdata.py` |
| MT5 order execution | `engine/app/broker/mt5_broker.py` |
| PC-side MT5 bridge | `MT5-Bridge-Installer/scripts/mt5_bridge.py` |
