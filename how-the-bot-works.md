# How JoelMTrader works

Trade Now does not place an order. It turns the scanner on. The bot keeps looking at gold, euro, and pound, and it only sends an order when one pair clears every gate below.

Your 4pm session is still inside that rule. From 4:00pm to now (about 6:43pm, UTC+2) the market session is open. The screen stays on **Scanning the markets** because none of the three pairs has been good enough to buy or sell.

## 1. What happens when you press Trade Now

1. The Flutter app calls the API. The API tells the Python engine to start a session.
2. The engine checks that MT5 is connected. If it is not, Trade Now fails and the app asks you to link the account first.
3. Status becomes `SCANNING`.
4. Every **5 seconds** the engine scores **XAUUSD, EURUSD, and GBPUSD**.
5. Every **2 seconds** it checks whether the best score is allowed to become a real order.
6. If nothing qualifies, it scans again. That loop is the whole point of the wait.

The gold banner on the dashboard is the reason for the latest pass. It names the best pair, its score, and the first things that blocked it. Open that pair’s row. Green lines are reasons in favour. Gold lines are penalties. Red lines are the blocks. A red line means no order.

## 2. Where a trade idea comes from

For each symbol the engine reads seven timeframes: **D1, H4, H1, M30, M15, M5, M1**.

It scores both buy and sell, then keeps the stronger side. The score is out of 100.

| Piece | Max | What it looks at |
| --- | --- | --- |
| Higher timeframe | 30 | Daily through M15 trend, EMAs, MACD, structure |
| Momentum | 20 | M5 trend, RSI room, MACD acceleration, M15 ADX |
| Location | 20 | Pullback to M5 EMA, support or resistance, order block, breakout retest, VWAP |
| M1 trigger | 15 | Candlestick pattern, M1 EMA alignment, micro break |
| Regime | 10 | Trend strength and whether volatility is normal |
| Volume | 5 | Tick volume versus its average |

Setups it can name:

- **TREND_PULLBACK** — price came back into the M5 value area
- **BREAKOUT_RETEST** — a breakout held the retest
- **FALSE_BREAKOUT_REVERSAL** — a failed break the other way
- **MOMENTUM** — direction only, with no pullback or zone. This one is harder to pass

The plan is a market entry at the current bid or ask. The stop sits beyond the nearest swing, inside 0.8 to 2.0 times the M5 ATR. The target starts at **2R** (twice the stop distance) and is shortened if a strong opposing zone is closer, up to 3R.

## 3. The colours on the ranking are not the entry rule

The number on each row is the score, not a promise.

| What you see | Meaning |
| --- | --- |
| Grey number | Score under 45 |
| Gold number | Score 45 to 61 |
| Green number | Score **62 or more** |
| Green border and **SELECTED** | That pair cleared every block and is the one the bot may send |
| Gold hourglass banner | Nothing is tradable. Still scanning |
| Blue | Brand colour, or the **DEMO ACCOUNT** tag. Blue does not mean “take the trade” |

A green 62 is the minimum score. It is not enough by itself.

**70 is not the normal line.** It appears only for a momentum-only setup: those need **70** (the normal 62, plus 8) because they have no pullback or zone behind them.

A trade is sent only when `tradable` is true. That means every line below is clear:

- Score at least **62** (70 if the setup is momentum only)
- M1 trigger component at least **4**
- Reward to risk at least **1.5** after spread
- Spread no more than **25%** of the stop distance
- Symbol is turned on in Settings
- No high-impact news block on that currency
- The minimum lot is affordable for the account
- The lot size came back greater than zero

Then, even a tradable pair can still be skipped on the way to the broker:

- Outside **06:00–20:00 UTC** (08:00–22:00 your time). Weekend is off. Friday after 20:00 UTC does not open new trades.
- Already **3** open trades
- Already **2** open trades in the same US-dollar direction (buy EUR, buy GBP, and buy gold all count as short USD)
- This symbol is already open
- Combined open risk would pass **8%** of equity
- Less than **20 seconds** since the last entry attempt
- Price moved more than 30% of the stop, or the spread widened, between the scan and the click to send
- Not enough free margin (the order needs margin under 60% of free margin)
- MT5 rejects the order. That symbol then waits **2 minutes**

So a blue-looking row, or a number above 70, does not open a trade. **SELECTED** plus a green border is the only “this one can be sent” state. If you do not see that, scanning is correct.

## 4. Why it has been scanning since 4pm

4:00pm your time is 14:00 UTC. The session runs until 20:00 UTC, which is 10:00pm your time. You are inside the trading window. The bot is allowed to enter. It has chosen not to.

It re-scores about every 5 seconds. Most of those passes fail one of the gates in section 3. The usual ones on a quiet afternoon are:

- score still under 62
- “Waiting for M1 trigger”
- momentum setup under 70
- reward to risk under 1.5
- spread too wide versus the stop
- news window
- minimum lot would risk more than the account is allowed to risk

Read the gold banner. It is written from those blocked reasons on the best pair.

Scanning for a few hours with zero trades is normal. The bot does not have a quota of trades per hour.

## 5. How many trades, and how much it risks

Defaults, unless you changed them in Settings:

| Rule | Default |
| --- | --- |
| Risk per trade | **2%** of equity |
| Hard cap if the broker’s minimum lot is larger than 2% | **7%** of equity, otherwise skip the trade |
| All open trades together | **8%** of equity |
| Open trades at once | **3** |
| Same USD direction at once | **2** |
| Daily loss | **8%** of the day’s starting balance, then halt until the next UTC day |
| Drawdown from the session peak | **25%**, then halt and close trades |
| Losses in a row | **3**, then a **15 minute** cooldown |
| After a loss on one symbol | that symbol waits **5 minutes** |
| Time stop | **45 minutes** if the trade is still under +0.5R |
| Move stop to break-even | at **+0.8R** |
| Start trailing the stop | at **+1.2R** |

Lot size is `equity × 2% / loss per lot`, rounded **down** to the broker’s lot step. On a small account the broker minimum (often 0.01) can cost more than 2%. The bot still takes it only if that cost is within **7%**. Above 7%, the row shows a red “Unaffordable” line and the trade is skipped. The row also shows **Risk at minimum lot** so you can see that number before an order exists.

While a trade is open the engine still scans. It can open another pair if the caps above allow it. It also manages the open stop: break-even, trail, news flatten (about 3 minutes before high-impact news), Friday weekend flatten, and the 45-minute time stop.

Stop trade closes the session. By default it also closes the open positions and sends the session push.

## 6. How the Flutter app is built

The app is one Flutter project, `frontend`, package name `waya_fx_bot`. It talks to the Java API. The API talks to the Python engine. The screen does not calculate the score. It draws whatever the engine last published.

What keeps it light:

- **Flutter Material 3 only.** No UI kit, no web view, no chart package. Screens are small widgets: a card, a title, a score row, a button.
- **Shared pieces live in** `lib/widgets/common.dart`: `AppCard`, `SectionTitle`, `StatusPill`, `Tag`, `Pressable`, `SelectChip`, `ToggleLine`. Pages compose those instead of restyling Material buttons on every screen.
- **State is** `provider` plus one `AppState`. The dashboard polls the API. It does not keep a second copy of the trading logic.
- **Charts are** `CustomPaint` painters in the app, not a charting library.
- **Logo and icon** are the SVG files in `assets/images`, drawn with `flutter_svg`.
- **Type is Inter**, registered in `pubspec.yaml` and set as `fontFamily` on the theme.
- **Colour** is one seed blue (`#0000FF`) in `lib/core/theme.dart`, plus green, gold, red, and slate in `Palette` for profit, waiting, loss, and inactive scores.
- **Text can be selected** because pages and dialogs sit inside a `SelectionArea`. Buttons use a small press widget that still lets you drag across the label.

The ranking card is `_RankingCard` and `_RankRow` in `lib/pages/dashboard_page.dart`. The bar colour is chosen there: green from 62, gold from 45, slate below that. The shell is a single scaffold with a side list of pages, not a new activity per screen.

## 7. The notification icon

The mark beside the battery was an exclamation point because the Android status icon file was drawn as a circle with an exclamation. Android status icons can only be a white shape on a transparent background, so that drawing is exactly what the bar showed.

That file is now three white bars, the same chart mark as the logo. Windows toasts use the desktop app icon instead of a missing icon.

Run the Android app again from Android Studio, and run the desktop app again, so the new icon is compiled in. A notification already sitting in the shade keeps the old picture until the next alert arrives.
