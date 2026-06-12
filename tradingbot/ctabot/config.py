"""Strategy configuration.

Every numeric parameter here was fixed *a priori* from published, pre-2015
sources (primarily Carver, "Systematic Trading" (2015) and Moskowitz, Ooi &
Pedersen, "Time Series Momentum", JFE 2012; Koijen, Moskowitz, Pedersen &
Vrugt, "Carry", JFE 2018). Nothing in this file was tuned on the dataset
used for backtesting. The validation suite perturbs these values to check
the result is a plateau, not a spike.
"""

from dataclasses import dataclass, field

# Pinned upstream data snapshot (robcarver17/pysystemtrade @ commit below).
DATA_REPO = "robcarver17/pysystemtrade"
DATA_SHA = "883c8681cf880d83acad5c39b842403a8eac5676"

# Universe: liquid futures, grouped by asset class. Class -> instruments.
# Diversification across classes is itself part of the design (equal risk
# weight per class, then per instrument within class).
UNIVERSE: dict[str, list[str]] = {
    "Equity": ["SP500", "NASDAQ", "DOW", "EUROSTX"],
    "Bond": ["US2", "US5", "US10", "US30", "BUND"],
    "Metals": ["GOLD", "SILVER", "COPPER", "PLAT"],
    "OilGas": ["CRUDE_W", "BRENT_W", "GAS_US", "HEATOIL"],
    "Ags": ["CORN", "WHEAT", "SOYBEAN", "SUGAR11", "COFFEE", "LIVECOW"],
}


def all_instruments() -> list[str]:
    return [i for instruments in UNIVERSE.values() for i in instruments]


@dataclass(frozen=True)
class StrategyConfig:
    # --- Signals (Carver 2015 standard rule set) ---
    ewmac_spans: tuple[tuple[int, int], ...] = ((16, 64), (32, 128), (64, 256))
    breakout_windows: tuple[int, ...] = (80, 160)
    carry_smooth_span: int = 90
    # Forecast processing
    forecast_target_abs: float = 10.0   # scale raw forecasts to E|f| = 10
    forecast_cap: float = 20.0
    forecast_scalar_min_periods: int = 250  # expanding window burn-in (days)
    # Sleeve weights: trend vs carry (Carver's long-standing default mix)
    trend_weight: float = 0.6
    carry_weight: float = 0.4
    # Forecast diversification multiplier for ~6 rules across 2 styles
    # (Carver 2015, table 17-equivalent; fixed a priori, not estimated).
    fdm: float = 1.25

    # --- Volatility estimation ---
    vol_span: int = 35                  # EWMA span on daily % returns
    vol_min_periods: int = 100
    # Blend short-run EWMA with a long-run average of itself; tames the
    # de-risk/re-risk whipsaw after vol spikes (Carver's 70/30 blend).
    vol_blend_short: float = 0.7
    vol_long_window: int = 2500         # ~10y rolling mean of the EWMA vol

    # --- Portfolio construction ---
    vol_target_annual: float = 0.20     # annualised portfolio vol target
    idm_cap: float = 2.5                # instrument diversification multiplier cap
    idm_window: int = 1250              # trailing window (days) for IDM estimate
    idm_min_periods: int = 750
    position_buffer: float = 0.10       # trade only outside +/-10% of avg position

    # --- Execution & costs ---
    execution_lag_days: int = 1         # decide at close t, trade at close t+1
    commission_usd_per_contract: float = 1.5
    cost_multiplier: float = 1.0        # stress knob; 1.0 = base costs

    # --- Calendar ---
    trading_days_per_year: int = 256    # Carver's convention

    # --- Return stacking ---
    # Constant additional long S&P 500 notional (fraction of capital) laid
    # on top of the strategy ("portable alpha"). 1.0 = full equity-market
    # exposure plus the overlay; pays the same roll/trade costs.
    equity_overlay: float = 0.0
    equity_overlay_instrument: str = "SP500"

    # --- Sample split: design frozen on data <= insample_end; later data
    # is genuinely out-of-sample for every choice made in this repo. ---
    insample_end: str = "2014-12-31"


DEFAULT = StrategyConfig()

# Presets answering different objectives. Sharpe is roughly invariant to
# vol_target (it just scales positions); average return is not.
#   base       — the validated 20%-vol strategy.
#   aggressive — same signals, 30% vol target. Higher mean, deeper drawdowns.
#   stacked    — 100% S&P futures exposure PLUS the overlay at 20% vol:
#                collects the equity risk premium and the (near-uncorrelated)
#                trend/carry premium on the same capital.
PRESETS: dict[str, StrategyConfig] = {
    "base": StrategyConfig(),
    "aggressive": StrategyConfig(vol_target_annual=0.30),
    "stacked": StrategyConfig(equity_overlay=1.0),
}


@dataclass(frozen=True)
class BacktestArtifacts:
    """Paths used by scripts; kept in one place."""
    data_dir: str = "data"
    raw_dir: str = "data/raw"
    manifest: str = "data/manifest.json"
    reports_dir: str = "reports"
    figures_dir: str = "reports/figures"


PATHS = BacktestArtifacts()
