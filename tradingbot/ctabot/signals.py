"""Forecast rules.

Every rule emits a *forecast*: a signed expectation of risk-adjusted return,
scaled so that |forecast| averages 10 and capped at +/-20 (Carver's
convention). Scaling factors are estimated from the pooled cross-section
with an *expanding* window shifted one day, so a forecast at time t uses
only information available strictly before t's close is acted on.

Rules (all standard, fixed a priori):
- EWMAC(n, 4n): exponential MA crossover divided by point volatility.
- Breakout(n): position of price within its n-day high/low channel.
- Carry: annualised roll yield divided by annualised volatility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .data import annualised_carry, pct_returns


def point_vol(adj: pd.Series, span: int, min_periods: int) -> pd.Series:
    """EWMA standard deviation of daily price-point moves."""
    return adj.diff().ewm(span=span, min_periods=min_periods).std()


def ewma_pct_vol(returns: pd.Series, cfg: StrategyConfig) -> pd.Series:
    """Annualised percent volatility: EWMA blended 70/30 with its own
    long-run average so post-spike de-risking does not whipsaw."""
    daily = returns.ewm(span=cfg.vol_span, min_periods=cfg.vol_min_periods).std()
    long_run = daily.rolling(cfg.vol_long_window, min_periods=252).mean()
    blended = cfg.vol_blend_short * daily + (1 - cfg.vol_blend_short) * long_run.fillna(daily)
    return blended * np.sqrt(cfg.trading_days_per_year)


def ewmac_forecast(adj: pd.Series, vol_points: pd.Series, fast: int, slow: int) -> pd.Series:
    raw = adj.ewm(span=fast).mean() - adj.ewm(span=slow).mean()
    return raw / vol_points.replace(0.0, np.nan)


def breakout_forecast(adj: pd.Series, window: int) -> pd.Series:
    roll_max = adj.rolling(window, min_periods=window // 2).max()
    roll_min = adj.rolling(window, min_periods=window // 2).min()
    mid = (roll_max + roll_min) / 2.0
    rng = (roll_max - roll_min).replace(0.0, np.nan)
    raw = 40.0 * (adj - mid) / rng
    return raw.ewm(span=max(window // 4, 1)).mean()


def carry_forecast(df: pd.DataFrame, ann_pct_vol: pd.Series, smooth_span: int) -> pd.Series:
    raw = annualised_carry(df) / ann_pct_vol.replace(0.0, np.nan)
    return raw.ewm(span=smooth_span).mean()


def scale_forecasts(raw: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Pooled, expanding, lagged scaling to E|f| = target, then cap.

    The pooled estimator (cross-sectional median of |raw| per day, expanding
    median over days, shifted one day) avoids fitting a scalar per
    instrument and cannot see the future.
    """
    cross_median = raw.abs().median(axis=1)
    pooled = cross_median.expanding(min_periods=cfg.forecast_scalar_min_periods).median().shift(1)
    scalar = cfg.forecast_target_abs / pooled
    scaled = raw.mul(scalar, axis=0)
    return scaled.clip(-cfg.forecast_cap, cfg.forecast_cap)


def build_raw_forecasts(data: dict[str, pd.DataFrame],
                        cfg: StrategyConfig) -> dict[str, pd.DataFrame]:
    """Raw (unscaled) forecasts per rule: rule -> DataFrame[date x instrument]."""
    rules: dict[str, dict[str, pd.Series]] = {}
    for name, df in data.items():
        adj = df["adj"]
        rets = pct_returns(df)
        pvol = point_vol(adj, cfg.vol_span, cfg.vol_min_periods)
        avol = ewma_pct_vol(rets, cfg)
        for fast, slow in cfg.ewmac_spans:
            rules.setdefault(f"ewmac{fast}_{slow}", {})[name] = ewmac_forecast(adj, pvol, fast, slow)
        for window in cfg.breakout_windows:
            rules.setdefault(f"breakout{window}", {})[name] = breakout_forecast(adj, window)
        rules.setdefault("carry", {})[name] = carry_forecast(df, avol, cfg.carry_smooth_span)
    return {rule: pd.DataFrame(series).sort_index() for rule, series in rules.items()}


def combined_forecast(data: dict[str, pd.DataFrame], cfg: StrategyConfig,
                      ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Scaled per-rule forecasts and the capped, FDM-adjusted combination.

    Trend rules are equally weighted within the trend sleeve; the sleeve mix
    is cfg.trend_weight / cfg.carry_weight. Weights renormalise over rules
    that have data, so young instruments are usable as soon as any rule is.
    """
    raw = build_raw_forecasts(data, cfg)
    scaled = {rule: scale_forecasts(frame, cfg) for rule, frame in raw.items()}

    trend_rules = [r for r in scaled if r != "carry"]
    weights = {rule: cfg.trend_weight / len(trend_rules) for rule in trend_rules}
    weights["carry"] = cfg.carry_weight

    frames = []
    weight_frames = []
    for rule, frame in scaled.items():
        w = weights[rule]
        if w == 0.0:
            continue
        # NaN forecasts contribute nothing rather than poisoning the sum
        # (live feeds have no curve data: the carry frame is entirely NaN).
        frames.append((frame * w).fillna(0.0))
        weight_frames.append(frame.notna() * w)
    total = sum(frames[1:], frames[0])
    live_weight = sum(weight_frames[1:], weight_frames[0]).replace(0.0, np.nan)
    combined = (total / live_weight) * cfg.fdm
    return combined.clip(-cfg.forecast_cap, cfg.forecast_cap), scaled
