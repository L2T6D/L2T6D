"""Black-Litterman allocation, following the structure of the Case 3 notebook.

Kept from the notebook:
  * P = identity (one absolute view per stock), Omega = tau * P Sigma P^T
  * three separate analysts -> three BL runs -> each weight vector L2-normalised -> summed
  * market-cap weights for the equilibrium prior, risk aversion 2.4, tau 0.05

Changed, because the notebook's version was a bug or has no real-world equivalent:
  * The prior uses delta = RISK_AVERSION. The notebook's exp_ret() passed tau (0.05)
    as delta, shrinking the prior ~48x relative to what it intended.
  * Sigma comes from real daily log returns (the notebook used the analysts'
    synthetic price paths, which real analysts don't publish).
  * Views come from 12-month price targets: q_i = ln(target_i / price_i) / 252.
"""
import numpy as np
from . import config


def log_returns(prices):
    return np.log(prices / prices.shift(1)).dropna()


def market_weights(last_prices, shares):
    caps = last_prices.values * shares.values
    return caps / caps.sum()


def implied_returns(cov, w_mkt, delta=config.RISK_AVERSION):
    return delta * cov @ w_mkt


def posterior_returns(cov, pi, q, tau=config.TAU):
    n = len(pi)
    P = np.eye(n)
    omega = tau * P @ cov @ P.T
    inv_tau_cov = np.linalg.pinv(tau * cov)
    inv_omega = np.linalg.pinv(omega)
    A = inv_tau_cov + P.T @ inv_omega @ P
    b = inv_tau_cov @ pi + P.T @ inv_omega @ q
    return np.linalg.pinv(A) @ b


def optimal_weights(cov, mu, delta=config.RISK_AVERSION):
    return np.linalg.pinv(delta * cov) @ mu


def target_views(last_prices, targets, pi):
    """Daily expected log return implied by each target. No target -> fall back to the prior."""
    q = np.log(targets.values.astype(float) / last_prices.values) / config.TRADING_DAYS
    return np.where(np.isfinite(q), q, pi)


def raw_rule(prices, fund):
    """The notebook's rule on real data. Returns raw (unnormalised) weights plus diagnostics."""
    rets = log_returns(prices.tail(config.COV_LOOKBACK_DAYS + 1))
    cov = rets.cov().values
    last = prices.iloc[-1]
    w_mkt = market_weights(last, fund["shares"])
    pi = implied_returns(cov, w_mkt)
    total = np.zeros(len(last))
    mus = {}
    for col in ("target_low", "target_mean", "target_high"):
        q = target_views(last, fund[col], pi)
        mu = posterior_returns(cov, pi, q)
        w = optimal_weights(cov, mu)
        total += w / np.linalg.norm(w)
        mus[col] = mu
    mu_avg = np.mean(list(mus.values()), axis=0)
    return total, {"w_mkt": w_mkt, "pi": pi, "mu": mu_avg, "cov": cov}


def apply_limits(raw):
    """Turn raw weights into a tradeable book: gross 100%, capped longs/shorts, not net short."""
    w = np.asarray(raw, dtype=float)
    gross = np.abs(w).sum()
    w = w / gross if gross > 0 else np.full_like(w, 1 / len(w))
    for _ in range(50):
        w = np.clip(w, -config.MAX_SHORT_PER_NAME, config.MAX_LONG_PER_NAME)
        net = w.sum()
        if net < config.MIN_NET_EXPOSURE:
            # shrink shorts proportionally until the book is no longer net short
            shorts = w < 0
            need = config.MIN_NET_EXPOSURE - net
            short_total = -w[shorts].sum()
            if short_total > 0:
                w[shorts] *= max(0.0, 1 - need / short_total)
        g = np.abs(w).sum()
        w = w * (config.GROSS_EXPOSURE / g) if g > 0 else w
        if (w >= -config.MAX_SHORT_PER_NAME - 1e-9).all() and \
           (w <= config.MAX_LONG_PER_NAME + 1e-9).all() and w.sum() >= config.MIN_NET_EXPOSURE - 1e-9:
            break
    return w


def trailing_sharpe(weights, prices, days=config.GATE_LOOKBACK_DAYS):
    """Annualised Sharpe of holding `weights` (constant) over the last `days` sessions."""
    simple = prices.pct_change().dropna().tail(days)
    port = simple.values @ np.asarray(weights, dtype=float)
    sd = port.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(port.mean() / sd * np.sqrt(config.TRADING_DAYS))
