#!/usr/bin/env python3
"""End-to-end research pipeline: calibration study, strategy walk-forwards,
neg-risk arbitrage scan, report + live-bot parameter export.

Usage:
    python research/run_research.py --data data/ --out reports/ \
        --cutoff 2025-12-01

Outputs:
    reports/REPORT.md, reports/fig_*.png, reports/params.json,
    reports/tables/*.csv (full grids, no cherry-picking)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polyedge.backtest import dedupe_per_event, evaluate, split_by_date, walk_forward
from polyedge.calibration import calibration_table, edge_zones, flb_tests
from polyedge.dataio import (
    build_settlement_table,
    price_series,
    load_active_books,
    load_markets,
    load_prices,
    spread_model,
)
from polyedge.stats import deflated_p_note
from polyedge.strategies import favorite_trades, momentum_trades, negrisk_sum_series

H = 3600.0
DAY = 86400.0


def fig_calibration(binned: pd.DataFrame, horizon_label: str, out: Path) -> None:
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(7, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
    ax.errorbar(
        binned["mean_price"], binned["emp_rate"],
        yerr=[(binned["emp_rate"] - binned["wilson_lo"]).clip(lower=0),
              (binned["wilson_hi"] - binned["emp_rate"]).clip(lower=0)],
        fmt="o", ms=4, capsize=2, label="empirical (95% Wilson)",
    )
    ax.set_ylabel("empirical YES frequency")
    ax.set_title(f"Polymarket calibration, {horizon_label} before resolution")
    ax.legend()
    ax2.bar(binned["mean_price"], binned["n"], width=0.04)
    ax2.set_yscale("log")
    ax2.set_xlabel("price (implied probability)")
    ax2.set_ylabel("n markets")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def fig_equity(trades: pd.DataFrame, title: str, out: Path) -> None:
    if trades.empty:
        return
    pnl = pd.Series(trades["ret"].to_numpy(),
                    index=pd.to_datetime(trades["exit_t"], unit="s")).sort_index()
    eq = pnl.cumsum()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(eq.index, eq.values)
    ax.set_title(title)
    ax.set_ylabel("cumulative P&L per $1 stakes")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--cutoff", default="2025-12-01", help="walk-forward train/test split")
    ap.add_argument("--n-boot", type=int, default=4000)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    report: list[str] = []

    # ------------------------------------------------------------ data
    markets = load_markets(args.data)
    prices = load_prices(args.data, "12h")
    books = load_active_books(args.data)
    active = None
    ap_path = Path(args.data) / "active_markets.parquet"
    if ap_path.exists():
        active = pd.read_parquet(ap_path)
    spread = spread_model(books, active)

    settle = build_settlement_table(markets, prices)
    series = price_series(prices)
    n_res = int(markets["resolved_clean"].sum())
    data_through = pd.to_datetime(prices["t"].max(), unit="s")
    report.append("# Polymarket edge research report\n")
    report.append(
        f"- markets in dataset: **{len(markets):,}** "
        f"(clean binary resolutions: **{n_res:,}**, ties/invalid: "
        f"{int((markets['outcome'] == 0.5).sum()):,}, unparseable: "
        f"{int(markets['outcome'].isna().sum()):,})\n"
        f"- price rows (12h fidelity): **{len(prices):,}** across "
        f"{prices['market_id'].nunique():,} markets\n"
        f"- total lifetime volume covered: **${markets['volume'].sum()/1e9:.2f}B**\n"
        f"- price data through: **{data_through:%Y-%m-%d}**\n"
        f"- walk-forward cutoff (signals before=train, after=test): **{args.cutoff}**\n"
        f"- execution haircut model: `{spread}`\n"
    )

    # ---------------------------------------------------- calibration
    report.append("\n## 1. Calibration / favorite-longshot bias\n")
    report.append(
        "Snapshot = last mid at horizon h before the settle flatline "
        "(see dataio.settle_time). Wilson 95% intervals; FLB regression "
        "`outcome - p ~ a + b(p - 0.5)` with event-cluster-robust errors.\n"
    )
    for h_s, lbl in [(24 * H, "24h"), (72 * H, "72h"), (168 * H, "7d")]:
        snaps, binned = calibration_table(prices, markets, settle, h_s, n_bins=20)
        binned.to_csv(out / "tables" / f"calibration_{lbl}.csv", index=False)
        fig_calibration(binned, lbl, out / f"fig_calibration_{lbl}.png")
        tests = flb_tests(snaps)
        ov = tests["overall"]
        report.append(
            f"**{lbl} before resolution** (n={ov['n']:,}): FLB slope "
            f"b={ov['slope']:.4f} (t={ov['t']:.1f}, p={ov['p']:.2g}) — "
            + ("favorites underpriced (classic FLB). " if ov["slope"] < 0 and ov["p"] < 0.05
               else "no significant favorite-longshot bias. ")
        )
        seg_lines = []
        for k, v in tests.items():
            if k != "overall" and isinstance(v, dict) and v.get("n", 0) >= 300 and np.isfinite(v.get("slope", np.nan)):
                seg_lines.append(f"  - {k}: b={v['slope']:.4f} (p={v['p']:.2g}, n={v['n']:,})")
        if seg_lines:
            report.append("\n" + "\n".join(seg_lines) + "\n")
        zones = edge_zones(snaps, [(0.01, 0.05), (0.05, 0.10), (0.90, 0.95),
                                   (0.95, 0.99), (0.97, 0.99)])
        report.append("\nGross (cost-free) expected returns by zone at "
                      f"{lbl}:\n\n{zones.to_markdown(index=False)}\n")

    # --------------------------------------------- favorite strategy WF
    report.append("\n## 2. Favorite strategy — walk-forward\n")
    report.append(
        "Rule: in the final W days before end_date, first bar with p >= θ "
        "buys YES (p <= 1-θ buys NO) at mid + tiered half-spread; hold to "
        "resolution. Max 2 trades/event; min lifetime volume $10k. Grid "
        "below is fully disclosed; the chosen cell maximizes the train CI "
        "lower bound and is then frozen for OOS.\n"
    )
    fav_cells: dict[str, pd.DataFrame] = {}
    fav_params: dict[str, dict] = {}
    for theta in (0.90, 0.93, 0.95, 0.97):
        for window in (1.0, 3.0, 7.0):
            for side in ("yes", "no", "both"):
                cell = f"fav θ={theta} W={window:g}d {side}"
                fav_params[cell] = {"theta": theta, "window_days": window,
                                    "side_mode": side}
                t = favorite_trades(series, markets, settle, spread,
                                    theta=theta, window_days=window,
                                    side_mode=side)
                fav_cells[cell] = (
                    t if not t.empty else pd.DataFrame(columns=["signal_t"]))
    fav_wf = walk_forward(fav_cells, args.cutoff)
    fav_wf["train_table"].to_csv(out / "tables" / "favorite_train_grid.csv", index=False)
    report.append("\nTrain grid (top 10 by CI lower bound):\n\n"
                  + fav_wf["train_table"].head(10)[
                      ["cell", "n_trades", "mean_ret", "ci_lo", "ci_hi",
                       "p_le0", "hit_rate", "sharpe_ann_weekly"]
                  ].to_markdown(index=False) + "\n")
    fav_ok = False
    if fav_wf["chosen"]:
        ev = fav_wf["test_eval"]
        note = deflated_p_note(len(fav_cells), ev.get("p_le0", np.nan))
        report.append(
            f"\n**Chosen cell:** `{fav_wf['chosen']}` → **out-of-sample**: "
            f"n={ev['n_trades']:,} trades, mean ret/stake "
            f"**{ev['mean_ret']*100:.2f}%** (95% CI [{ev['ci_lo']*100:.2f}%, "
            f"{ev['ci_hi']*100:.2f}%], cluster-bootstrap by event), hit rate "
            f"{ev['hit_rate']:.1%}, weekly Sharpe {ev['sharpe_ann_weekly']:.2f} "
            f"({ev['n_weeks']} wks), max drawdown ${ev['max_drawdown_$']:.1f} "
            f"per $1 stakes, annualized return on peak capital "
            f"{ev['ann_ret_on_capital']*100:.1f}%.\n"
            f"\nMultiple-testing note: {note}\n"
        )
        fig_equity(fav_wf["test_trades"], f"Favorite {fav_wf['chosen']} OOS equity",
                   out / "fig_favorite_equity_oos.png")
        fav_ok = bool(ev["ci_lo"] > 0 and ev["n_trades"] >= 100)
        # cost sensitivity on the chosen cell
        sens = []
        cp = fav_params[fav_wf["chosen"]]
        for mult, lab in [(0.0, "no costs"), (1.0, "1x half-spread"),
                          (2.0, "2x half-spread")]:
            tr = favorite_trades(series, markets, settle, spread,
                                 haircut_mult=mult, **cp)
            _, te = split_by_date(tr, args.cutoff)
            e = evaluate(dedupe_per_event(te), label=lab, n_boot=1500)
            sens.append({"costs": lab, "mean_ret": e.get("mean_ret"),
                         "ci_lo": e.get("ci_lo"), "ci_hi": e.get("ci_hi"),
                         "n": e.get("n_trades")})
        report.append("\nCost sensitivity (OOS, chosen cell):\n\n"
                      + pd.DataFrame(sens).to_markdown(index=False) + "\n")
        # per-quarter stability over the whole sample (train + OOS)
        all_chosen = dedupe_per_event(fav_cells[fav_wf["chosen"]])
        if not all_chosen.empty:
            q = pd.to_datetime(all_chosen["signal_t"], unit="s").dt.to_period("Q")
            rows = []
            for per, g in all_chosen.groupby(q):
                e = evaluate(g, n_boot=800)
                rows.append({"quarter": str(per), "n": e["n_trades"],
                             "mean_ret": round(e["mean_ret"], 4),
                             "ci_lo": round(e["ci_lo"], 4),
                             "ci_hi": round(e["ci_hi"], 4),
                             "oos": str(per.start_time >= pd.Timestamp(args.cutoff))})
            report.append("\nPer-quarter stability of the chosen cell "
                          "(quarters after the cutoff are out-of-sample):\n\n"
                          + pd.DataFrame(rows).to_markdown(index=False) + "\n")

    # --------------------------------------------- momentum strategy WF
    report.append("\n## 3. Momentum / underreaction — walk-forward\n")
    report.append(
        "Rule: |Δp| >= δ over 24h, price in [0.10, 0.90], enter at signal "
        "bar with the move ('with') or against it ('against'); hold to "
        "resolution or time-exit. One trade per market.\n"
    )
    mom_cells: dict[str, pd.DataFrame] = {}
    for delta in (0.05, 0.10, 0.15):
        for direction in ("with", "against"):
            for hold, hl in ((None, "res"), (3.0, "3d"), (7.0, "7d")):
                t = momentum_trades(series, markets, settle, spread,
                                    delta=delta, direction=direction,
                                    hold_days=hold)
                mom_cells[f"mom δ={delta} {direction} hold={hl}"] = (
                    t if not t.empty else pd.DataFrame(columns=["signal_t"]))
    mom_wf = walk_forward(mom_cells, args.cutoff)
    mom_wf["train_table"].to_csv(out / "tables" / "momentum_train_grid.csv", index=False)
    report.append("\nTrain grid (top 10 by CI lower bound):\n\n"
                  + mom_wf["train_table"].head(10)[
                      ["cell", "n_trades", "mean_ret", "ci_lo", "ci_hi",
                       "p_le0", "hit_rate", "sharpe_ann_weekly"]
                  ].to_markdown(index=False) + "\n")
    mom_ok = False
    if mom_wf["chosen"]:
        ev = mom_wf["test_eval"]
        note = deflated_p_note(len(mom_cells), ev.get("p_le0", np.nan))
        report.append(
            f"\n**Chosen cell:** `{mom_wf['chosen']}` → **out-of-sample**: "
            f"n={ev['n_trades']:,}, mean ret/stake **{ev['mean_ret']*100:.2f}%** "
            f"(95% CI [{ev['ci_lo']*100:.2f}%, {ev['ci_hi']*100:.2f}%]), hit "
            f"rate {ev['hit_rate']:.1%}, weekly Sharpe "
            f"{ev['sharpe_ann_weekly']:.2f}.\n\nMultiple-testing note: {note}\n"
        )
        fig_equity(mom_wf["test_trades"], f"Momentum {mom_wf['chosen']} OOS equity",
                   out / "fig_momentum_equity_oos.png")
        mom_ok = bool(ev["ci_lo"] > 0 and ev["n_trades"] >= 100)

    # --------------------------------------------- neg-risk arbitrage
    report.append("\n## 4. Neg-risk structural arbitrage (indicative)\n")
    nr = negrisk_sum_series(prices, markets)
    if not nr.empty:
        nr.to_parquet(out / "tables" / "negrisk_sums.parquet", index=False)
        # conservative cost: half-spread per leg on the relevant side
        h_leg = float(np.median(spread["half_spread"]))
        nr["arb_no"] = nr["sum_yes"] - 1.0 - nr["n_members"] * h_leg  # $ per set
        nr["arb_yes"] = 1.0 - nr["sum_yes"] - nr["n_members"] * h_leg
        opp = nr[(nr["arb_no"] > 0.01) | (nr["arb_yes"] > 0.01)]
        ev_opp = opp.groupby("event_id").agg(
            max_edge=("arb_no", "max"), n_snaps=("t", "count"),
            volume=("event_volume", "first"), members=("n_members", "first"))
        report.append(
            f"Events analyzed: {nr['event_id'].nunique():,}; grid snapshots: "
            f"{len(nr):,}. Snapshots with sum-of-YES mispricing beyond "
            f"per-leg half-spreads (> $0.01/set): **{len(opp):,}** "
            f"({len(opp)/max(len(nr),1):.2%}) across "
            f"**{opp['event_id'].nunique():,} events**.\n\n"
            "These are *mid-based and staleness-filtered but execution-"
            "unverified* — treat as an upper bound on frequency and use the "
            "live scanner (FOK basket orders) to harvest. Top events:\n\n"
            + ev_opp.sort_values("max_edge", ascending=False).head(10)
                    .to_markdown() + "\n"
        )
        fig, ax = plt.subplots(figsize=(7, 4))
        dev = (nr["sum_yes"] - 1.0).clip(-0.25, 0.25)
        ax.hist(dev, bins=100)
        ax.set_yscale("log")
        ax.set_xlabel("sum(YES mids) - 1 across neg-risk event")
        ax.set_title("Neg-risk sum deviations (12h grid, fresh mids only)")
        fig.tight_layout()
        fig.savefig(out / "fig_negrisk_dev.png", dpi=150)
        plt.close(fig)
    else:
        report.append("No complete neg-risk events with full member coverage.\n")

    # --------------------------------------------- params for the bot
    params: dict = {"generated_utc": pd.Timestamp.now("UTC").isoformat(),
                    "train_cutoff": args.cutoff,
                    "data_through": str(data_through)}
    if fav_ok and fav_wf["chosen"]:
        cp = fav_params[fav_wf["chosen"]]
        params["favorite"] = {
            "enabled": True,
            "theta": cp["theta"],
            "window_days": cp["window_days"],
            "side_mode": cp["side_mode"],
            "min_volume": 10000.0,
            "expected_ret": float(fav_wf["test_eval"]["mean_ret"]),
            "oos_ci": [float(fav_wf["test_eval"]["ci_lo"]),
                       float(fav_wf["test_eval"]["ci_hi"])],
        }
    else:
        params["favorite"] = {"enabled": False,
                              "why": "no cell with OOS CI low > 0 and n>=100"}
    if mom_ok and mom_wf["chosen"]:
        params["momentum_note"] = {
            "oos_validated_cell": mom_wf["chosen"],
            "oos_mean_ret": float(mom_wf["test_eval"]["mean_ret"]),
            "note": "12h-fidelity signal; live impl needs finer data — not armed",
        }
    params["negrisk"] = {"enabled": True, "min_edge_per_set": 0.02,
                         "max_members": 25,
                         "rationale": "structural; deterministic payout if basket fills"}
    (out / "params.json").write_text(json.dumps(params, indent=2))

    report.append("\n## 5. Verdict & caveats\n")
    report.append(
        f"- favorite strategy OOS-validated: **{fav_ok}**\n"
        f"- momentum OOS-validated: **{mom_ok}** (not armed in live bot at "
        "12h fidelity regardless)\n"
        "- neg-risk arbitrage: structural, always-on in live scanner with "
        "FOK baskets\n\n"
        "Caveats: mid-price fills modeled with tiered half-spread haircuts "
        "(see cost sensitivity); lifetime volume used as liquidity filter "
        "(mild survivorship in favor of liquid markets); 12h price grid "
        "understates path risk for time-exits; resolution timestamps from "
        "price flatline detection; market microstructure (queue, partial "
        "fills) not modeled — stakes assumed small vs depth.\n"
    )
    (out / "REPORT.md").write_text("\n".join(report))
    print(f"report written to {out/'REPORT.md'}")
    print(json.dumps(params, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
