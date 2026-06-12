"""Signal-level regression tests."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctabot.config import StrategyConfig
from ctabot.signals import combined_forecast
from tests.test_engine import synth_universe

CFG = StrategyConfig(forecast_scalar_min_periods=100, vol_min_periods=50)


def test_all_nan_carry_does_not_poison_combination():
    """A rule whose forecasts are entirely NaN (e.g. carry on a live feed
    with no curve data) must not NaN-out the combined forecast — with any
    sleeve weighting."""
    data, _meta = synth_universe()
    for df in data.values():
        df[["carry_price", "price_contract", "carry_contract"]] = np.nan

    for cfg in (CFG,  # default 60/40 trend/carry
                StrategyConfig(forecast_scalar_min_periods=100, vol_min_periods=50,
                               trend_weight=1.0, carry_weight=0.0)):
        combined, scaled = combined_forecast(data, cfg)
        assert scaled["carry"].isna().all().all()
        tail = combined.iloc[-500:]
        assert tail.notna().all().all(), "combined forecast lost coverage"
        assert (tail.abs() > 1e-9).any().any(), "combined forecast is all zero"


def test_missing_rule_renormalises_not_dilutes():
    """Where only trend rules have data, the combination should average the
    trend rules at full weight, not shrink toward zero."""
    data, _meta = synth_universe()
    for df in data.values():
        df[["carry_price", "price_contract", "carry_contract"]] = np.nan
    combined_no_carry, _ = combined_forecast(data, CFG)

    cfg_trend = StrategyConfig(forecast_scalar_min_periods=100, vol_min_periods=50,
                               trend_weight=1.0, carry_weight=0.0)
    combined_trend, _ = combined_forecast(data, cfg_trend)
    pd.testing.assert_frame_equal(combined_no_carry, combined_trend)
