# Lauren's Trading Bot: Build Spec for Claude Code (v2)

Drop this file into an empty folder as `CLAUDE.md`, open Claude Code there, and say: **"Read CLAUDE.md and build Phase 1."**

v2 changes v1 (Nov 9 2026) after a data check on 1990-2026 S&P 500 and VIX history.
Every change is marked **[v2]** with the reason. Evidence: `research/FINDINGS.md`.

## 1. What we are building

A personal options bot that sells defined-risk XSP put spreads only when the market regime allows it. Rules come from Lauren's own research (A+ Insight Pro scan transcripts, mined into Playbook v1, Nov 9 2026). No outside signals, no ticker tips, no flow alerts.

- Broker: **Alpaca** (paper first). Python, `alpaca-py` SDK.
- Account: **$6,000**.
- Default mode: **PAPER**. Live trading is locked (see section 9).

**[v2] Honest expectation.** Simulated on 1990-2026, these rules earn about 3-4% a year on $6,000 with perfect fills, and lose money once slippage reaches about 2 cents per spread. Execution quality is the whole game. Build the bot to measure fills from day one.

## 2. Hard rules for you, Claude Code

- Never switch to live trading. Never edit the live-trading lock. Lauren does that by hand.
- Never raise a risk limit in section 6 without Lauren saying so in chat.
- Every rule lives in `config.yaml`, not hard-coded.
- Every decision gets logged with a reason, including "no trade today" and why.
- Keys live in `.env`. Add `.env` to `.gitignore` before the first commit.
- If something in Alpaca's docs differs from this spec (symbols, endpoints, index option support, order types, time-in-force for options), check the current docs, follow them, and tell Lauren what changed.
- **[v2] Fail closed.** If any input is missing or stale (VIX, bars, option chain, account, clock), open nothing new, keep managing exits, log it and alert.
- **[v2] Before every order**, confirm the account in use is the paper account unless the section 9 lock is fully satisfied. Log the account id.

## 3. The strategy (Playbook v2)

### Master switch (regime)
- Pull SPY daily bars, resample to monthly closes, compute the **monthly 5 EMA** (`ewm(span=5, adjust=False)` on monthly closes).
- **[v2]** Use the last **completed** month only. The switch can change only on the first trading day of a month. (v1 didn't say; using the current partial month peeks ahead in a backtest.)
- Last completed monthly close **above** its monthly 5 EMA = **ON**.
- **Below** = **OFF**: no new trades. Existing trades still follow their exits.

### VIX filter
- VIX source: FRED series `VIXCLS` (free CSV, no key). Fallback: Cboe VIX history CSV.
- **[v2]** FRED posts VIXCLS a day late, so the entry decision uses the **prior session's VIX close**. If the newest value is more than 3 sessions old, fail closed.
- The regime grid:

| Regime | VIX | Action |
|---|---|---|
| ON | 20 or higher | Sell put spreads, full size. Best premium per trade. |
| ON | Under 20 | Sell put spreads, half size. Calmest market, thinnest premium. |
| OFF | 20 or higher | Never sell. This is the trap. |
| OFF | Under 20 | No trades. |

**[v2] Corrected backtest basis.** VIX only exists from 1990, so v1's 1950-2026 numbers could not have used it. On real VIX, 1990-2026 (437 months), the share of months where the next month fell more than 5%:

| Cell | Months | Next month fell > 5% |
|---|---|---|
| ON, VIX 20+ | 79 | 10.1% (v1 said 1.2%) |
| ON, VIX < 20 | 247 | 4.5% |
| OFF, VIX 20+ | 82 | 24.4% (v1 said 15.7%) |
| OFF, VIX < 20 | 29 | 10.3% |

The switch is real: OFF + VIX 20+ is the worst cell. ON + VIX 20+ is not the safest market, but it is the best cell per trade, because the 1-expected-move strike sits further away and premium is richer.

### Extra filters from the transcripts (toggles, **[v2] default OFF**)
In the simulation, filters 1 and 4 lowered returns without lowering drawdown. They ship OFF and turn on only if Lauren's own backtest shows they help.
1. **Weekly agreement.** No new entry if SPY opened the week below **both** its weekly 5 and 10 EMA (computed on completed weekly closes).
2. **Inside-week chop.** No new entry if this week opened inside last week's range right after an outside reversal week. **[v2] Defined:** last week's high > prior week's high, last week's low < prior week's low, it closed in the opposite direction from the week before it, and its range was ≥ 1.5× the 10-week average range.
3. **Event blackout.** No new entry on FOMC day or the day before. Keep dates in `config.yaml`. **[v2]** Also allow CPI dates (same list format), default empty.
4. **Rule of 16.** Expected daily move = VIX / 16 (%). Skip entries on a day SPY is already down more than 1 expected daily move from the prior close. Use it in alerts too.

### Entry
- Underlying: **XSP** (mini S&P, cash-settled, European, no assignment, Section 1256 tax treatment).
- Expiration: **30 to 45 days out**. Pick the one closest to 38.
- Expected move = XSP price × (VIX / 100) × sqrt(DTE / 365).
- Short put strike: first strike **below** price minus 1 expected move.
- Long put strike: below the short strike. Width = the widest spread where (width − credit) × 100 ≤ max risk.
- **[v2] Min credit: 10% of width** (was 20%). At 1 expected move, a $1-3 wide spread pays about 10-15% of width; at 20%, the simulation found **zero** qualifying trades in 36 years. Also require a **$0.25 minimum credit** so costs can't eat the whole trade. Both tunable. Log every rejected candidate with its credit, so Lauren can see how often the floor binds on real chains.
- Order: multi-leg limit at mid. If unfilled after 5 minutes, step 0.01 toward natural, up to 3 steps, then cancel and log. **[v2]** Re-check the min credit and the risk limit before each step. Never step past the floor.
- Entry window: once per day, 10:00 to 11:00 a.m. Central (the market opens 8:30 Central, so the first 30 minutes are already excluded).
- **[v2] Fill log:** for every fill, record mid, natural, and fill price at entry and exit. Report average slippage per spread weekly. If it averages above $0.02 per spread per side over 10+ fills, alert Lauren: the backtest says the edge is gone at that cost.

### Exits (checked every 15 minutes during market hours)
- **Take profit at 50% of credit.** **[v2]** Right after the entry fills, place a resting buy-to-close limit at 50% of the credit, so winners exit at your price instead of paying the spread. If Alpaca only accepts `day` time-in-force for options, re-place it at each open.
- **[v2] Stop: XSP trades below the short strike at a 15-minute check, or the spread mark reaches 3× the credit received, whichever comes first.** v1's stop at 2× credit was the worst stop tested: it fired on ordinary vol noise in about 1 trade in 5 and cut results at every cost level. The new stop still never holds a loser past a clear line and never adds to a loser, which was the point of v1's rule. Make `stop.type` (`strike_breach` | `credit_multiple`) and `stop.credit_multiple` config values, and backtest both.
- **[v2]** Use the underlying price for the strike-breach check, not option quotes. Option marks can spike on a wide quote. For the credit-multiple check, use the mid, and require it on two consecutive checks.
- **Time exit:** close any spread at 21 days left, no matter the P&L.
- If XSP is unavailable on Alpaca, fall back to SPY put spreads. **[v2]** SPY options are American, so a short put can be assigned early when it is deep in the money with little time value. (Ex-dividend risk applies to short calls, not puts.) The strike-breach stop and the 21-day exit make that rare; also close any spread whose short leg is in the money with 2 or fewer days left. SPY option spreads are usually much tighter than XSP. Since cost decides this strategy, compare fills on both during paper trading.

## 4. Phase 2 (build later, ship disabled)
- Weekly 5 EMA dip-buy calls when the trend is confirmed (monthly ON and weekly agree).
- Best entry: brief undercut of support, then reclaim (shakeout).
- Scale out: 3 take-profit zones in a trend; 50-80% off same day in chop.
- Options only, defined risk. Flag: `phase2.enabled: false`.

## 5. Phase 3 (build when Lauren uploads her trade log)
- `analyze_my_trades.py` reads `data/my_trades.csv` (entry/exit time, ticker, strike, expiry, call/put, entry/exit price, contracts, notes).
- FIFO round-trip P&L. Output: best setups, time of day, hold time, and leaks (holding losers, adding to losers).
- Findings become new toggles in `config.yaml`, tested before use.

## 6. Risk limits (do not raise without Lauren)

| Limit | Value |
|---|---|
| Max risk per trade | $300 (VIX under 20: $150) |
| Max open positions | 3 |
| Daily loss stop | $400: no new entries rest of day, push alert. **[v2]** Counts realized P&L plus the change in open-position marks today. |
| Drawdown kill switch | Account down 15% from start ($900): bot disables itself, flattens, alerts. Manual restart only. **[v2]** "Start" = $6,000 fixed, not a high-water mark. |
| Max spreads per expiration | 1 |

**[v2] Two questions for Lauren. Each would lower risk, so neither change is made without her:**
1. **All 3 positions are the same bet.** A crash hits all three at once: 3 × $300 = $900 = the kill switch. One bad day could trip it. Option: cap total open risk at $600.
2. **Flattening defined-risk spreads in a crash** sells at the widest quotes of the day. Option: on kill, stop new entries and let open spreads finish at their stops, time exits or expiry; flatten only by Lauren's command. Their max loss is already capped by the width.

## 7. Repo layout

```
bot/
  config.yaml        all rules and limits
  .env.example       ALPACA_KEY, ALPACA_SECRET, NTFY_TOPIC
  main.py            scheduler: entry job, exit job, daily summary
  regime.py          monthly 5 EMA, weekly filter, VIX grid
  data.py            Alpaca bars, FRED VIX, option chains
  strategy.py        strike, width, credit selection
  orders.py          multi-leg orders, fill stepping, resting take-profit, cancels
  risk.py            limits, daily loss stop, kill switch
  journal.py         SQLite log of every decision, order, fill and slippage
  alerts.py          ntfy.sh push to Lauren's phone
  backtest/
    run_backtest.py
  research/          v2 data check (regime_grid.py, spread_sim.py, FINDINGS.md)
  tests/
```

## 8. Backtest (before any paper trading)
- SPY daily bars from Alpaca history; VIX from FRED.
- Price spreads with Black-Scholes using VIX as the IV proxy, with a configurable put-skew bump. Note this understates skew, so real credits on puts run higher and real losses can too. Say so in the report.
- **[v2] Runs:** base switch only; base plus each filter in section 3 alone (4 runs); all filters together; both stop types; min credit 10% and 20%. Report how many candidate trades each rule rejected.
- **[v2] Cost sensitivity is required:** run every version at 0, 1, 2 and 3 cents slippage per spread per side, and report the breakeven cost. This number matters more than any filter.
- **[v2]** No lookahead: regime from the last completed month, VIX from the prior close, entries and exits at prices the bot would really have seen.
- **[v2]** Daily bars can't see intraday stops. Approximate them with the daily low, run both the close-only and the low-touch versions, and say which is which.
- Report in plain language: trades, win rate, average win, average loss, max drawdown, worst month, results by regime cell, breakeven slippage.
- Save the report to `reports/backtest_YYYY-MM-DD.md`.

## 9. Live-trading lock and go-live checklist
Live trading only runs when **all** are true:
1. `LIVE_TRADING=true` in `.env`
2. A file named `I_APPROVE_LIVE.txt` exists in the repo root, created by Lauren
3. `config.yaml` has `mode: live`

Before Lauren flips it:
- Backtest report reviewed
- At least 4 weeks of paper trading with 5+ closed trades
- Every stop and the kill switch fired at least once in tests
- Paper results reviewed against the backtest
- **[v2]** Measured average slippage below the backtest's breakeven cost. **Caveat:** paper fills are simulated and usually kinder than real ones. Treat paper slippage as a best case.

## 10. Alerts (short, phone-friendly)
Push via ntfy.sh. One line each:
- "Regime ON, VIX 22. Sold XSP 690/687 put spread, $0.71 credit, max risk $229."
- "Closed at 50% profit: +$35."
- "Stop hit (XSP below 690): -$71. Rule held."
- "No trade: regime OFF."
- "No trade: best credit $0.18 < $0.25 floor." **[v2]**
- "Slippage warning: avg $0.03/spread over last 10 fills." **[v2]**
- Daily 3:15 p.m. Central summary: open positions, P&L today, regime, VIX.

## 11. Build order
1. Repo, config, `.env.example`, journal, alerts. Send a test push.
2. `data.py` + `regime.py`. Print today's regime and why. **[v2]** Also check and report Alpaca's current support for XSP options, multi-leg orders and options time-in-force.
3. Backtest. Stop and show Lauren the report.
4. `strategy.py` + `orders.py` on paper. Dry run first (log orders, don't send).
5. `risk.py` with unit tests for every limit.
6. Scheduler, run on paper. Weekly summary every Friday, **[v2]** including fill slippage.
7. Phase 2 code, disabled.

## 12. Running it
- Start on Lauren's computer with a scheduler that runs on market days. **[v2]** Use Alpaca's market clock/calendar for holidays and early closes.
- Move to a small always-on cloud server once paper trading is stable.
- Timezone: America/Chicago.

Not financial advice. This is Lauren's own rule set turned into code; she owns every go-live decision.
