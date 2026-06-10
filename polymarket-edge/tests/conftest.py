import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DAY = 86400
T0 = pd.Timestamp("2025-06-01").timestamp()


def make_market(mid, end_days, outcome, volume=50_000.0, event_id=None,
                closed_days=None, neg_risk=False):
    end = pd.Timestamp("2025-06-01") + pd.Timedelta(days=end_days)
    return {
        "market_id": str(mid),
        "question": f"q{mid}",
        "category": "test",
        "event_id": event_id,
        "event_neg_risk": neg_risk,
        "neg_risk": neg_risk,
        "volume": volume,
        "outcome": outcome,
        "resolved_clean": outcome in (0.0, 1.0),
        "end_date": end,
        "closed_time": (pd.Timestamp("2025-06-01") + pd.Timedelta(days=closed_days))
        if closed_days is not None else pd.NaT,
        "start_date": pd.Timestamp("2025-05-01"),
        "created_at": pd.Timestamp("2025-05-01"),
    }


def path_market(mid, pts):
    """pts: list of (day_offset, price)."""
    return pd.DataFrame({
        "market_id": str(mid),
        "t": [T0 + d * DAY for d, _ in pts],
        "p": [p for _, p in pts],
    })


@pytest.fixture
def flat_spread():
    return {"tiers": [0.0], "half_spread": [0.01], "source": "test"}


@pytest.fixture
def simple_universe():
    """One favorite that wins, one longshot that loses (i.e. NO wins)."""
    markets = pd.DataFrame([
        make_market("m1", end_days=10, outcome=1.0),
        make_market("m2", end_days=10, outcome=0.0),
    ])
    # m1 trades up to 0.95 well before end; m2 sits at 0.06
    grid = np.arange(0, 10.5, 0.5)
    p1 = np.clip(0.70 + 0.03 * grid, 0, 0.95)
    p2 = np.full_like(grid, 0.06)
    prices = pd.concat([
        path_market("m1", list(zip(grid, p1))),
        path_market("m2", list(zip(grid, p2))),
        # settle flatlines after end
        path_market("m1", [(10.5, 1.0), (11.0, 1.0)]),
        path_market("m2", [(10.5, 0.0), (11.0, 0.0)]),
    ], ignore_index=True).sort_values(["market_id", "t"]).reset_index(drop=True)
    return markets, prices
