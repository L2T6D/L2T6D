"""Approximate backtest of Playbook v1 XSP put spreads, 1990-2026, on daily closes.

Approximations (all of them bias results; read the numbers as relative, not exact):
  * XSP = S&P 500 / 10, $1 strikes, one expiration available every calendar day.
  * Black-Scholes, r = 3%, no dividends. IV = VIX (flat), or VIX plus a put-skew bump.
  * Entries and exits at the daily close; the stop is only checked at closes, so real
    intraday stops fire more often and gaps can blow through them.
  * Regime uses the last COMPLETED month (no lookahead). VIX filter uses the prior close
    (FRED publishes VIXCLS a day late).
  * Slippage: $0.03 per spread on entry and on every exit.
"""
import argparse
import math
import sys

import numpy as np
import pandas as pd

N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
R, SLIP = 0.03, 0.03  # overridden by --slip


def put(S, K, T, vol):
    if T <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (R + 0.5 * vol * vol) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    return K * math.exp(-R * T) * N(-d2) - S * N(-d1)


def iv(S, K, vix, skew):
    # crude skew: +skew vol points (as a fraction of VIX) per 10% OTM
    return vix / 100 * (1 + skew * max(0.0, math.log(S / K)) / 0.10)


def spread_value(S, Ks, Kl, T, vix, skew):
    return put(S, Ks, T, iv(S, Ks, vix, skew)) - put(S, Kl, T, iv(S, Kl, vix, skew))


def load(path):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df["xsp"] = df["spx"] / 10
    m = df["spx"].resample("ME").last()
    on = (m > m.ewm(span=5, adjust=False).mean())
    # regime known on day d = value at the last month end strictly before d
    df["regime_on"] = on.shift(1).reindex(df.index, method="ffill").shift(0)
    df["regime_on"] = [bool(on[on.index < d].iloc[-1]) if (on.index < d).any() else False
                       for d in df.index]
    df["vix_prev"] = df["vix"].shift(1)
    w = df["spx"].resample("W-FRI").agg(["first", "last", "max", "min"])
    w_open = df["spx_open"].resample("W-FRI").first()
    e5 = w["last"].ewm(span=5, adjust=False).mean().shift(1)
    e10 = w["last"].ewm(span=10, adjust=False).mean().shift(1)
    week_ok = (w_open > e5) & (w_open > e10)
    df["week_ok"] = week_ok.reindex(df.index, method="bfill")
    df["day_ret"] = df["spx"] / df["spx"].shift(1) - 1
    return df.dropna(subset=["vix_prev"]).iloc[150:]


def run(df, stop_mult=2.0, tp=0.5, min_credit=0.20, skew=0.0, use_regime=True,
        trade_off_low=False, weekly=False, rule16=False, max_open=3, dte=38, exit_dte=21,
        risk_hi=300, risk_lo=150, half_size_low=True, em_mult=1.0, strike_stop=False):
    dates = df.index
    open_pos, trades = [], []
    for i, d in enumerate(dates):
        row = df.iloc[i]
        S, vix = row.xsp, row.vix
        # ---- exits at today's close
        still = []
        for p in open_pos:
            left = (p["exp"] - d).days
            val = spread_value(S, p["Ks"], p["Kl"], left / 365, vix, skew)
            reason = None
            if tp and val <= p["credit"] * (1 - tp):
                reason = "take profit"
            elif strike_stop and S < p["Ks"]:
                reason = "stop"
            elif stop_mult and val >= p["credit"] * stop_mult:
                reason = "stop"
            elif left <= exit_dte:
                reason = "time"
            if reason:
                pnl = (p["credit"] - val - 2 * SLIP) * 100 * p["n"]
                trades.append({**p, "exit": d, "reason": reason, "pnl": pnl})
            else:
                still.append(p)
        open_pos = still
        # ---- entry (once per day)
        vixp = row.vix_prev
        on, hi = row.regime_on, vixp >= 20
        if use_regime and not on:
            continue
        if not use_regime and not on and hi:
            pass
        if weekly and not row.week_ok:
            continue
        if rule16 and row.day_ret < -(vixp / 16) / 100:
            continue
        if len(open_pos) >= max_open:
            continue
        exp = d + pd.Timedelta(days=dte)
        if any(p["exp"] == exp for p in open_pos):
            continue
        T = dte / 365
        em = em_mult * S * vix / 100 * math.sqrt(T)
        Ks = math.floor(S - em)
        if Ks >= S - em:
            Ks -= 1
        max_risk = risk_hi if hi else (risk_lo if half_size_low else risk_hi)
        best = None
        for width in range(1, 40):
            c = spread_value(S, Ks, Ks - width, T, vix, skew)
            if (width - c) * 100 <= max_risk:
                best = (width, c)
            else:
                break
        if not best:
            continue
        width, c = best
        if c - SLIP < min_credit * width:
            trades.append({"entry": d, "skipped": True})
            continue
        open_pos.append({"entry": d, "exp": exp, "Ks": Ks, "Kl": Ks - width, "width": width,
                         "credit": c - SLIP, "n": 1, "vix_cell": "20+" if hi else "<20",
                         "skipped": False})
    t = pd.DataFrame(trades)
    skipped = int(t["skipped"].sum()) if len(t) else 0
    t = t[~t["skipped"]] if len(t) else t
    return t, skipped


def summarize(name, t, skipped):
    if t.empty:
        return {"variant": name, "trades": 0, "skipped (min credit)": skipped}
    eq = 6000 + t.sort_values("exit")["pnl"].cumsum()
    dd = (eq - eq.cummax()).min()
    yrs = (t["exit"].max() - t["entry"].min()).days / 365.25
    wins, losses = t[t.pnl > 0], t[t.pnl <= 0]
    by_month = t.groupby(t["exit"].dt.to_period("M"))["pnl"].sum()
    return {"variant": name, "trades": len(t), "skipped (min credit)": skipped,
            "win rate": f"{len(wins)/len(t):.0%}", "avg win": f"{wins.pnl.mean():.0f}",
            "avg loss": f"{losses.pnl.mean():.0f}", "total P&L": f"{t.pnl.sum():,.0f}",
            "P&L/yr": f"{t.pnl.sum()/yrs:,.0f}", "max DD": f"{dd:,.0f}",
            "worst month": f"{by_month.min():,.0f}",
            "stops": int((t.reason == "stop").sum())}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="spx_vix_daily.csv")
    ap.add_argument("--skew", type=float, default=0.0)
    ap.add_argument("--slip", type=float, default=0.03)
    a = ap.parse_args()
    SLIP = a.slip
    df = load(a.data)
    variants = {
        "spec as written": {},
        "spec, no min credit": {"min_credit": 0},
        "spec, min credit 10%": {"min_credit": 0.10},
        "stop 3x credit, min 10%": {"stop_mult": 3.0, "min_credit": 0.10},
        "no stop (time+TP only), min 10%": {"stop_mult": 0, "min_credit": 0.10},
        "no regime switch, min 10%": {"use_regime": False, "min_credit": 0.10},
        "+ weekly agreement, min 10%": {"weekly": True, "min_credit": 0.10},
        "+ rule of 16, min 10%": {"rule16": True, "min_credit": 0.10},
        "stop on close below short strike, min 10%": {"stop_mult": 0, "strike_stop": True, "min_credit": 0.10},
        "short strike 0.75 EM, stop 3x, min 10%": {"em_mult": 0.75, "stop_mult": 3.0, "min_credit": 0.10},
        "short strike 0.75 EM, strike stop, min 10%": {"em_mult": 0.75, "stop_mult": 0, "strike_stop": True, "min_credit": 0.10},
    }
    rows = []
    for name, kw in variants.items():
        t, s = run(df, skew=a.skew, **kw)
        rows.append(summarize(name, t, s))
        if name == "spec, min credit 10%":
            cells = t.groupby("vix_cell")["pnl"].agg(["count", "mean", "sum"]).round(0)
    print(f"skew={a.skew} slip={SLIP}  {df.index[0].date()} to {df.index[-1].date()}")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nBy VIX cell (spec rules, min credit 10%):\n", cells.to_string())
