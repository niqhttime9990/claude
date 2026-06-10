"""Statistical machinery: interval estimates that respect the data's
correlation structure. Trades on the same event are not independent, so all
mean-return inference uses a cluster bootstrap at the event level."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps


def event_clusters(df: pd.DataFrame) -> np.ndarray:
    """Cluster key for inference: the event when known, else the market —
    sibling outcomes of one election/championship are one draw, not fifty."""
    return df["event_id"].fillna("mkt:" + df["market_id"].astype(str)).to_numpy()


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def cluster_bootstrap_mean(
    values: np.ndarray,
    clusters: np.ndarray,
    n_boot: int = 5000,
    seed: int = 7,
    alpha: float = 0.05,
) -> dict:
    """Bootstrap CI for the mean, resampling whole clusters (events).

    Returns mean, CI bounds, and the bootstrap p-value for mean <= 0
    (one-sided, the relevant test for 'is there an edge').
    """
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    if len(values) == 0:
        return {"mean": np.nan, "lo": np.nan, "hi": np.nan, "p_value_le0": np.nan,
                "n": 0, "n_clusters": 0}
    uniq = pd.unique(clusters)
    idx_by_cluster = {c: np.flatnonzero(clusters == c) for c in uniq}
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        picks = rng.choice(len(uniq), size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_cluster[uniq[i]] for i in picks])
        boots[b] = values[idx].mean()
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return {
        "mean": float(values.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "p_value_le0": float((boots <= 0).mean()),
        "n": int(len(values)),
        "n_clusters": int(len(uniq)),
        "boot_std": float(boots.std()),
    }


def weekly_performance(pnl: pd.Series) -> dict:
    """Sharpe-style summary from a timestamp-indexed P&L series (USD per $1
    stakes). Aggregates to ISO weeks; annualizes by sqrt(52)."""
    if pnl.empty:
        return {"weekly_mean": np.nan, "weekly_std": np.nan, "sharpe_ann": np.nan,
                "n_weeks": 0, "t_stat": np.nan}
    wk = pnl.groupby(pd.Grouper(freq="W")).sum()
    wk = wk[wk != 0.0]
    if len(wk) < 4:
        return {"weekly_mean": float(wk.mean()) if len(wk) else np.nan,
                "weekly_std": float(wk.std()) if len(wk) > 1 else np.nan,
                "sharpe_ann": np.nan, "n_weeks": int(len(wk)), "t_stat": np.nan}
    mean, std = wk.mean(), wk.std(ddof=1)
    sharpe = mean / std * np.sqrt(52) if std > 0 else np.nan
    t_stat = mean / (std / np.sqrt(len(wk))) if std > 0 else np.nan
    return {"weekly_mean": float(mean), "weekly_std": float(std),
            "sharpe_ann": float(sharpe), "n_weeks": int(len(wk)),
            "t_stat": float(t_stat)}


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def deflated_p_note(n_cells_tested: int, best_p: float) -> dict:
    """Bonferroni-style honesty check for grid searches: the probability of
    seeing at least one p-value this small across all tested cells."""
    fam = 1 - (1 - best_p) ** n_cells_tested if best_p == best_p else np.nan
    return {"n_cells": n_cells_tested, "raw_p": best_p,
            "family_wise_p_bonferroni": float(min(1.0, best_p * n_cells_tested)),
            "family_wise_p_independent_approx": float(fam)}


def binomial_calibration_test(
    prices: np.ndarray, outcomes: np.ndarray, clusters: np.ndarray | None = None
) -> dict:
    """Regression test for favorite-longshot bias: outcome - p ~ a + b*(p-0.5).

    b < 0 means favorites underpriced / longshots overpriced (classic FLB:
    extremes too moderate); b > 0 the reverse. Cluster-robust (CR1) errors
    when clusters are given — sibling outcomes of one event are not
    independent observations; HC1 otherwise."""
    x = prices - 0.5
    y = outcomes - prices
    n = len(x)
    if n < 50:
        return {"intercept": np.nan, "slope": np.nan, "t": np.nan, "p": np.nan,
                "n": n, "n_clusters": 0}
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    if clusters is not None:
        uniq = pd.unique(clusters)
        G = len(uniq)
        meat = np.zeros((2, 2))
        for c in uniq:
            sel = clusters == c
            s = X[sel].T @ resid[sel]
            meat += np.outer(s, s)
        meat *= (G / max(G - 1, 1)) * ((n - 1) / max(n - 2, 1))
        dof = max(G - 1, 1)
    else:
        meat = (X * (resid**2)[:, None]).T @ X * (n / (n - 2))
        dof = n - 2
    cov = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.diag(cov))
    t = beta[1] / se[1]
    p = 2 * (1 - sps.t.cdf(abs(t), df=dof))
    return {"intercept": float(beta[0]), "slope": float(beta[1]),
            "t": float(t), "p": float(p), "n": n,
            "n_clusters": int(len(pd.unique(clusters))) if clusters is not None else n}
