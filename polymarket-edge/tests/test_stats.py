import numpy as np
import pandas as pd
import pytest

from polyedge.stats import (
    cluster_bootstrap_mean,
    max_drawdown,
    weekly_performance,
    wilson_interval,
)


def test_wilson_basic():
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi < 0.35
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_narrows_with_n():
    lo1, hi1 = wilson_interval(50, 100)
    lo2, hi2 = wilson_interval(5000, 10000)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_cluster_bootstrap_wider_than_iid():
    rng = np.random.default_rng(0)
    # 50 clusters of 20 identical values -> effective n is 50, not 1000
    cluster_vals = rng.normal(0.05, 1.0, 50)
    values = np.repeat(cluster_vals, 20)
    clusters = np.repeat(np.arange(50), 20)
    res_cl = cluster_bootstrap_mean(values, clusters, n_boot=800, seed=1)
    res_iid = cluster_bootstrap_mean(values, np.arange(1000), n_boot=800, seed=1)
    assert res_cl["boot_std"] > 2 * res_iid["boot_std"]
    assert res_cl["n_clusters"] == 50


def test_cluster_bootstrap_detects_positive_mean():
    rng = np.random.default_rng(3)
    values = rng.normal(0.5, 0.1, 400)
    clusters = np.arange(400)
    res = cluster_bootstrap_mean(values, clusters, n_boot=500)
    assert res["lo"] > 0
    assert res["p_value_le0"] < 0.01


def test_weekly_performance_and_drawdown():
    idx = pd.date_range("2025-01-01", periods=100, freq="D")
    pnl = pd.Series(0.01, index=idx)
    wk = weekly_performance(pnl)
    assert wk["n_weeks"] >= 13
    assert wk["weekly_std"] == pytest.approx(0.0, abs=1e-9) or wk["sharpe_ann"] > 5
    eq = pd.Series([0, 1, 2, 1.5, 3, 2.0], dtype=float)
    assert max_drawdown(eq) == pytest.approx(-1.0)
