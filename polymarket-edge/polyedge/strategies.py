"""Signal generation for backtests. Every rule here is ex ante: a decision at
bar t uses only prices with timestamp <= t plus static metadata that was
known before the market started (end_date, volume filters use lifetime
volume as a liquidity proxy — see report caveats).

Execution model: by default a trade decided at bar i fills at the WORSE of
bar i and bar i+1 prices for the bought side, plus a haircut (empirical
half-spread by liquidity tier). The signal bar alone is not executable
information — the 12h series is built from prints, and chasing a stale
print is the dominant backtest illusion here (same-bar mean-reversion
"profits" collapse ~75% under next-bar entry). entry_bar="same" remains
available to quantify that gap. Buying NO is priced as (1 - yes_p) +
haircut, valid because CLOB YES/NO books are complements.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dataio import haircut_for_volume, price_series


def _as_series(prices) -> dict:
    if isinstance(prices, dict):
        return prices
    return price_series(prices)


def _prep(markets: pd.DataFrame) -> pd.DataFrame:
    m = markets[markets["resolved_clean"]].copy()
    m["end_t"] = m["end_date"].apply(lambda x: x.timestamp() if pd.notna(x) else np.nan)
    m["closed_t"] = m["closed_time"].apply(lambda x: x.timestamp() if pd.notna(x) else np.nan)
    return m.dropna(subset=["end_t"])


def _execution(
    entry_bar: str,
    buy_yes: bool,
    i: int,
    t_arr: np.ndarray,
    p_arr: np.ndarray,
    hard_stop: float,
    h: float,
) -> tuple[float, float, int] | None:
    """Fill price/time for a decision at bar i. Returns (fill, entry_t, entry_i)
    or None if the trade cannot be executed honestly."""
    p_sig = p_arr[i]
    if entry_bar == "same":
        p_exec, t_exec, i_exec = p_sig, t_arr[i], i
    else:  # "next_worse": worse of signal and next bar, entered at next bar
        if i + 1 >= len(t_arr):
            return None
        t1, p1 = t_arr[i + 1], p_arr[i + 1]
        if t1 >= hard_stop or not (0.005 < p1 < 0.995):
            return None
        p_exec = max(p_sig, p1) if buy_yes else min(p_sig, p1)
        t_exec, i_exec = t1, i + 1
    fill = (p_exec if buy_yes else 1.0 - p_exec) + h
    return min(fill, 0.999), float(t_exec), i_exec


def _attach_exits(
    trades: list[dict], settle_map: dict[str, float], end_map: dict[str, float]
) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["exit_t"] = [
        settle_map.get(m, end_map.get(m, np.nan)) for m in df["market_id"]
    ]
    df["exit_t"] = df[["exit_t", "signal_t"]].max(axis=1) + 60.0
    return df


def favorite_trades(
    prices: pd.DataFrame,
    markets: pd.DataFrame,
    settle: pd.DataFrame,
    spread: dict,
    theta: float,
    window_days: float,
    side_mode: str = "both",  # "yes" buy high-priced favorites, "no" fade longshots, "both"
    min_volume: float = 10_000.0,
    haircut_mult: float = 1.0,
    entry_bar: str = "next_worse",
) -> pd.DataFrame:
    """Enter on the first bar inside the final `window_days` before end_date
    where the favorite condition holds; hold to resolution."""
    m = _prep(markets)
    m = m[m["volume"] >= min_volume]
    settle_map = settle.set_index("market_id")["settle_t"].to_dict()
    end_map = dict(zip(m["market_id"], m["end_t"]))
    recs = m.to_dict("records")
    h_arr = haircut_for_volume(m["volume"].to_numpy(), spread) * haircut_mult

    series = _as_series(prices)
    trades: list[dict] = []
    for row, h in zip(recs, h_arr):
        mid = row["market_id"]
        if mid not in series:
            continue
        t_arr, p_arr = series[mid]
        end_t, closed_t = row["end_t"], row["closed_t"]
        lo_t = end_t - window_days * 86400
        hard_stop = min(end_t, closed_t) if np.isfinite(closed_t) else end_t
        first_t = t_arr[0]
        for i in range(len(t_arr)):
            t, p = t_arr[i], p_arr[i]
            if t < lo_t or t >= hard_stop:
                continue
            if t - first_t < 86400:  # market must have a day of trading behind it
                continue
            if not (0.005 < p < 0.995):
                continue
            if p >= theta and side_mode in ("yes", "both"):
                side, buy_yes = "YES", True
            elif p <= 1 - theta and side_mode in ("no", "both"):
                side, buy_yes = "NO", False
            else:
                continue
            ex = _execution(entry_bar, buy_yes, i, t_arr, p_arr, hard_stop, h)
            if ex is None:
                continue
            fill, entry_t, _ = ex
            outcome = row["outcome"]
            exit_val = outcome if side == "YES" else 1.0 - outcome
            trades.append({
                "market_id": mid, "event_id": row["event_id"],
                "category": row["category"], "side": side,
                "signal_t": entry_t, "fill": float(fill),
                "exit_val": float(exit_val),
                "ret": float(exit_val / fill - 1.0),
                "volume": float(row["volume"]),
            })
            break  # one entry per market
    return _attach_exits(trades, settle_map, end_map)


def momentum_trades(
    prices: pd.DataFrame,
    markets: pd.DataFrame,
    settle: pd.DataFrame,
    spread: dict,
    delta: float,
    lookback_h: float = 24.0,
    band: tuple[float, float] = (0.10, 0.90),
    direction: str = "with",  # "with" = continuation, "against" = mean reversion
    hold_days: float | None = None,  # None = hold to resolution
    min_volume: float = 10_000.0,
    haircut_mult: float = 1.0,
    min_tte_h: float = 24.0,
    entry_bar: str = "next_worse",
    min_age_h: float = 48.0,
    min_prior_bars: int = 4,
) -> pd.DataFrame:
    """After a move of at least `delta` over `lookback_h`, enter in (or
    against) the move's direction. One trade per market. Age guards exclude
    the listing period, where placeholder quotes fabricate 'moves'."""
    m = _prep(markets)
    m = m[m["volume"] >= min_volume]
    settle_map = settle.set_index("market_id")["settle_t"].to_dict()
    end_map = dict(zip(m["market_id"], m["end_t"]))
    recs = m.to_dict("records")
    h_arr = haircut_for_volume(m["volume"].to_numpy(), spread) * haircut_mult
    lb_s = lookback_h * 3600

    series = _as_series(prices)
    trades: list[dict] = []
    for row, h in zip(recs, h_arr):
        mid = row["market_id"]
        if mid not in series:
            continue
        t_arr, p_arr = series[mid]
        end_t, closed_t = row["end_t"], row["closed_t"]
        hard_stop = min(end_t, closed_t) if np.isfinite(closed_t) else end_t
        n = len(t_arr)
        first_t = t_arr[0]
        j = 0
        for i in range(n):
            t, p = t_arr[i], p_arr[i]
            if t >= hard_stop or (end_t - t) < min_tte_h * 3600:
                continue
            if not (band[0] <= p <= band[1]):
                continue
            if t - first_t < min_age_h * 3600 or i < min_prior_bars:
                continue
            # latest bar at least `lookback` old but no older than lookback+24h
            while j < n and t_arr[j] <= t - lb_s:
                j += 1
            k = j - 1
            if k < 0 or (t - lb_s) - t_arr[k] > 86400:
                continue
            move = p - p_arr[k]
            if abs(move) < delta:
                continue
            up = move > 0
            buy_yes = up if direction == "with" else not up
            ex = _execution(entry_bar, buy_yes, i, t_arr, p_arr, hard_stop, h)
            if ex is None:
                continue
            fill, entry_t, entry_i = ex
            side = "YES" if buy_yes else "NO"
            outcome = row["outcome"]
            # exit: resolution, or first bar >= hold horizon (whichever first)
            exit_val, exit_t = None, None
            if hold_days is not None:
                tgt = entry_t + hold_days * 86400
                later = np.flatnonzero((t_arr >= tgt) & (t_arr < hard_stop))
                later = later[later > entry_i] if len(later) else later
                if len(later):
                    ep = p_arr[later[0]]
                    exit_p = max(ep - h, 0.001) if side == "YES" else max((1 - ep) - h, 0.001)
                    exit_val, exit_t = exit_p, float(t_arr[later[0]])
            if exit_val is None:
                exit_val = outcome if side == "YES" else 1.0 - outcome
                exit_t = settle_map.get(mid, end_map.get(mid, entry_t + 86400))
            trades.append({
                "market_id": mid, "event_id": row["event_id"],
                "category": row["category"], "side": side,
                "signal_t": entry_t, "fill": float(fill),
                "exit_val": float(exit_val),
                "ret": float(exit_val / fill - 1.0),
                "volume": float(row["volume"]),
                "exit_t": float(max(exit_t, entry_t + 60.0)),
            })
            break
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades)


def negrisk_sum_series(
    prices: pd.DataFrame,
    markets: pd.DataFrame,
    min_members: int = 3,
    staleness_s: float = 24 * 3600,
) -> pd.DataFrame:
    """For each neg-risk event, the time series of the YES-mid sum across all
    member outcomes on a 12h grid. In a complete mutually-exclusive event the
    fair sum is exactly 1; deviations beyond transaction costs are structural
    arbitrage. Mid staleness makes this an *indicative* measure — execution
    certainty requires live books (the live scanner does that)."""
    m = markets[(markets["event_neg_risk"]) | (markets["neg_risk"])].copy()
    m = m.dropna(subset=["event_id"])
    counts = m.groupby("event_id")["market_id"].nunique()
    events = counts[counts >= min_members].index
    m = m[m["event_id"].isin(events)]
    out_rows = []
    px = prices[prices["market_id"].isin(m["market_id"])]
    by_event = m.groupby("event_id")["market_id"].apply(list).to_dict()
    series = {mid: g[["t", "p"]].to_numpy() for mid, g in px.groupby("market_id", sort=False)}
    for ev, mids in by_event.items():
        arrs = [series.get(mid) for mid in mids]
        if any(a is None or len(a) == 0 for a in arrs):
            continue
        grid = np.unique(np.concatenate([a[:, 0] for a in arrs]))
        grid = grid[(grid >= max(a[0, 0] for a in arrs))]
        if len(grid) == 0:
            continue
        sums = np.zeros(len(grid))
        fresh = np.ones(len(grid), dtype=bool)
        live = np.zeros(len(grid))
        for a in arrs:
            idx = np.searchsorted(a[:, 0], grid, side="right") - 1
            ok = idx >= 0
            age = grid - a[np.clip(idx, 0, None), 0]
            ok &= age <= staleness_s
            fresh &= ok
            p = np.where(ok, a[np.clip(idx, 0, None), 1], 0.0)
            sums += p
            live += (p > 0.005) & (p < 0.995)
        ev_vol = float(m[m["event_id"] == ev]["volume"].sum())
        for g_t, s, f, lv in zip(grid, sums, fresh, live):
            if f:
                out_rows.append({
                    "event_id": ev, "t": float(g_t), "n_members": len(mids),
                    "sum_yes": float(s), "n_live": int(lv), "event_volume": ev_vol,
                })
    return pd.DataFrame(out_rows)
