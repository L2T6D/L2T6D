"""Download S&P 500 and VIX daily history from Yahoo Finance into spx_vix_daily.csv."""
import pandas as pd
import yfinance as yf

d = yf.download(["^GSPC", "^VIX"], start="1989-01-01", auto_adjust=False, progress=False)
pd.DataFrame({"spx_open": d["Open"]["^GSPC"], "spx_high": d["High"]["^GSPC"],
              "spx_low": d["Low"]["^GSPC"], "spx": d["Close"]["^GSPC"],
              "vix": d["Close"]["^VIX"]}).dropna().to_csv("spx_vix_daily.csv")
