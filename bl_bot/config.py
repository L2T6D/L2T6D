"""All tunable settings in one place. Edit these, not the code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
STATE_FILE = LOG_DIR / "book_state.json"
PENDING_FILE = LOG_DIR / "pending_decision.json"

# Nine liquid US large caps across sectors. Swap freely; any count works.
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "JNJ", "PG", "CAT"]
BENCHMARK = "SPY"

# Black-Litterman settings, same values as the original notebook.
TAU = 0.05           # uncertainty scaling on the prior
RISK_AVERSION = 2.4  # "rap" in the notebook (they tuned 2.15-2.65)
TRADING_DAYS = 252
COV_LOOKBACK_DAYS = 252   # one year of daily returns for the covariance matrix

# Sharpe gate: a candidate replaces the book only if its trailing Sharpe is higher.
GATE_LOOKBACK_DAYS = 63   # about one quarter

# Position limits applied after the raw rule (the raw rule can ask for ~89% net short).
MAX_SHORT_PER_NAME = 0.10   # no single short bigger than 10% of equity
MAX_LONG_PER_NAME = 0.35    # no single long bigger than 35% of equity
MIN_NET_EXPOSURE = 0.0      # book is never net short overall
GROSS_EXPOSURE = 1.0        # sum of |weights| = 100% of equity (no leverage)

# Paper book
STARTING_CASH = 100_000.0
MIN_TRADE_WEIGHT = 0.005    # skip trades smaller than 0.5% of equity

# Claude decision step (only used with --decider api)
CLAUDE_MODEL = "claude-fable-5-2"
CLAUDE_EFFORT = "high"
