"""Statistical validation.

The question is not "is the backtest Sharpe > 0" but "is it distinguishable
from luck, after accounting for fat tails, autocorrelation, multiple
testing, and the machinery's ability to manufacture performance out of
nothing". Tools:

- Stationary block bootstrap (Politis & Romano 1994) for Sharpe confidence
  intervals that respect serial dependence and volatility clustering.
- Probabilistic / Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014):
  non-normality-adjusted significance, deflated by the number of strategy
  variants evaluated while building this repo.
- Placebo test: random circular time-shifts of each instrument's forecast,
  run through the *identical* sizing/cost engine, give the distribution of
  Sharpe a signal with this structure but no information would produce.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

TRADING_DAYS = 256


# ---------------------------------------------------------------------------
# Descriptive


def sharpe(returns: pd.Series, days: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    if len(r) < 2 or r.std() == 0:
        return np.nan
    return float(r.mean() / r.std() * np.sqrt(days))


def summary(returns: pd.Series, days: int = TRADING_DAYS) -> dict:
    r = returns.dropna()
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    ann_ret = r.mean() * days
    ann_vol = r.std() * np.sqrt(days)
    downside = r[r < 0].std() * np.sqrt(days)
    monthly = r.resample("ME").sum()
    return {
        "start": str(r.index.min().date()),
        "end": str(r.index.max().date()),
        "years": round((r.index.max() - r.index.min()).days / 365.25, 1),
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe(r, days),
        "sortino": ann_ret / downside if downside > 0 else np.nan,
        "max_drawdown": float(dd.min()),
        "calmar": ann_ret / abs(dd.min()) if dd.min() < 0 else np.nan,
        "skew_daily": float(sps.skew(r)),
        "skew_monthly": float(sps.skew(monthly.dropna())),
        "worst_day": float(r.min()),
        "worst_month": float(monthly.min()),
        "pct_positive_months": float((monthly > 0).mean()),
    }


# ---------------------------------------------------------------------------
# Stationary block bootstrap


def stationary_bootstrap_sharpe(returns: pd.Series, n_boot: int = 10_000,
                                mean_block: float = 20.0, seed: int = 7,
                                days: int = TRADING_DAYS) -> dict:
    """Bootstrap distribution of the Sharpe ratio under resampling that
    preserves blocks of serial dependence (expected block length
    `mean_block` days)."""
    r = returns.dropna().to_numpy()
    n = len(r)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block

    idx = np.empty((n_boot, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, n_boot)
    restart = rng.random((n_boot, n)) < p
    fresh = rng.integers(0, n, (n_boot, n))
    for t in range(1, n):
        cont = (idx[:, t - 1] + 1) % n
        idx[:, t] = np.where(restart[:, t], fresh[:, t], cont)

    samples = r[idx]
    means = samples.mean(axis=1)
    stds = samples.std(axis=1, ddof=1)
    srs = means / stds * np.sqrt(days)
    point = sharpe(returns, days)
    return {
        "sharpe": point,
        "ci_2.5": float(np.percentile(srs, 2.5)),
        "ci_97.5": float(np.percentile(srs, 97.5)),
        "p_value_sr_le_0": float((srs <= 0).mean()),
        "n_boot": n_boot,
        "mean_block": mean_block,
    }


# ---------------------------------------------------------------------------
# PSR / DSR (Bailey & Lopez de Prado 2014)


def probabilistic_sharpe(returns: pd.Series, sr_benchmark_daily: float = 0.0) -> float:
    """P(true SR > benchmark), adjusted for skew/kurtosis. Daily units."""
    r = returns.dropna()
    t = len(r)
    sr = r.mean() / r.std()  # daily SR
    g3 = sps.skew(r)
    g4 = sps.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    z = (sr - sr_benchmark_daily) * np.sqrt(t - 1) / denom
    return float(sps.norm.cdf(z))


def deflated_sharpe(returns: pd.Series, n_trials: int,
                    var_trial_sr_daily: float) -> dict:
    """DSR: PSR against the expected maximum daily SR of `n_trials`
    zero-skill strategies whose SR variance matches the observed dispersion
    across the variants actually evaluated."""
    gamma = 0.5772156649
    e = np.e
    sr_star = np.sqrt(max(var_trial_sr_daily, 1e-12)) * (
        (1 - gamma) * sps.norm.ppf(1 - 1.0 / n_trials)
        + gamma * sps.norm.ppf(1 - 1.0 / (n_trials * e))
    )
    r = returns.dropna()
    return {
        "n_trials": n_trials,
        "sr_star_daily": float(sr_star),
        "sr_star_annual": float(sr_star * np.sqrt(TRADING_DAYS)),
        "dsr": probabilistic_sharpe(returns, sr_star),
    }


# ---------------------------------------------------------------------------
# Placebo: circularly shifted forecasts


def circular_shift_forecast(forecast: pd.DataFrame, rng: np.random.Generator,
                            min_shift: int = 260) -> pd.DataFrame:
    """Shift each instrument's forecast by an independent random offset
    (>= ~1 year, wrapping within its own live window). Keeps each forecast's
    autocorrelation, scale and the engine's cost/sizing behaviour; destroys
    any alignment with subsequent returns."""
    out = {}
    for col in forecast.columns:
        s = forecast[col]
        live = s.dropna()
        if len(live) < 2 * min_shift:
            out[col] = s
            continue
        k = int(rng.integers(min_shift, len(live) - min_shift))
        shifted = pd.Series(np.roll(live.to_numpy(), k), index=live.index)
        out[col] = shifted.reindex(s.index)
    return pd.DataFrame(out)


def placebo_test(run_fn, forecast: pd.DataFrame, n_reps: int = 200,
                 seed: int = 11) -> dict:
    """`run_fn(forecast) -> net returns Series`. Returns the null Sharpe
    distribution and the one-sided p-value of the real Sharpe."""
    rng = np.random.default_rng(seed)
    real = sharpe(run_fn(forecast))
    null = []
    for _ in range(n_reps):
        shifted = circular_shift_forecast(forecast, rng)
        null.append(sharpe(run_fn(shifted)))
    null_arr = np.array(null)
    return {
        "real_sharpe": real,
        "null_mean": float(np.nanmean(null_arr)),
        "null_std": float(np.nanstd(null_arr)),
        "null_p95": float(np.nanpercentile(null_arr, 95)),
        "null_max": float(np.nanmax(null_arr)),
        "p_value": float((null_arr >= real).mean()),
        "n_reps": n_reps,
        "null_sharpes": null,
    }
