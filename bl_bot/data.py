"""Market data from Yahoo Finance via yfinance."""
import numpy as np
import pandas as pd
import yfinance as yf


def price_history(tickers, days):
    """Daily closes (split/dividend adjusted), oldest first, one column per ticker."""
    period = f"{int(days * 1.6) + 30}d"  # calendar days, enough to cover `days` sessions
    df = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                     progress=False, threads=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    df = df[tickers].dropna(how="all").ffill()
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise RuntimeError(f"Missing price history for {missing}")
    return df.tail(days + 1)


def fundamentals(tickers):
    """Shares outstanding plus analyst low/mean/high 12-month price targets."""
    rows = []
    for t in tickers:
        tk = yf.Ticker(t)
        info = tk.info or {}
        try:
            pt = tk.analyst_price_targets or {}
        except Exception:
            pt = {}
        rows.append({
            "ticker": t,
            "shares": info.get("sharesOutstanding") or info.get("impliedSharesOutstanding"),
            "target_low": pt.get("low", info.get("targetLowPrice")),
            "target_mean": pt.get("mean", info.get("targetMeanPrice")),
            "target_high": pt.get("high", info.get("targetHighPrice")),
            "n_analysts": info.get("numberOfAnalystOpinions"),
        })
    df = pd.DataFrame(rows).set_index("ticker")
    if df["shares"].isna().any():
        raise RuntimeError(f"No shares outstanding for {df.index[df['shares'].isna()].tolist()}")
    return df.astype({"shares": float})


def last_session_date(prices):
    return pd.Timestamp(prices.index[-1]).date()
