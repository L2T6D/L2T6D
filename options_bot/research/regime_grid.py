"""Recompute the Playbook v1 regime grid on 1990-2026 data (VIX only exists from 1990).

Signal at each month end uses that month's close and that day's VIX close.
Outcome is the NEXT month's S&P 500 return (close to close)."""
import sys
import pandas as pd

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "spx_vix_daily.csv",
                 index_col=0, parse_dates=True)
m = df[["spx", "vix"]].resample("ME").last()
m["ema5"] = m["spx"].ewm(span=5, adjust=False).mean()
m["on"] = m["spx"] > m["ema5"]
m["vix20"] = m["vix"] >= 20
m["next_ret"] = m["spx"].shift(-1) / m["spx"] - 1
# worst intra-month drawdown from this month-end close, using daily closes next month
daily = df["spx"]
m["next_min"] = [daily[(daily.index > a) & (daily.index <= b)].min() / m.loc[a, "spx"] - 1
                 if b in m.index else float("nan")
                 for a, b in zip(m.index, m.index[1:].append(pd.Index([pd.NaT])))]
m = m.iloc[5:-1]  # drop EMA warm-up and the unfinished month

rows = []
for (on, v20), g in m.groupby(["on", "vix20"]):
    rows.append({
        "regime": "ON" if on else "OFF", "VIX": "20+" if v20 else "<20", "months": len(g),
        "next month < -5%": f"{(g.next_ret < -0.05).mean():.1%}",
        "next month any close < -5% from entry": f"{(g.next_min < -0.05).mean():.1%}",
        "avg next month": f"{g.next_ret.mean():+.2%}",
        "worst next month": f"{g.next_ret.min():+.1%}",
    })
print(f"{m.index[0]:%Y-%m} to {m.index[-1]:%Y-%m}, {len(m)} months")
print(pd.DataFrame(rows).to_string(index=False))
