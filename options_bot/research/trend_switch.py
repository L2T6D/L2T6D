"""Use the Playbook monthly-5-EMA switch to hold the index (or 2x index) vs T-bills.

1990-2026, S&P 500 price index (no dividends, so all equity variants are understated ~2%/yr),
T-bills from ^IRX. 2x = daily-rebalanced like SSO, minus 0.9%/yr fee and T-bill borrow cost.
Signal = last completed month's close vs its monthly 5 EMA; trade on the next session.
Switching cost: 0.05% per change in exposure."""
import sys
import numpy as np
import pandas as pd
import yfinance as yf

px = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "spx_vix_daily.csv",
                 index_col=0, parse_dates=True)
irx = yf.download("^IRX", start="1989-01-01", progress=False)["Close"].squeeze()
df = px[["spx", "vix"]].join(irx.rename("irx")).ffill().dropna()
df["r"] = df.spx.pct_change()
df["cash"] = df.irx / 100 / 252
m = df.spx.resample("ME").last()
on = m > m.ewm(span=5, adjust=False).mean()
df["on"] = [bool(on[on.index < d].iloc[-1]) if (on.index < d).any() else False for d in df.index]
mv = df.vix.resample("ME").last()
df["vix_lo"] = [bool(mv[mv.index < d].iloc[-1] < 20) if (mv.index < d).any() else False for d in df.index]
df = df.iloc[130:].dropna()

def lev(L):  # daily return of an L-times fund, fee and borrow included
    return L * df.r - (L - 1) * df.cash - (0.009 / 252 if L > 1 else 0)

def run(expo):  # expo: Series of exposure 0/1/2 per day (decided before the day)
    ret = pd.Series(0.0, index=df.index)
    for L in sorted(set(expo)):
        mask = expo == L
        ret[mask] = df.cash[mask] if L == 0 else lev(L)[mask]
    ret -= expo.diff().abs().fillna(0) * 0.0005
    eq = (1 + ret).cumprod()
    yrs = len(ret) / 252
    mo = (1 + ret).resample("ME").prod() - 1
    return {"CAGR": f"{eq.iloc[-1]**(1/yrs)-1:.1%}", "max DD": f"{(eq/eq.cummax()-1).min():.0%}",
            "months up": f"{(mo > 0).mean():.0%}", "worst month": f"{mo.min():.0%}",
            "$5k ->": f"${5000*eq.iloc[-1]:,.0f}",
            "switches/yr": f"{(expo.diff().abs() > 0).sum()/yrs:.1f}"}

one = pd.Series(1.0, index=df.index)
sw = df.on.astype(float)
rows = {
    "buy & hold 1x": run(one),
    "buy & hold 2x": run(one * 2),
    "switch: 1x when ON, T-bills when OFF": run(sw),
    "switch: 2x when ON, T-bills when OFF": run(sw * 2),
    "switch: 2x ON+VIX<20, 1x ON+VIX20+, else T-bills": run(sw * np.where(df.vix_lo, 2, 1)),
}
print(f"{df.index[0].date()} to {df.index[-1].date()}")
print(pd.DataFrame(rows).T.to_string())
