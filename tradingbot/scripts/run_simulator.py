#!/usr/bin/env python3
"""ctabot paper-trading simulator.

Replay 40+ years of history at adjustable speed, or paper-trade the live
market (delayed Yahoo quotes), with a $10M default account and a local web
dashboard. No real orders are ever sent.

    python scripts/run_simulator.py                          # replay since 1982
    python scripts/run_simulator.py --start 2018-01-01       # replay recent years
    python scripts/run_simulator.py --preset stacked         # S&P + overlay
    python scripts/run_simulator.py --mode live              # real-time paper trading
    python scripts/run_simulator.py --mode live --capital 50000000

Live mode needs internet access (Yahoo Finance) and persists the account in
ctabot_sim_state.json so you can stop/restart across days.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ctabot.config import PRESETS
from simulator.server import build, serve


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="base")
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--start", default="1982-01-01", help="replay start date")
    ap.add_argument("--end", default=None, help="replay end date")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--poll", type=float, default=60.0, help="live poll seconds")
    ap.add_argument("--state", default="ctabot_sim_state.json",
                    help="live-mode account persistence file")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    controller = build(args.mode, args.preset, args.capital,
                       start=args.start, end=args.end,
                       state_path=args.state if args.mode == "live" else None)
    if args.mode == "live":
        import atexit
        atexit.register(lambda: controller.account.save(args.state))
    serve(controller, port=args.port, live_poll_seconds=args.poll,
          open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
