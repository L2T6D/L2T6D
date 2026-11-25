# Playbook v1 review: what the data says

Data: S&P 500 and VIX daily closes from Yahoo Finance, 1990-01-02 to 2026-11-24.
Scripts: `regime_grid.py` (regime table), `spread_sim.py` (spread simulation).
Rerun: `python3 fetch_data.py`, then `python3 regime_grid.py spx_vix_daily.csv` and `python3 spread_sim.py spx_vix_daily.csv --skew 0.15 --slip 0.02`.

## 1. The regime-grid statistic in v1 cannot be right as stated

v1 says S&P 1950-2026 with VIX 20+. VIX starts in 1990, so 1950-1989 must have used a proxy.
On real VIX (1990-06 to 2026-10, 437 completed months; signal at month end, outcome next month):

| Regime | VIX | Months | Next month < -5% | Any close < -5% during next month | Avg next month | Worst next month |
|---|---|---|---|---|---|---|
| ON | 20+ | 79 | **10.1%** (v1 says 1.2%) | 17.7% | +1.17% | -14.6% |
| ON | <20 | 247 | 4.5% | 8.5% | +0.62% | -8.6% |
| OFF | 20+ | 82 | 24.4% (v1 says 15.7%) | 36.6% | +0.90% | -16.9% |
| OFF | <20 | 29 | 10.3% | 10.3% | +0.72% | -9.2% |

- The switch is real: OFF + VIX 20+ is the most dangerous cell, as v1 says.
- ON + VIX 20+ is **not** the safest cell for the market. ON + VIX under 20 is.
- ON + VIX 20+ is still the best cell **per trade** in the spread simulation, because premium is
  richer and the 1-expected-move strike sits further away. So keep full size there, for that reason.

## 2. Spread simulation (approximate)

Rules as in v1 (38 DTE, short strike just below 1 expected move, width sized to the $300/$150 risk
limit, 50% take profit, 21-DTE time exit, max 3 open, 1 per expiration). Black-Scholes with
IV = VIX plus a mild put skew, exits at daily closes, $6,000 start, 1 spread per trade.
"Slip" = cost per spread on entry and on every exit, versus mid.

| Variant | P&L/yr at 0 slip | max DD at 0 slip | P&L/yr at 2 cents slip | max DD at 2 cents slip |
|---|---|---|---|---|
| **v1 exactly as written (min credit 20%)** | **0 trades in 36 years** | | **0 trades** | |
| v1, min credit 10% (2x-credit stop) | +$186 | -$470 | -$171 | -$5,412 |
| stop at 3x credit | +$209 | -$505 | -$93 | -$3,281 |
| stop when price closes below short strike | +$210 | -$542 | -$80 | -$2,970 |
| no stop (TP + time exit only) | +$229 | -$552 | -$54 | -$2,254 |
| no regime switch | +$273 | -$856 | -$233 | -$7,324 |
| + weekly agreement filter | +$105 | -$648 | -$161 | -$5,217 |
| + rule-of-16 filter | +$168 | -$572 | -$176 | -$5,521 |

Breakeven cost is about **1 cent per spread per side**. At 1 cent, the 3x and strike stops earn
about +$50/yr and v1's 2x stop is flat.

What this means:
1. **The 20% minimum credit makes v1 never trade.** A 1-expected-move, $1-3 wide XSP spread
   pays about 10-15% of its width. Use 10% (or a fixed dollar floor) and verify on real chains.
2. **Execution cost decides the strategy.** One $3-wide XSP spread takes in about $40. The edge is
   a few dollars per trade, and 2-3 cents of slippage per spread erases it. Entry at mid,
   resting take-profit orders, and fewer forced exits matter more than any filter.
3. **The 2x-credit stop is the worst stop tested** at every cost level. It fires on ordinary vol
   noise (about 1 trade in 5). The strike-breach stop and the 3x stop both do better.
4. **The weekly-agreement and rule-of-16 filters lowered results.** Ship them as toggles, default OFF.
5. **Even with perfect fills, the expected return is about 3-4% a year on $6,000.** That is about
   what cash earns. Real put skew is steeper than this model, so real credits may be higher; real
   intraday stops and gaps are worse. Paper trading has to settle it.

Caveats: daily closes only (intraday stops fire more often in reality), Black-Scholes with a crude
skew, VIX as the vol input, one expiration every day, no early-close or holiday handling, no FOMC
blackout test (no date list in the data). Use this to rank rule choices, not to forecast dollars.
