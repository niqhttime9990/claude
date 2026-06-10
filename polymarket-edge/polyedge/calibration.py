"""Market calibration analysis: at a fixed horizon before resolution, how
often does YES actually happen as a function of the quoted price? The
deviation profile (favorite-longshot bias and friends) is the raw material
for the strategies; this module only measures, it does not trade."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dataio import snapshot_at_horizon
from .stats import binomial_calibration_test, event_clusters as _clusters, wilson_interval


def calibration_table(
    prices: pd.DataFrame,
    markets: pd.DataFrame,
    settle: pd.DataFrame,
    horizon_s: float,
    n_bins: int = 20,
    min_volume: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per-market snapshot table, binned calibration table)."""
    snap = snapshot_at_horizon(prices, settle, horizon_s)
    m = markets[markets["resolved_clean"]][
        ["market_id", "outcome", "volume", "category", "event_id"]
    ]
    if min_volume > 0:
        m = m[m["volume"] >= min_volume]
    df = snap.merge(m, on="market_id", how="inner")
    df = df[(df["snap_p"] > 0.0) & (df["snap_p"] < 1.0)]

    edges = np.linspace(0, 1, n_bins + 1)
    df["bin"] = np.clip(np.digitize(df["snap_p"], edges) - 1, 0, n_bins - 1)
    rows = []
    for b, g in df.groupby("bin"):
        n = len(g)
        k = int(g["outcome"].sum())
        lo, hi = wilson_interval(k, n)
        rows.append({
            "bin_lo": edges[b], "bin_hi": edges[b + 1],
            "mid": (edges[b] + edges[b + 1]) / 2,
            "mean_price": float(g["snap_p"].mean()),
            "emp_rate": k / n, "wilson_lo": lo, "wilson_hi": hi,
            "n": n, "gap": k / n - float(g["snap_p"].mean()),
        })
    return df, pd.DataFrame(rows)


def flb_tests(snapshots: pd.DataFrame) -> dict:
    """Favorite-longshot bias tests on the per-market snapshot table,
    overall and per segment. Errors cluster by event (sibling outcomes of
    one election/championship are one draw, not fifty)."""
    out = {"overall": binomial_calibration_test(
        snapshots["snap_p"].to_numpy(), snapshots["outcome"].to_numpy(),
        _clusters(snapshots))}
    for name, sel in [
        ("vol>=10k", snapshots["volume"] >= 10_000),
        ("vol>=100k", snapshots["volume"] >= 100_000),
    ]:
        g = snapshots[sel]
        out[name] = binomial_calibration_test(
            g["snap_p"].to_numpy(), g["outcome"].to_numpy(), _clusters(g))
    for cat, g in snapshots.groupby(snapshots["category"].fillna("uncat")):
        if len(g) >= 300:
            out[f"cat:{cat}"] = binomial_calibration_test(
                g["snap_p"].to_numpy(), g["outcome"].to_numpy(), _clusters(g))
    return out


def edge_zones(snapshots: pd.DataFrame, zones: list[tuple[float, float]]) -> pd.DataFrame:
    """Expected return of buying YES (and NO) in given price zones, gross of
    costs — a quick mispricing map before strategy construction."""
    rows = []
    for lo, hi in zones:
        g = snapshots[(snapshots["snap_p"] >= lo) & (snapshots["snap_p"] < hi)]
        if len(g) < 30:
            continue
        p = g["snap_p"].to_numpy()
        y = g["outcome"].to_numpy()
        ret_yes = y / p - 1.0
        ret_no = (1 - y) / (1 - p) - 1.0
        rows.append({
            "zone": f"[{lo:.2f},{hi:.2f})", "n": len(g),
            "mean_price": float(p.mean()), "emp_rate": float(y.mean()),
            "gross_ret_yes": float(ret_yes.mean()),
            "gross_ret_no": float(ret_no.mean()),
        })
    return pd.DataFrame(rows)
