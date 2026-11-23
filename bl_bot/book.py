"""Simulated paper book: fractional shares, shorts allowed, filled at the day's close."""
import csv
import json
from datetime import date

import numpy as np

from . import config


def load():
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return None


def save(state):
    config.STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def new_book(asof, spy_close):
    return {"cash": config.STARTING_CASH, "shares": {t: 0.0 for t in config.TICKERS},
            "inception": str(asof), "spy_at_inception": spy_close,
            "last_rebalance": None, "rebalances": 0}


def equity(state, last_prices):
    return state["cash"] + sum(state["shares"].get(t, 0.0) * float(last_prices[t])
                               for t in config.TICKERS)


def current_weights(state, last_prices):
    eq = equity(state, last_prices)
    return np.array([state["shares"].get(t, 0.0) * float(last_prices[t]) / eq
                     for t in config.TICKERS])


def rebalance(state, target_w, last_prices, asof):
    """Trade to target weights at the close. Returns the list of fills."""
    eq = equity(state, last_prices)
    cur = current_weights(state, last_prices)
    fills = []
    for i, t in enumerate(config.TICKERS):
        if abs(target_w[i] - cur[i]) < config.MIN_TRADE_WEIGHT:
            continue
        px = float(last_prices[t])
        new_sh = target_w[i] * eq / px
        delta = new_sh - state["shares"].get(t, 0.0)
        state["cash"] -= delta * px
        state["shares"][t] = new_sh
        fills.append({"date": str(asof), "ticker": t, "shares": round(delta, 6),
                      "price": round(px, 4), "notional": round(delta * px, 2)})
    if fills:
        state["last_rebalance"] = str(asof)
        state["rebalances"] += 1
        append_csv("fills.csv", fills)
    return fills


def append_csv(name, rows):
    if not rows:
        return
    path = config.LOG_DIR / name
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)


def upsert_daily_mark(asof, eq, spy_close, state):
    """One row per session in book_history.csv (rerunning a day overwrites it)."""
    path = config.LOG_DIR / "book_history.csv"
    rows = []
    if path.exists():
        with path.open() as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != str(asof)]
    rows.append({
        "date": str(asof), "equity": round(eq, 2), "spy_close": round(spy_close, 4),
        "book_return_since_inception": round(eq / config.STARTING_CASH - 1, 6),
        "spy_return_since_inception": round(spy_close / state["spy_at_inception"] - 1, 6),
    })
    rows.sort(key=lambda r: r["date"])
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
