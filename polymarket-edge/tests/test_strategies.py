import numpy as np
import pandas as pd
import pytest

from polyedge.backtest import dedupe_per_event, evaluate, max_concurrency
from polyedge.dataio import build_settlement_table, settle_time
from polyedge.strategies import favorite_trades, momentum_trades, negrisk_sum_series
from tests.conftest import DAY, T0, make_market, path_market


def test_settle_time_finds_flatline():
    g = path_market("x", [(0, 0.5), (1, 0.7), (2, 0.97), (3, 1.0), (4, 1.0)])
    st = settle_time(g, 1.0)
    assert st == pytest.approx(T0 + 3 * DAY)


def test_favorite_trades_basic(simple_universe, flat_spread):
    markets, prices = simple_universe
    settle = build_settlement_table(markets, prices)
    trades = favorite_trades(prices, markets, settle, flat_spread,
                             theta=0.93, window_days=7, side_mode="both",
                             min_volume=0)
    assert set(trades["market_id"]) == {"m1", "m2"}
    t1 = trades[trades["market_id"] == "m1"].iloc[0]
    assert t1["side"] == "YES"
    # first bar in final 7d with p >= 0.93: grid day 8.0 (p=0.94), fill +1c
    assert t1["fill"] == pytest.approx(0.95, abs=1e-9)
    assert t1["ret"] == pytest.approx(1 / 0.95 - 1, abs=1e-9)
    t2 = trades[trades["market_id"] == "m2"].iloc[0]
    assert t2["side"] == "NO"
    assert t2["fill"] == pytest.approx(0.95, abs=1e-9)
    assert t2["ret"] == pytest.approx(1 / 0.95 - 1, abs=1e-9)


def test_favorite_no_entry_after_closed_time(flat_spread):
    # market resolves early (closed at day 5) but end_date is day 10;
    # price pins at 1.0 from day 5 — no entry may occur at/after closure
    markets = pd.DataFrame([
        make_market("m1", end_days=10, outcome=1.0, closed_days=5),
    ])
    pts = [(d / 2, 0.9) for d in range(0, 10)] + [(5.0, 1.0), (6.0, 1.0), (10.0, 1.0)]
    prices = path_market("m1", pts)
    settle = build_settlement_table(markets, prices)
    trades = favorite_trades(prices, markets, settle, flat_spread,
                             theta=0.85, window_days=7, side_mode="both",
                             min_volume=0)
    if not trades.empty:
        assert (trades["signal_t"] < T0 + 5 * DAY).all()


def test_no_lookahead_signals_identical_when_future_differs(flat_spread):
    """Two universes identical through day 8, divergent after: every signal
    decided at t <= day 8 must be identical."""
    base = [(d / 2, 0.5 + 0.05 * (d / 2)) for d in range(0, 17)]  # through day 8
    fut_a = base + [(9.0, 0.99), (10.0, 1.0)]
    fut_b = base + [(9.0, 0.10), (10.0, 0.0)]
    mk_a = pd.DataFrame([make_market("m", end_days=10, outcome=1.0)])
    mk_b = pd.DataFrame([make_market("m", end_days=10, outcome=0.0)])
    pa, pb = path_market("m", fut_a), path_market("m", fut_b)
    sa, sb = build_settlement_table(mk_a, pa), build_settlement_table(mk_b, pb)
    for kwargs in [dict(theta=0.90, window_days=7, side_mode="both", min_volume=0)]:
        ta = favorite_trades(pa, mk_a, sa, flat_spread, **kwargs)
        tb = favorite_trades(pb, mk_b, sb, flat_spread, **kwargs)
        ta8 = ta[ta["signal_t"] <= T0 + 8 * DAY]
        tb8 = tb[tb["signal_t"] <= T0 + 8 * DAY]
        assert len(ta8) == len(tb8)
        if len(ta8):
            assert (ta8["signal_t"].to_numpy() == tb8["signal_t"].to_numpy()).all()
            assert (ta8["fill"].to_numpy() == tb8["fill"].to_numpy()).all()
            assert (ta8["side"].to_numpy() == tb8["side"].to_numpy()).all()

    ma = momentum_trades(pa, mk_a, sa, flat_spread, delta=0.05, min_volume=0)
    mb = momentum_trades(pb, mk_b, sb, flat_spread, delta=0.05, min_volume=0)
    ma8 = ma[ma["signal_t"] <= T0 + 8 * DAY] if not ma.empty else ma
    mb8 = mb[mb["signal_t"] <= T0 + 8 * DAY] if not mb.empty else mb
    assert len(ma8) == len(mb8)
    if len(ma8):
        assert (ma8["signal_t"].to_numpy() == mb8["signal_t"].to_numpy()).all()
        assert (ma8["side"].to_numpy() == mb8["side"].to_numpy()).all()


def test_momentum_direction_and_exit(flat_spread):
    # jump from 0.3 to 0.5 on day 5 -> 'with' buys YES at 0.5+h
    pts = [(0, 0.30), (1, 0.30), (2, 0.30), (3, 0.30), (4, 0.30),
           (5, 0.50), (6, 0.60), (7, 0.70), (9, 0.95), (10, 1.0)]
    markets = pd.DataFrame([make_market("m", end_days=10, outcome=1.0)])
    prices = path_market("m", pts)
    settle = build_settlement_table(markets, prices)
    t = momentum_trades(prices, markets, settle, flat_spread, delta=0.15,
                        direction="with", min_volume=0)
    assert len(t) == 1
    row = t.iloc[0]
    assert row["side"] == "YES"
    assert row["fill"] == pytest.approx(0.51)
    assert row["ret"] == pytest.approx(1 / 0.51 - 1)
    # time exit at 3d: first bar >= day 8 is day 9 (p=0.95), sell at -h
    t3 = momentum_trades(prices, markets, settle, flat_spread, delta=0.15,
                         direction="with", hold_days=3.0, min_volume=0)
    row3 = t3.iloc[0]
    assert row3["exit_val"] == pytest.approx(0.94)
    against = momentum_trades(prices, markets, settle, flat_spread, delta=0.15,
                              direction="against", min_volume=0)
    assert against.iloc[0]["side"] == "NO"


def test_negrisk_sum_series_detects_mispricing():
    ev = "ev1"
    markets = pd.DataFrame([
        make_market("a", 10, 1.0, event_id=ev, neg_risk=True),
        make_market("b", 10, 0.0, event_id=ev, neg_risk=True),
        make_market("c", 10, 0.0, event_id=ev, neg_risk=True),
    ])
    grid = [(d, p) for d, p in [(0, 0.5), (1, 0.5), (2, 0.5)]]
    prices = pd.concat([
        path_market("a", grid), path_market("b", grid), path_market("c", grid),
    ], ignore_index=True)
    nr = negrisk_sum_series(prices, markets)
    assert not nr.empty
    assert nr["sum_yes"].iloc[0] == pytest.approx(1.5)
    assert (nr["n_members"] == 3).all()


def test_dedupe_and_concurrency():
    trades = pd.DataFrame({
        "market_id": ["1", "2", "3", "4"],
        "event_id": ["e", "e", "e", None],
        "volume": [100.0, 300.0, 200.0, 50.0],
        "signal_t": [0.0, 0.0, 0.0, 10.0],
        "exit_t": [100.0, 100.0, 100.0, 20.0],
        "ret": [0.1, 0.1, 0.1, 0.1],
        "fill": [0.5] * 4, "exit_val": [0.55] * 4,
        "side": ["YES"] * 4, "category": ["t"] * 4,
    })
    d = dedupe_per_event(trades, max_per_event=2)
    assert len(d) == 3  # 2 from event e (highest volume) + singleton
    assert set(d[d["event_id"] == "e"]["market_id"]) == {"2", "3"}
    # trades 2,3 span [0,100]; trade 4 spans [10,20] inside it -> peak 3
    assert max_concurrency(d) == 3
    assert max_concurrency(d[d["event_id"] == "e"]) == 2


def test_evaluate_math():
    trades = pd.DataFrame({
        "market_id": list("abcd"),
        "event_id": [None] * 4,
        "volume": [1e4] * 4,
        "signal_t": [pd.Timestamp("2025-01-01").timestamp()] * 4,
        "exit_t": [pd.Timestamp("2025-01-08").timestamp()] * 4,
        "ret": [0.05, 0.05, -0.02, 0.04],
        "fill": [0.9] * 4, "exit_val": [1.0] * 4,
        "side": ["YES"] * 4, "category": ["t"] * 4,
    })
    ev = evaluate(trades, "t", n_boot=300)
    assert ev["n_trades"] == 4
    assert ev["mean_ret"] == pytest.approx(np.mean([0.05, 0.05, -0.02, 0.04]))
    assert ev["hit_rate"] == 0.75
