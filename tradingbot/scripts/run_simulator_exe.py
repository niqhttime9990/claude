#!/usr/bin/env python3
"""Entry point for the packaged .exe: live paper-trading by default.

Double-clicking the exe starts live mode with a $10M paper account and
opens the dashboard. A replay of history needs the repo's data/ folder
next to the exe (copy tradingbot/data there), then run:

    ctabot-simulator.exe replay
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulator.server import build, serve


def main() -> None:
    mode = "replay" if (len(sys.argv) > 1 and sys.argv[1] == "replay") else "live"
    capital = float(sys.argv[2]) if len(sys.argv) > 2 else 10_000_000
    print(f"ctabot simulator — {mode} mode, ${capital:,.0f} paper account")
    if mode == "live":
        print("fetching live data from Yahoo Finance (first load ~30s)...")
    controller = build(mode, "base", capital,
                       state_path="ctabot_sim_state.json" if mode == "live" else None)
    if mode == "live":
        import atexit
        atexit.register(lambda: controller.account.save("ctabot_sim_state.json"))
    serve(controller, port=8765, live_poll_seconds=60.0, open_browser=True)


if __name__ == "__main__":
    main()
