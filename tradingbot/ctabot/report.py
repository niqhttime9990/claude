"""Figures and the markdown validation report."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})


def fig_equity(curves: dict[str, pd.Series], path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    main = next(iter(curves))
    for label, net in curves.items():
        eq = (1 + net.fillna(0)).cumprod()
        lw = 1.8 if label == main else 1.0
        ax1.plot(eq.index, eq, label=label, linewidth=lw)
    ax1.set_yscale("log")
    ax1.set_title("Cumulative return (log scale), net of costs")
    ax1.legend(loc="upper left", fontsize=9)
    net = curves[main]
    eq = (1 + net.fillna(0)).cumprod()
    dd = eq / eq.cummax() - 1
    ax2.fill_between(dd.index, dd, 0, color="firebrick", alpha=0.6)
    ax2.set_title(f"Drawdown: {main}")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_rolling_sharpe(net: pd.Series, path: Path, window_years: int = 3,
                       days: int = 256) -> None:
    w = window_years * days
    roll = net.rolling(w).mean() / net.rolling(w).std() * np.sqrt(days)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(roll.index, roll, color="navy")
    ax.axhline(0, color="black", linewidth=0.8)
    full = net.mean() / net.std() * np.sqrt(days)
    ax.axhline(full, color="green", linestyle="--", linewidth=0.9,
               label=f"full-sample SR {full:.2f}")
    ax.set_title(f"Rolling {window_years}y Sharpe ratio (net)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_yearly_returns(net: pd.Series, path: Path) -> None:
    yearly = net.groupby(net.index.year).sum()
    fig, ax = plt.subplots(figsize=(11, 4))
    colors = ["seagreen" if v >= 0 else "firebrick" for v in yearly]
    ax.bar(yearly.index.astype(str), yearly * 100, color=colors)
    ax.set_title("Calendar-year net return (%)")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_placebo(placebo: dict, path: Path) -> None:
    nulls = np.array(placebo["null_sharpes"], dtype=float)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(nulls, bins=40, color="steelblue", alpha=0.8,
            label=f"placebo Sharpes (n={placebo['n_reps']})")
    ax.axvline(placebo["real_sharpe"], color="firebrick", linewidth=2,
               label=f"real strategy SR {placebo['real_sharpe']:.2f} "
                     f"(p={placebo['p_value']:.3f})")
    ax.set_title("Null distribution: randomly time-shifted forecasts through the same engine")
    ax.set_xlabel("annualised Sharpe")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_sensitivity(table: pd.DataFrame, base_sr: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, max(4, 0.28 * len(table))))
    ax.scatter(table["sharpe"], range(len(table)), color="navy", zorder=3, s=18)
    ax.axvline(base_sr, color="firebrick", linestyle="--",
               label=f"base config SR {base_sr:.2f}")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(range(len(table)))
    ax.set_yticklabels(table["label"], fontsize=8)
    ax.set_xlabel("net annualised Sharpe (full sample)")
    ax.set_title("Parameter sensitivity: every variation, one dot each")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_attribution(per_class: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for col in per_class.columns:
        ax.plot(per_class.index, per_class[col].cumsum() * 100, label=col)
    ax.set_title("Cumulative net P&L by asset class (% of capital, additive)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_bootstrap(boot_full: dict, boot_oos: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    labels, vals = [], []
    for name, b in [("full sample", boot_full), ("out-of-sample", boot_oos)]:
        labels.append(f"{name}\nSR {b['sharpe']:.2f}")
        vals.append((b["ci_2.5"], b["sharpe"], b["ci_97.5"]))
    for i, (lo, mid, hi) in enumerate(vals):
        ax.plot([lo, hi], [i, i], color="navy", linewidth=3, alpha=0.6)
        ax.plot([mid], [i], "o", color="firebrick", markersize=9)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("annualised Sharpe, 95% block-bootstrap CI")
    ax.set_title("Sharpe confidence intervals (stationary block bootstrap)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def md_table(rows: list[dict], cols: list[str], fmt: dict | None = None) -> str:
    fmt = fmt or {}
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    lines = [head, sep]
    for row in rows:
        cells = []
        for c in cols:
            v = row.get(c, "")
            f = fmt.get(c)
            cells.append(f.format(v) if (f and isinstance(v, (int, float)) and not pd.isna(v)) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
