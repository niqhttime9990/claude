"""Loading and shaping the historical dataset produced by pipeline/fetch_data.py.

Conventions used everywhere downstream:
  * prices are YES-token mids in [0, 1]; NO is the complement
  * `t` is unix seconds (UTC); pandas timestamps are tz-naive UTC
  * outcome: 1.0 YES won, 0.0 NO won, 0.5 tie/invalid, NaN unparseable
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATE_COLS = ["start_date", "end_date", "created_at", "closed_time"]


def _to_utc_naive(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
    return out.dt.tz_localize(None)


def load_markets(data_dir: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(Path(data_dir) / "markets.parquet")
    for c in DATE_COLS:
        if c in df.columns:
            df[c] = _to_utc_naive(df[c])
    df["market_id"] = df["market_id"].astype(str)
    # A market is usable for outcome studies only with a clean binary label.
    df["resolved_clean"] = df["outcome"].isin([0.0, 1.0])
    return df


def load_prices(data_dir: str | Path, tag: str = "12h") -> pd.DataFrame:
    parts = sorted(Path(data_dir).glob(f"prices_{tag}_*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no prices_{tag}_*.parquet shards in {data_dir}")
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df["market_id"] = df["market_id"].astype(str)
    df = df.dropna(subset=["t", "p"])
    df = df[(df["p"] >= 0.0) & (df["p"] <= 1.0)]
    df = df.sort_values(["market_id", "t"], kind="stable").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["t"], unit="s")
    return df


def settle_time(group: pd.DataFrame, outcome: float, tol: float = 0.005) -> float | None:
    """First timestamp after which the price stays pinned at the outcome.

    Histories of resolved markets end in a flatline at 0/1 once the result is
    known. Snapshots taken inside that flatline would fake perfect
    calibration, so studies anchor on the moment the flatline starts.
    Uses outcome knowledge — descriptive analyses only, never strategies.
    """
    p = group["p"].to_numpy()
    t = group["t"].to_numpy()
    if len(p) == 0:
        return None
    pinned = np.abs(p - outcome) < tol
    # last index where the price is NOT pinned; settle = the next sample
    not_pinned = np.flatnonzero(~pinned)
    if len(not_pinned) == 0:
        return float(t[0])
    i = not_pinned[-1]
    if i == len(p) - 1:
        return float(t[-1])  # never settled before history ends
    return float(t[i + 1])


def build_settlement_table(markets: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Per-market: settle_t (price pin time), last_t, first_t, n_points."""
    rows = []
    out_map = markets.set_index("market_id")["outcome"].to_dict()
    for mid, g in prices.groupby("market_id", sort=False):
        outcome = out_map.get(mid)
        if outcome not in (0.0, 1.0):
            continue
        rows.append({
            "market_id": mid,
            "settle_t": settle_time(g, outcome),
            "first_t": float(g["t"].iloc[0]),
            "last_t": float(g["t"].iloc[-1]),
            "n_points": int(len(g)),
        })
    return pd.DataFrame(rows)


def snapshot_at_horizon(
    prices: pd.DataFrame,
    settle: pd.DataFrame,
    horizon_s: float,
    min_life_s: float = 2 * 86400,
) -> pd.DataFrame:
    """Last observed price at (settle_t - horizon) per market.

    Markets must have existed for at least `min_life_s` before the snapshot
    so the price had a chance to be a market price rather than an opening
    quote. Snapshot must precede the settle flatline by construction.
    """
    s = settle.dropna(subset=["settle_t"]).copy()
    s["cut_t"] = s["settle_t"] - horizon_s
    s = s[s["cut_t"] - s["first_t"] >= min_life_s]
    merged = prices.merge(s[["market_id", "cut_t"]], on="market_id", how="inner")
    merged = merged[merged["t"] <= merged["cut_t"]]
    # staleness guard: snapshot must be within 36h of the cut
    merged = merged[merged["cut_t"] - merged["t"] <= 36 * 3600]
    idx = merged.groupby("market_id")["t"].idxmax()
    snap = merged.loc[idx, ["market_id", "t", "p"]].rename(
        columns={"t": "snap_t", "p": "snap_p"}
    )
    return snap.reset_index(drop=True)


def price_series(prices: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-market (t, p) arrays, computed once and shared across strategy
    grid cells (the groupby is the hot path on multi-million-row panels)."""
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for mid, g in prices.groupby("market_id", sort=False):
        out[mid] = (g["t"].to_numpy(dtype=float), g["p"].to_numpy(dtype=float))
    return out


def load_active_books(data_dir: str | Path) -> pd.DataFrame | None:
    p = Path(data_dir) / "active_books.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df.dropna(subset=["best_bid", "best_ask"])
    df = df[(df["best_ask"] > df["best_bid"]) & (df["best_ask"] <= 1) & (df["best_bid"] >= 0)]
    df["spread"] = df["best_ask"] - df["best_bid"]
    return df


def spread_model(books: pd.DataFrame | None, active_markets: pd.DataFrame | None) -> dict:
    """Empirical half-spread by 24h-volume tier, used as the execution
    haircut in backtests. Falls back to conservative constants if the
    snapshot is missing."""
    fallback = {"tiers": [0.0, 10_000.0, 100_000.0],
                "half_spread": [0.02, 0.01, 0.005],
                "source": "fallback_constants"}
    if books is None or active_markets is None or books.empty:
        return fallback
    am = active_markets[["market_id", "volume_24h", "volume"]].copy()
    am["market_id"] = am["market_id"].astype(str)
    b = books.copy()
    b["market_id"] = b["market_id"].astype(str)
    df = b.merge(am, on="market_id", how="left")
    df = df[df["spread"] < 0.5]  # drop husks with no real book
    if len(df) < 30:
        return fallback
    tiers = [0.0, 10_000.0, 100_000.0]
    halves = []
    for lo, hi in zip(tiers, tiers[1:] + [np.inf]):
        sel = df[(df["volume_24h"] >= lo) & (df["volume_24h"] < hi)]
        halves.append(float(sel["spread"].median() / 2) if len(sel) >= 10 else np.nan)
    # fill gaps from neighbours, then floor at half a tick
    halves = pd.Series(halves).bfill().ffill().fillna(0.01).clip(lower=0.005).tolist()
    return {"tiers": tiers, "half_spread": halves, "source": "active_book_snapshot",
            "n_books": int(len(df))}


def haircut_for_volume(volume_24h_proxy: np.ndarray, model: dict) -> np.ndarray:
    tiers = model["tiers"]
    hs = model["half_spread"]
    out = np.full(len(volume_24h_proxy), hs[0], dtype=float)
    for i, lo in enumerate(tiers):
        out[volume_24h_proxy >= lo] = hs[i]
    return out
