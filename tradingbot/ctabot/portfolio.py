"""Position sizing: volatility targeting with risk parity across asset
classes, an estimated (lookahead-safe) instrument diversification
multiplier, and position buffering to control turnover.

Positions are expressed as notional exposure as a fraction of capital
(futures are unfunded, so exposure can exceed 1x; the 20% vol target keeps
typical gross around 2-4x, normal for a CTA).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyConfig


def class_risk_weights(active: pd.DataFrame, class_of: dict[str, str]) -> pd.DataFrame:
    """Equal risk weight per asset class, equal split within a class,
    renormalised daily over instruments that are active (have a forecast)."""
    weights = pd.DataFrame(0.0, index=active.index, columns=active.columns)
    groups: dict[str, list[str]] = {}
    for inst in active.columns:
        groups.setdefault(class_of[inst], []).append(inst)
    classes = list(groups.values())
    n_active_classes = pd.Series(0, index=active.index, dtype=float)
    for members in classes:
        n_active_classes += active[members].any(axis=1).astype(float)
    for members in classes:
        n_in_class = active[members].sum(axis=1)
        class_w = (1.0 / n_active_classes).replace(np.inf, np.nan)
        per_inst = class_w / n_in_class.replace(0, np.nan)
        weights[members] = active[members].mul(per_inst, axis=0).fillna(0.0)
    return weights


def idm_series(returns: pd.DataFrame, vols: pd.DataFrame, weights: pd.DataFrame,
               cfg: StrategyConfig) -> pd.Series:
    """Instrument diversification multiplier 1/sqrt(w' C w), estimated on
    trailing unit-vol returns, refreshed yearly, using only past data.
    Negative correlations are floored at zero (Carver), capping the benefit
    claimed from historically negative stock/bond correlation."""
    unit = (returns / vols.shift(1)).clip(-5, 5)  # standardised, outlier-trimmed
    idx = returns.index
    out = pd.Series(1.0, index=idx)
    step = cfg.trading_days_per_year
    current = 1.0
    for start in range(cfg.idm_min_periods, len(idx), step):
        window = unit.iloc[max(0, start - cfg.idm_window):start]
        w = weights.iloc[start - 1]
        live = window.columns[(window.notna().sum() > 60) & (w > 0)]
        if len(live) >= 2:
            corr = window[live].corr().clip(lower=0.0).fillna(0.0).to_numpy(copy=True)
            np.fill_diagonal(corr, 1.0)
            wv = w[live].to_numpy()
            wv = wv / wv.sum()
            variance = float(wv @ corr @ wv)
            current = min(cfg.idm_cap, max(1.0, 1.0 / np.sqrt(variance)))
        out.iloc[start:start + step] = current
    return out


def target_positions(forecast: pd.DataFrame, ann_vol: pd.DataFrame,
                     returns: pd.DataFrame, class_of: dict[str, str],
                     cfg: StrategyConfig,
                     ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Notional positions (fraction of capital), the average-position scale
    used for buffering, and the IDM series applied."""
    # An instrument stays "active" through short data gaps (its own holidays)
    # so class weights don't jump on calendar mismatches and force churn.
    active = (forecast.notna() & ann_vol.notna()).rolling(10, min_periods=1).max().astype(bool)
    weights = class_risk_weights(active, class_of)
    idm = idm_series(returns, ann_vol, weights, cfg)
    avg_scale = (cfg.vol_target_annual * weights).div(ann_vol, axis=0).mul(idm, axis=0)
    pos = (forecast / 10.0) * avg_scale
    return pos, avg_scale, idm


def buffered_positions(target: pd.DataFrame, avg_scale: pd.DataFrame,
                       buffer_frac: float, hold_gap_limit: int = 10) -> pd.DataFrame:
    """Trade only when the target leaves a +/- buffer band around the held
    position; then trade to the nearest band edge. Cuts turnover sharply at
    negligible cost to gross performance.

    A NaN target (instrument holiday / data gap) holds the existing position
    rather than trading to zero; gaps longer than `hold_gap_limit` days are
    treated as a real exit."""
    tgt = target.ffill(limit=hold_gap_limit).to_numpy()
    buf = (avg_scale.abs().ffill(limit=hold_gap_limit).to_numpy()) * buffer_frac
    held = np.zeros_like(tgt)
    prev = np.zeros(tgt.shape[1])
    for t in range(tgt.shape[0]):
        live = ~np.isnan(tgt[t])
        lo = tgt[t, live] - buf[t, live]
        hi = tgt[t, live] + buf[t, live]
        prev[live] = np.clip(prev[live], lo, hi)
        prev[~live] = 0.0
        held[t] = prev
    return pd.DataFrame(held, index=target.index, columns=target.columns)
