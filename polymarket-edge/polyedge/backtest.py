"""Trade-level backtest accounting.

The unit of record is a trade: $1 of notional spent at `fill`, returning
`exit_val` per share at `exit_t`. Returns are per-dollar-staked, so a
portfolio equity curve under equal stakes is the cumulative sum of `ret`.

All inference clusters by event: same-event trades (sibling outcomes,
correlated sports markets) resolve together and are not independent draws.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .stats import cluster_bootstrap_mean, event_clusters, max_drawdown, weekly_performance

EMPTY_EVAL_KEYS = (
    "n_events", "mean_ret", "ci_lo", "ci_hi", "p_le0", "hit_rate",
    "total_pnl_per_$1_stakes", "max_concurrent_stakes", "ann_ret_on_capital",
    "sharpe_ann_weekly", "n_weeks", "max_drawdown_$", "median_market_volume",
    "span_days",
)

TRADE_COLS = [
    "market_id", "event_id", "category", "side", "signal_t", "fill",
    "exit_t", "exit_val", "ret", "volume",
]


def dedupe_per_event(trades: pd.DataFrame, max_per_event: int = 2) -> pd.DataFrame:
    """Cap trades per event, keeping the most liquid markets. Without this,
    one 20-candidate neg-risk event contributes 20 correlated 'independent'
    trades and quietly dominates the stats."""
    if trades.empty:
        return trades
    t = trades.copy()
    t["_ev"] = t["event_id"].fillna("mkt:" + t["market_id"].astype(str))
    t = t.sort_values("volume", ascending=False)
    t = t.groupby("_ev", sort=False).head(max_per_event)
    return t.drop(columns="_ev").sort_values("signal_t").reset_index(drop=True)


def max_concurrency(trades: pd.DataFrame) -> int:
    """Peak number of simultaneously open $1 stakes = capital requirement."""
    if trades.empty:
        return 0
    events = []
    for _, r in trades.iterrows():
        events.append((r["signal_t"], 1))
        events.append((max(r["exit_t"], r["signal_t"] + 1), -1))
    events.sort()
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    return peak


def evaluate(trades: pd.DataFrame, label: str = "", n_boot: int = 4000) -> dict:
    """Full evaluation of a trade set. Returns a flat dict for tabulation."""
    if trades.empty:
        # full schema so consumers never KeyError on an empty cell
        return {"label": label, "n_trades": 0,
                **{k: np.nan for k in EMPTY_EVAL_KEYS}}
    t = trades.copy()
    clusters = event_clusters(t)
    boot = cluster_bootstrap_mean(t["ret"].to_numpy(), clusters, n_boot=n_boot)
    pnl = pd.Series(t["ret"].to_numpy(),
                    index=pd.to_datetime(t["exit_t"].to_numpy(), unit="s")).sort_index()
    wk = weekly_performance(pnl)
    equity = pnl.cumsum()
    cap = max_concurrency(t)
    total_pnl = float(t["ret"].sum())
    span_days = max(1.0, (t["exit_t"].max() - t["signal_t"].min()) / 86400)
    ret_on_capital_ann = (total_pnl / max(cap, 1)) * (365.0 / span_days)
    return {
        "label": label,
        "n_trades": int(len(t)),
        "n_events": int(pd.unique(clusters).size),
        "mean_ret": boot["mean"],
        "ci_lo": boot["lo"],
        "ci_hi": boot["hi"],
        "p_le0": boot["p_value_le0"],
        "hit_rate": float((t["ret"] > 0).mean()),
        "total_pnl_per_$1_stakes": total_pnl,
        "max_concurrent_stakes": cap,
        "ann_ret_on_capital": float(ret_on_capital_ann),
        "sharpe_ann_weekly": wk["sharpe_ann"],
        "n_weeks": wk["n_weeks"],
        "max_drawdown_$": max_drawdown(equity),
        "median_market_volume": float(t["volume"].median()),
        "span_days": float(span_days),
    }


def split_by_date(trades: pd.DataFrame, cutoff: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train/test split on signal time (out-of-sample = signals after cutoff)."""
    cut = pd.Timestamp(cutoff).timestamp()
    return trades[trades["signal_t"] < cut], trades[trades["signal_t"] >= cut]


def walk_forward(
    candidates_by_cell: dict[str, pd.DataFrame],
    cutoff: str,
    min_train_trades: int = 150,
    max_per_event: int = 2,
) -> dict:
    """Choose the grid cell with the best conservative train score (bootstrap
    CI lower bound), then report that single frozen cell out-of-sample.

    Returns the train table for all cells (full disclosure), the chosen cell,
    and its OOS evaluation. Headline numbers must come from `test_eval`.
    """
    train_rows, evals = [], {}
    for cell, trades in candidates_by_cell.items():
        tr, te = split_by_date(trades, cutoff)
        tr = dedupe_per_event(tr, max_per_event)
        te = dedupe_per_event(te, max_per_event)
        ev = evaluate(tr, label=cell)
        ev["cell"] = cell
        train_rows.append(ev)
        evals[cell] = (tr, te)
    train_table = pd.DataFrame(train_rows)
    ok = train_table[(train_table["n_trades"] >= min_train_trades)]
    if ok.empty or not np.isfinite(ok["ci_lo"]).any():
        return {"train_table": train_table, "chosen": None, "test_eval": None}
    chosen = ok.loc[ok["ci_lo"].idxmax(), "cell"]
    test_eval = evaluate(evals[chosen][1], label=f"{chosen} [OOS]")
    return {
        "train_table": train_table.sort_values("ci_lo", ascending=False),
        "chosen": chosen,
        "test_eval": test_eval,
        "test_trades": evals[chosen][1],
    }
