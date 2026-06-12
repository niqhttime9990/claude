#!/usr/bin/env python3
"""Run the base backtest and print a summary (fast path, no validation)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from ctabot import stats as st
from ctabot.backtest import run_strategy
from ctabot.config import PATHS, StrategyConfig
from ctabot.data import load_universe


def main() -> None:
    cfg = StrategyConfig()
    data, meta = load_universe(ROOT / PATHS.raw_dir)
    res = run_strategy(data, meta, cfg)
    net = res.net.loc["1975":]
    s = st.summary(net)
    print(f"{s['start']} -> {s['end']} ({s['years']} years)")
    for k in ("ann_return", "ann_vol", "max_drawdown", "worst_month"):
        print(f"  {k:22s} {s[k]:8.2%}")
    for k in ("sharpe", "sortino", "calmar", "skew_monthly"):
        print(f"  {k:22s} {s[k]:8.2f}")
    print(f"  {'cost drag (trade+roll)':22s} "
          f"{(res.trade_costs.mean() + res.roll_costs.mean()) * 256:8.2%} /yr")
    oos = net.loc[pd.Timestamp(cfg.insample_end):]
    print(f"  {'out-of-sample sharpe':22s} {st.sharpe(oos):8.2f}   (since {cfg.insample_end})")


if __name__ == "__main__":
    main()
