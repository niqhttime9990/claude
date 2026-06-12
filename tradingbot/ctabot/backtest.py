"""Backtest engine.

Timing convention (deliberately conservative):
- A position decided from information up to close t is *executed at the
  close of t + execution_lag_days* (default: next day's close).
- It therefore first earns the return from that close to the following
  close. With lag = 1 this means P&L_t uses positions decided at t-2.

Costs:
- Trading: |change in held notional| x per-trade cost, where per-trade cost
  is (half-spread + commission) in price points over the contract price.
  The half-spread per instrument comes from pysystemtrade's measured
  spreadcosts.csv.
- Rolling: holding a futures position costs one trade's worth of cost
  `rolls_per_year` times a year, charged as a daily drag on |held|.

Returns are arithmetic daily fractions of (notional) capital. Futures P&L
is inherently *excess of cash*: margin earns interest, so comparing Sharpe
ratios against excess-return benchmarks is apples-to-apples.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .data import pct_returns
from .portfolio import buffered_positions, target_positions
from .signals import combined_forecast, ewma_pct_vol


@dataclass
class BacktestResult:
    net: pd.Series                      # daily net strategy return
    gross: pd.Series                    # before costs
    trade_costs: pd.Series
    roll_costs: pd.Series
    held: pd.DataFrame                  # executed notional positions
    per_instrument_net: pd.DataFrame
    returns: pd.DataFrame               # instrument daily returns used
    forecast: pd.DataFrame
    rule_forecasts: dict = field(default_factory=dict)
    idm: pd.Series | None = None
    # Decision series: target at index t uses information up to t's close
    # and is executed 1+lag bars later. The freshest tradeable target lives
    # here — it cannot be recovered by back-shifting `held`.
    decided: pd.DataFrame | None = None

    def equity(self) -> pd.Series:
        return (1.0 + self.net.fillna(0.0)).cumprod()


def per_trade_cost_frac(data: dict[str, pd.DataFrame], meta: pd.DataFrame,
                        cfg: StrategyConfig) -> pd.DataFrame:
    """Per-unit-notional cost of one trade, per instrument per day."""
    out = {}
    for name, df in data.items():
        points = (meta.loc[name, "spread_cost_points"]
                  + cfg.commission_usd_per_contract / meta.loc[name, "point_size"])
        denom = df["price"].abs().clip(lower=df["price"].abs()
                                       .rolling(252, min_periods=20).median() * 0.1)
        out[name] = cfg.cost_multiplier * points / denom
    return pd.DataFrame(out)


def run_engine(positions: pd.DataFrame, returns: pd.DataFrame,
               cost_frac: pd.DataFrame, rolls_per_year: pd.Series,
               cfg: StrategyConfig) -> BacktestResult:
    """Apply execution lag, compute gross/net P&L and cost drags."""
    idx = returns.index
    pos = positions.reindex(idx).fillna(0.0)
    cost = cost_frac.reindex(idx).ffill().fillna(0.0)
    rets = returns.fillna(0.0)

    held = pos.shift(1 + cfg.execution_lag_days).fillna(0.0)
    gross_by_inst = held * rets
    trades = held.diff().abs().fillna(0.0)
    trade_costs_by_inst = trades * cost
    roll_drag = held.abs() * cost.mul(rolls_per_year, axis=1) / cfg.trading_days_per_year

    net_by_inst = gross_by_inst - trade_costs_by_inst - roll_drag
    return BacktestResult(
        net=net_by_inst.sum(axis=1),
        gross=gross_by_inst.sum(axis=1),
        trade_costs=trade_costs_by_inst.sum(axis=1),
        roll_costs=roll_drag.sum(axis=1),
        held=held,
        per_instrument_net=net_by_inst,
        returns=returns,
        forecast=pd.DataFrame(index=idx),
    )


def run_strategy(data: dict[str, pd.DataFrame], meta: pd.DataFrame,
                 cfg: StrategyConfig | None = None,
                 forecast_override: pd.DataFrame | None = None) -> BacktestResult:
    """Full pipeline: forecasts -> sizing -> buffering -> engine.

    `forecast_override` lets validation code run placebo/permuted forecasts
    through the identical sizing and cost machinery.
    """
    cfg = cfg or StrategyConfig()
    returns = pd.DataFrame({name: pct_returns(df) for name, df in data.items()}).sort_index()

    rule_forecasts: dict = {}
    if forecast_override is None:
        forecast, rule_forecasts = combined_forecast(data, cfg)
    else:
        forecast = forecast_override
    forecast = forecast.reindex(returns.index)

    ann_vol = pd.DataFrame({name: ewma_pct_vol(returns[name], cfg) for name in returns})
    ann_vol = ann_vol.clip(lower=0.01)  # 1% vol floor: don't lever a dead series

    class_of = meta["asset_class"].to_dict()
    pos, avg_scale, idm = target_positions(forecast, ann_vol, returns, class_of, cfg)
    pos = buffered_positions(pos, avg_scale, cfg.position_buffer)

    if cfg.equity_overlay != 0.0 and cfg.equity_overlay_instrument in pos.columns:
        inst = cfg.equity_overlay_instrument
        live_mask = returns[inst].notna().cumsum() > 0
        pos[inst] = pos[inst].fillna(0.0) + cfg.equity_overlay * live_mask

    cost_frac = per_trade_cost_frac(data, meta, cfg)
    result = run_engine(pos, returns, cost_frac, meta["rolls_per_year"], cfg)
    result.forecast = forecast
    result.rule_forecasts = rule_forecasts
    result.idm = idm
    result.decided = pos
    return result
