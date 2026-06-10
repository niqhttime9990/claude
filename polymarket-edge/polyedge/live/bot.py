"""The trading loop: scan -> risk gate -> execute -> settle -> log.

Paper mode is the default everywhere. Live mode requires explicit opt-in
and credentials, and starts with the same conservative RiskLimits.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .execution import LiveExecutor, OrderIntent, PaperExecutor
from .gateway import Gateway, parse_json_field
from .risk import PortfolioView, RiskLimits, RiskManager
from .strategies import favorite_scan, load_params, negrisk_scan


def jlog(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record["ts_iso"] = datetime.now(timezone.utc).isoformat()
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


class Bot:
    def __init__(
        self,
        params_path: str,
        state_dir: str = "state",
        live: bool = False,
        stake_usd: float = 25.0,
        limits: RiskLimits | None = None,
    ):
        self.params = load_params(params_path)
        self.gw = Gateway()
        self.live = live
        self.stake_usd = stake_usd
        self.state_dir = Path(state_dir)
        # In live mode the paper executor doubles as the shadow book that
        # exposures, settlement, and the drawdown kill switch read from
        # (live submissions are recorded into it as assumed fills).
        self.paper = PaperExecutor(self.state_dir / "paper_state.json")
        self.executor = LiveExecutor() if live else self.paper
        self.risk = RiskManager(limits or RiskLimits())
        self.log_path = self.state_dir / "bot_log.jsonl"

    # ------------------------------------------------------------------
    async def scan(self) -> list[OrderIntent]:
        held = set(self.paper.state["positions"].keys())
        intents: list[OrderIntent] = []
        for coro in (
            favorite_scan(self.gw, self.params, held, self.stake_usd),
            negrisk_scan(self.gw, self.params),
        ):
            try:
                intents.extend(await coro)
            except Exception as e:  # noqa: BLE001 - a failed scan must not kill the loop
                jlog(self.log_path, {"type": "scan_error", "error": repr(e)})
        return intents

    def gate(self, intents: list[OrderIntent]) -> list[OrderIntent]:
        gross, by_mkt, by_ev = self.paper.exposures()
        view = PortfolioView(
            equity=self.paper.equity(),
            start_equity=self.paper.state.get("start_equity", 0.0),
            gross_exposure=gross,
            market_exposure=by_mkt,
            event_exposure=by_ev,
        )
        self.risk.check_portfolio(view)
        approved = []

        def reserve(it: OrderIntent) -> None:
            # approved-but-unfilled orders must count against the caps, or a
            # batch of N orders each passes while collectively busting them
            view.gross_exposure += it.usd
            view.market_exposure[it.market_id] = (
                view.market_exposure.get(it.market_id, 0.0) + it.usd)
            if it.event_id:
                view.event_exposure[it.event_id] = (
                    view.event_exposure.get(it.event_id, 0.0) + it.usd)

        def release(it: OrderIntent) -> None:
            view.gross_exposure -= it.usd
            view.market_exposure[it.market_id] -= it.usd
            if it.event_id:
                view.event_exposure[it.event_id] -= it.usd

        # All-or-none groups: approve only complete groups.
        groups: dict[str | None, list[OrderIntent]] = {}
        for it in intents:
            groups.setdefault(it.all_or_none_group, []).append(it)
        for gid, legs in groups.items():
            verdicts = []
            for it in legs:
                ok, why = self.risk.approve(
                    market_id=it.market_id, event_id=it.event_id,
                    price=it.limit_price, usd=it.usd, spread=None,
                    edge=it.edge, view=view,
                )
                if ok:
                    reserve(it)
                verdicts.append((it, ok, why))
                jlog(self.log_path, {"type": "risk", "ok": ok, "why": why,
                                     "intent": it.__dict__})
            if gid is None:
                approved.extend(it for it, ok, _ in verdicts if ok)
            elif all(ok for _, ok, _ in verdicts):
                approved.extend(legs)
            else:
                for it, ok, _ in verdicts:  # roll back partial group reservations
                    if ok:
                        release(it)
        return approved

    async def execute(self, intents: list[OrderIntent]) -> None:
        if not intents:
            return
        books = await self.gw.books(list({it.token_id for it in intents}))
        results = self.executor.execute_batch(intents, books)
        if self.live:
            # shadow-book live submissions so exposures/risk caps keep binding
            by_token = {it.token_id: it for it in intents}
            for r in results:
                if r.get("status") == "submitted":
                    it = by_token.get(r["intent"]["token_id"])
                    if it is not None:
                        self.paper.record_external_fill(it)
        for r in results:
            jlog(self.log_path, {"type": "execution", **r})

    async def settle_paper(self) -> None:
        """Resolve paper positions whose markets have closed."""
        positions = self.paper.state["positions"]
        if not positions:
            return
        token_outcomes: dict[str, float] = {}
        for tid, pos in list(positions.items()):
            try:
                m = await self.gw.market(pos["market_id"])
            except Exception:
                continue
            if not m.get("closed"):
                continue
            prices = parse_json_field(m.get("outcomePrices"))
            tokens = parse_json_field(m.get("clobTokenIds"))
            if len(prices) != 2 or len(tokens) != 2:
                continue
            try:
                y = float(prices[0])
            except (TypeError, ValueError):
                continue
            outcome_by_token = {str(tokens[0]): y, str(tokens[1]): 1.0 - y}
            if tid in outcome_by_token:
                token_outcomes[tid] = outcome_by_token[tid]
        for ev in self.paper.settle(token_outcomes):
            jlog(self.log_path, {"type": "settlement", **ev})

    # ------------------------------------------------------------------
    async def run_once(self) -> dict:
        await self.settle_paper()
        intents = await self.scan()
        approved = self.gate(intents)
        await self.execute(approved)
        eq = self.paper.equity()
        status = {
            "type": "heartbeat", "equity": eq,
            "cash": self.paper.state["cash"],
            "n_positions": len(self.paper.state["positions"]),
            "intents": len(intents), "approved": len(approved),
            "halted": self.risk.halted,
        }
        jlog(self.log_path, status)
        return status

    async def run(self, poll_s: float = 120.0) -> None:
        print(f"polyedge bot starting (live={self.live}); params strategies: "
              f"{[k for k, v in self.params.items() if isinstance(v, dict) and v.get('enabled')]}")
        try:
            while True:
                t0 = time.monotonic()
                status = await self.run_once()
                print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {status}")
                if self.risk.halted:
                    print(f"RISK HALT: {self.risk.halt_reason}")
                    break
                await asyncio.sleep(max(5.0, poll_s - (time.monotonic() - t0)))
        finally:
            await self.gw.close()
