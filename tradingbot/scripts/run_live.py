#!/usr/bin/env python3
"""Compute today's target book and orders.

Default is a dry run: print targets and the orders that *would* be sent.
With --paper, fills are recorded against a local paper-broker state file.

    python scripts/run_live.py --capital 250000 --eurusd 1.08
    python scripts/run_live.py --capital 250000 --paper --state paper_state.json

For real money you would implement ctabot.live.Broker for your broker and,
far more importantly, replace the pinned research snapshot with a live data
feed (see README, "Going live").
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ctabot.config import PATHS, StrategyConfig
from ctabot.data import load_universe
from ctabot.live import PaperBroker, buffer_in_contracts, compute_targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, required=True, help="account capital in USD")
    ap.add_argument("--eurusd", type=float, default=None, help="EURUSD rate for EUR instruments")
    ap.add_argument("--paper", action="store_true", help="record fills in the paper broker")
    ap.add_argument("--state", default="paper_state.json", help="paper broker state file")
    args = ap.parse_args()

    cfg = StrategyConfig()
    data, meta = load_universe(ROOT / PATHS.raw_dir)
    fx = {"EUR": args.eurusd} if args.eurusd else None
    book = compute_targets(data, meta, args.capital, cfg, fx_to_usd=fx)
    buf = buffer_in_contracts(book, meta, cfg)

    print(f"as of {book.asof} | capital ${book.capital_usd:,.0f}\n")
    table = book.targets.copy()
    table["target_contracts"] = table["target_contracts"].round(1)
    print(table[["forecast", "notional_frac", "price", "target_contracts"]]
          .round(3).to_string())

    broker = PaperBroker(args.state) if args.paper else None
    held = broker.positions() if broker else {}
    orders = book.orders_against(held, buf)

    print(f"\norders ({'paper' if args.paper else 'dry run'}):")
    if not orders:
        print("  none (all positions inside buffer)")
    for o in orders:
        side = "BUY " if o.contracts > 0 else "SELL"
        print(f"  {side} {abs(o.contracts):4d} {o.instrument:9s} "
              f"@~{o.reference_price:>10.2f}  (${abs(o.notional_usd):>12,.0f})  {o.reason}")
    if broker:
        broker.submit(orders, book.asof)
        print(f"\nrecorded {len(orders)} fills -> {args.state}")


if __name__ == "__main__":
    main()
