"""polyedge command line.

  python -m polyedge.cli scan    # one-shot signal scan, prints intents, no orders
  python -m polyedge.cli paper   # paper-trading loop (default state/ dir)
  python -m polyedge.cli live    # real orders; needs env keys + explicit flag
  python -m polyedge.cli status  # print paper portfolio
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .live.bot import Bot
from .live.risk import RiskLimits


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="polyedge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--params", default="reports/params.json")
    common.add_argument("--state-dir", default="state")
    common.add_argument("--stake", type=float, default=25.0)
    common.add_argument("--poll", type=float, default=120.0)

    sub.add_parser("scan", parents=[common])
    sub.add_parser("paper", parents=[common])
    live = sub.add_parser("live", parents=[common])
    live.add_argument("--i-accept-real-money-risk", action="store_true")
    sub.add_parser("status", parents=[common])
    return ap


async def amain() -> int:
    args = build_parser().parse_args()
    if args.cmd == "status":
        p = Path(args.state_dir) / "paper_state.json"
        if not p.exists():
            print("no paper state yet")
            return 0
        state = json.loads(p.read_text())
        print(json.dumps({
            "cash": state["cash"],
            "positions": state["positions"],
            "n_log": len(state["log"]),
        }, indent=2))
        return 0

    live = args.cmd == "live"
    if live and not args.i_accept_real_money_risk:
        print("refusing to trade real money without --i-accept-real-money-risk")
        return 2

    bot = Bot(args.params, state_dir=args.state_dir, live=live,
              stake_usd=args.stake, limits=RiskLimits())
    if args.cmd == "scan":
        intents = await bot.scan()
        for it in intents:
            print(json.dumps(it.__dict__, default=str))
        print(f"{len(intents)} intents (no orders placed)")
        await bot.gw.close()
        return 0
    await bot.run(poll_s=args.poll)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
