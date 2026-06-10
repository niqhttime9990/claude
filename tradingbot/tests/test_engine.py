"""Engine correctness tests.

The single most important property of a backtest is that results at time t
cannot depend on data after t. `test_no_lookahead_*` verify this directly:
truncating or corrupting future data must not change earlier results.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctabot.backtest import run_engine, run_strategy
from ctabot.config import StrategyConfig
from ctabot.data import annualised_carry, pct_returns
from ctabot.portfolio import buffered_positions
from ctabot.signals import scale_forecasts


def synth_universe(n_days: int = 4000, n_inst: int = 6, seed: int = 3,
                   ann_drift: float = 0.05):
    """Synthetic instruments with realistic vol, contango curves and meta."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=n_days)
    data = {}
    rows = []
    classes = ["Equity", "Bond", "Metals"]
    for k in range(n_inst):
        vol = 0.10 + 0.05 * k
        rets = rng.normal(ann_drift / 256, vol / 16, n_days)
        price = 100 * np.exp(np.cumsum(rets))
        df = pd.DataFrame(index=idx)
        df["adj"] = price
        df["price"] = price
        df["carry_price"] = price * 1.005   # mild contango
        df["price_contract"] = 20240300
        df["carry_contract"] = 20240500
        name = f"SYN{k}"
        data[name] = df
        rows.append({"instrument": name, "asset_class": classes[k % 3],
                     "point_size": 100.0, "currency": "USD",
                     "spread_cost_points": price.mean() * 0.0001,
                     "rolls_per_year": 4})
    meta = pd.DataFrame(rows).set_index("instrument")
    return data, meta


CFG = StrategyConfig(forecast_scalar_min_periods=100, vol_min_periods=50,
                     idm_min_periods=300)


def test_no_lookahead_truncation():
    """Dropping the last 400 days must not change any earlier daily return."""
    data, meta = synth_universe()
    full = run_strategy(data, meta, CFG).net
    cut = {k: df.iloc[:-400] for k, df in data.items()}
    trunc = run_strategy(cut, meta, CFG).net
    common = trunc.index
    pd.testing.assert_series_equal(full.loc[common], trunc, atol=1e-12, rtol=0)


def test_no_lookahead_future_corruption():
    """Multiplying all prices after a date by 5 must not change results before it."""
    data, meta = synth_universe()
    base = run_strategy(data, meta, CFG).net
    corrupt = {}
    cutoff = data["SYN0"].index[3000]
    for k, df in data.items():
        df2 = df.copy()
        df2.loc[df2.index > cutoff, ["adj", "price", "carry_price"]] *= 5.0
        corrupt[k] = df2
    corrupted = run_strategy(corrupt, meta, CFG).net
    pd.testing.assert_series_equal(base.loc[:cutoff], corrupted.loc[:cutoff],
                                   atol=1e-12, rtol=0)


def test_execution_lag():
    """With lag L, a position decided at t first earns the return at t+L+1."""
    idx = pd.bdate_range("2020-01-01", periods=10)
    pos = pd.DataFrame({"X": [0, 1, 1, 1, 1, 1, 1, 1, 1, 1]}, index=idx, dtype=float)
    rets = pd.DataFrame({"X": [0.01] * 10}, index=idx)
    cost = pd.DataFrame({"X": [0.0] * 10}, index=idx)
    rolls = pd.Series({"X": 0})
    res = run_engine(pos, rets, cost, rolls, StrategyConfig(execution_lag_days=1))
    # pos set at index 1 -> held from index 3 onwards (shift 2)
    assert res.net.iloc[2] == 0.0
    assert res.net.iloc[3] == pytest.approx(0.01)


def test_costs_identity_and_monotonicity():
    data, meta = synth_universe()
    r1 = run_strategy(data, meta, CFG)
    assert np.allclose(r1.net, r1.gross - r1.trade_costs - r1.roll_costs)
    assert r1.trade_costs.sum() > 0 and r1.roll_costs.sum() > 0
    r5 = run_strategy(data, meta, StrategyConfig(
        forecast_scalar_min_periods=100, vol_min_periods=50, idm_min_periods=300,
        cost_multiplier=5.0))
    assert r5.net.sum() < r1.net.sum()


def test_vol_targeting_single_instrument():
    """Constant max forecast on one synthetic instrument -> realised vol near
    2x target (forecast 20 = 2x average position), IDM = 1."""
    data, meta = synth_universe(n_inst=1, n_days=5000)
    template = pd.DataFrame({"SYN0": 1.0}, index=data["SYN0"].index)
    res = run_strategy(data, meta, CFG, forecast_override=template * 10.0)
    realised = res.net.iloc[300:].std() * np.sqrt(256)
    assert realised == pytest.approx(CFG.vol_target_annual, rel=0.25)


def test_forecast_scaling_is_expanding_and_lagged():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2000-01-03", periods=1000)
    raw = pd.DataFrame(rng.normal(0, 2, (1000, 3)), index=idx, columns=list("ABC"))
    scaled1 = scale_forecasts(raw, CFG)
    raw2 = raw.copy()
    raw2.iloc[600:] *= 100  # corrupt the future
    scaled2 = scale_forecasts(raw2, CFG)
    pd.testing.assert_frame_equal(scaled1.iloc[:600], scaled2.iloc[:600])
    assert scaled1.abs().max().max() <= CFG.forecast_cap + 1e-9


def test_buffering_no_trade_inside_band():
    idx = pd.bdate_range("2020-01-01", periods=5)
    target = pd.DataFrame({"X": [1.0, 1.005, 0.995, 1.004, 0.996]}, index=idx)
    scale = pd.DataFrame({"X": [1.0] * 5}, index=idx)
    held = buffered_positions(target, scale, buffer_frac=0.10)
    assert held["X"].iloc[1:].diff().dropna().abs().max() == 0.0


def test_buffering_holds_through_gap():
    idx = pd.bdate_range("2020-01-01", periods=6)
    target = pd.DataFrame({"X": [1.0, np.nan, np.nan, 1.0, 1.0, 1.0]}, index=idx)
    scale = pd.DataFrame({"X": [1.0] * 6}, index=idx)
    held = buffered_positions(target, scale, buffer_frac=0.10)
    assert (held["X"] > 0.8).all()


def test_carry_sign_and_magnitude():
    idx = pd.bdate_range("2024-01-01", periods=300)
    df = pd.DataFrame(index=idx)
    df["price"] = 100.0
    df["carry_price"] = 101.0          # contango, carry contract 2 months later
    df["price_contract"] = 20240600
    df["carry_contract"] = 20240800
    df["adj"] = 100.0
    c = annualised_carry(df)
    # (100 - 101) / (2/12) / 100 = -6% annualised
    assert c.iloc[-1] == pytest.approx(-0.06, abs=1e-9)


def test_pct_returns_uses_contract_price():
    idx = pd.bdate_range("2024-01-01", periods=40)
    df = pd.DataFrame(index=idx)
    df["adj"] = np.linspace(500, 539, 40)      # +1 point/day
    df["price"] = np.linspace(100, 139, 40)    # actual contract price
    df["carry_price"] = df["price"]
    df["price_contract"] = 20240600
    df["carry_contract"] = 20240800
    r = pct_returns(df)
    assert r.iloc[1] == pytest.approx(1.0 / 100.0)
    assert r.iloc[-1] == pytest.approx(1.0 / 138.0)
