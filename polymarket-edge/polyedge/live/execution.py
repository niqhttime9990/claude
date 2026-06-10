"""Order execution backends.

PaperExecutor simulates marketable-limit fills against live order books and
settles positions when markets resolve — the default and the recommended
first month of any deployment. LiveExecutor wraps py-clob-client and only
activates with explicit opt-in (--live plus env credentials).

State is a JSON file: cash, positions {token -> {shares, cost, market_id,
event_id}}, realized trades log. Equity marks positions at best bid.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .gateway import Book, Gateway


@dataclass
class OrderIntent:
    strategy: str
    market_id: str
    event_id: str | None
    token_id: str
    side: str            # only BUY is used; selling = buying the complement
    limit_price: float
    usd: float
    edge: float          # model edge per $1 at the limit price
    reason: str
    all_or_none_group: str | None = None  # neg-risk baskets fill atomically


class PaperExecutor:
    def __init__(self, state_path: str | Path, start_cash: float = 1000.0):
        self.path = Path(state_path)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"cash": start_cash, "start_equity": start_cash,
                          "positions": {}, "log": []}
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        tmp.replace(self.path)

    # ----- portfolio introspection -------------------------------------
    def equity(self, marks: dict[str, float] | None = None) -> float:
        eq = self.state["cash"]
        for tid, pos in self.state["positions"].items():
            mark = (marks or {}).get(tid)
            eq += pos["shares"] * (mark if mark is not None else pos["avg_price"])
        return eq

    def exposures(self) -> tuple[float, dict[str, float], dict[str, float]]:
        gross, by_mkt, by_ev = 0.0, {}, {}
        for pos in self.state["positions"].values():
            usd = pos["shares"] * pos["avg_price"]
            gross += usd
            by_mkt[pos["market_id"]] = by_mkt.get(pos["market_id"], 0.0) + usd
            ev = pos.get("event_id")
            if ev:
                by_ev[ev] = by_ev.get(ev, 0.0) + usd
        return gross, by_mkt, by_ev

    # ----- trading -------------------------------------------------------
    def execute_batch(self, intents: list[OrderIntent], books: dict[str, Book]) -> list[dict]:
        """Fill marketable-limit buys against book asks up to the limit price.
        Groups marked all_or_none fill only if every leg can fully fill."""
        results = []
        groups: dict[str | None, list[OrderIntent]] = {}
        for it in intents:
            groups.setdefault(it.all_or_none_group, []).append(it)
        for gid, legs in groups.items():
            if gid is not None:
                # atomicity needs depth AND cash for the whole basket up front
                fills = [self._plan_fill(it, books.get(it.token_id)) for it in legs]
                group_cost = sum(it.usd for it in legs)
                if any(f is None for f in fills) or group_cost > self.state["cash"]:
                    results.extend({"intent": it.__dict__, "status": "aon_unfillable"}
                                   for it in legs)
                    continue
            for it in legs:
                results.append(self._fill(it, books.get(it.token_id)))
        self._save()
        return results

    def record_external_fill(self, it: OrderIntent) -> None:
        """Shadow-book an order submitted through another executor (live mode)
        so exposures and the risk gate keep binding. Conservatively assumes
        the submitted order fills completely at its limit price."""
        shares = it.usd / max(it.limit_price, 0.001)
        self.state["cash"] -= it.usd
        pos = self.state["positions"].setdefault(it.token_id, {
            "shares": 0.0, "avg_price": 0.0, "market_id": it.market_id,
            "event_id": it.event_id, "strategy": it.strategy,
        })
        tot_cost = pos["shares"] * pos["avg_price"] + it.usd
        pos["shares"] += shares
        pos["avg_price"] = tot_cost / pos["shares"]
        self.state["log"].append({"ts": time.time(), "type": "shadow_fill",
                                  "intent": it.__dict__})
        self._save()

    def _plan_fill(self, it: OrderIntent, book: Book | None):
        if book is None or not book.asks:
            return None
        # only levels at or below limit are takeable
        usable = [l for l in book.asks if l.price <= it.limit_price + 1e-9]
        depth_usd = sum(l.price * l.size for l in usable)
        if depth_usd + 1e-9 < it.usd:
            return None
        spend, shares = it.usd, 0.0
        for l in usable:
            take = min(spend, l.price * l.size)
            shares += take / l.price
            spend -= take
            if spend <= 1e-9:
                break
        return (it.usd / shares, shares)

    def _fill(self, it: OrderIntent, book: Book | None) -> dict:
        plan = self._plan_fill(it, book)
        if plan is None:
            return {"intent": it.__dict__, "status": "unfilled"}
        avg, shares = plan
        if it.usd > self.state["cash"]:
            return {"intent": it.__dict__, "status": "insufficient_cash"}
        self.state["cash"] -= it.usd
        pos = self.state["positions"].setdefault(it.token_id, {
            "shares": 0.0, "avg_price": 0.0, "market_id": it.market_id,
            "event_id": it.event_id, "strategy": it.strategy,
        })
        tot_cost = pos["shares"] * pos["avg_price"] + it.usd
        pos["shares"] += shares
        pos["avg_price"] = tot_cost / pos["shares"]
        rec = {"ts": time.time(), "intent": it.__dict__, "status": "filled",
               "avg_price": avg, "shares": shares}
        self.state["log"].append(rec)
        return rec

    def settle(self, token_outcomes: dict[str, float]) -> list[dict]:
        """Pay out resolved positions: shares * outcome (1 or 0)."""
        events = []
        for tid, outcome in token_outcomes.items():
            pos = self.state["positions"].pop(tid, None)
            if pos is None:
                continue
            payout = pos["shares"] * outcome
            self.state["cash"] += payout
            ev = {"ts": time.time(), "type": "settlement", "token_id": tid,
                  "shares": pos["shares"], "outcome": outcome, "payout": payout,
                  "cost": pos["shares"] * pos["avg_price"], "strategy": pos.get("strategy")}
            self.state["log"].append(ev)
            events.append(ev)
        if events:
            self._save()
        return events


class LiveExecutor:
    """Real orders via py-clob-client. Requires:
      POLY_PRIVATE_KEY   (Polygon key holding USDC, or proxy-funder setup)
      POLY_FUNDER        (optional proxy wallet address)
      POLY_SIGNATURE_TYPE(optional, default 0)
    Orders are GTC marketable limits; neg-risk baskets use FOK legs.
    """

    def __init__(self) -> None:
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import OrderArgs, OrderType  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "py-clob-client not installed; pip install -r requirements-live.txt"
            ) from e
        key = os.environ.get("POLY_PRIVATE_KEY")
        if not key:
            raise RuntimeError("POLY_PRIVATE_KEY not set")
        kwargs = {"key": key, "chain_id": 137}
        if os.environ.get("POLY_FUNDER"):
            kwargs["funder"] = os.environ["POLY_FUNDER"]
            kwargs["signature_type"] = int(os.environ.get("POLY_SIGNATURE_TYPE", "1"))
        self._client = ClobClient("https://clob.polymarket.com", **kwargs)
        self._client.set_api_creds(self._client.create_or_derive_api_creds())

    def execute_batch(self, intents: list[OrderIntent], books) -> list[dict]:
        from py_clob_client.clob_types import OrderArgs, OrderType

        results = []
        for it in intents:
            shares = round(it.usd / it.limit_price, 2)
            order = self._client.create_order(OrderArgs(
                price=round(it.limit_price, 3), size=shares,
                side="BUY", token_id=it.token_id,
            ))
            otype = OrderType.FOK if it.all_or_none_group else OrderType.GTC
            try:
                resp = self._client.post_order(order, otype)
                results.append({"intent": it.__dict__, "status": "submitted",
                                "response": resp})
            except Exception as e:  # noqa: BLE001
                results.append({"intent": it.__dict__, "status": "error",
                                "error": repr(e)})
        return results
