"""Read-only access to live Polymarket endpoints (no keys required).

Used by the live strategies for signals and by the paper executor for fills.
Network egress to these hosts is required at runtime (run the bot somewhere
with open internet; the research environment may be sandboxed)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


@dataclass
class BookLevel:
    price: float
    size: float


@dataclass
class Book:
    token_id: str
    bids: list[BookLevel]  # sorted best (highest) first
    asks: list[BookLevel]  # sorted best (lowest) first
    ts: float

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    def buy_cost(self, usd: float) -> tuple[float, float] | None:
        """(avg_price, shares) to buy `usd` notional walking the asks."""
        remaining, shares = usd, 0.0
        for lvl in self.asks:
            lvl_usd = lvl.price * lvl.size
            take = min(remaining, lvl_usd)
            shares += take / lvl.price
            remaining -= take
            if remaining <= 1e-9:
                return (usd / shares, shares)
        return None  # not enough depth


def parse_json_field(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class Gateway:
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "polyedge-bot/0.1"},
            limits=httpx.Limits(max_connections=16),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict | None = None, tries: int = 4):
        for attempt in range(tries):
            try:
                r = await self._client.get(url, params=params)
                if r.status_code in (429,) or r.status_code >= 500:
                    raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except Exception:
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(1.5**attempt)

    async def active_markets(self, limit: int = 1000, order: str = "volume24hr") -> list[dict]:
        out = []
        for offset in range(0, limit, 500):
            page = await self._get(
                f"{GAMMA}/markets",
                {"active": "true", "closed": "false", "limit": min(500, limit - offset),
                 "offset": offset, "order": order, "ascending": "false"},
            )
            if not page:
                break
            out.extend(page)
        return out

    async def negrisk_events(self, limit: int = 300) -> list[dict]:
        out = []
        for offset in range(0, limit, 100):
            page = await self._get(
                f"{GAMMA}/events",
                {"active": "true", "closed": "false", "limit": min(100, limit - offset),
                 "offset": offset, "order": "volume24hr", "ascending": "false"},
            )
            if not page:
                break
            out.extend([e for e in page if e.get("negRisk")])
        return out

    async def market(self, market_id: str) -> dict:
        return await self._get(f"{GAMMA}/markets/{market_id}")

    async def book(self, token_id: str) -> Book | None:
        data = await self._get(f"{CLOB}/book", {"token_id": token_id})
        if not isinstance(data, dict):
            return None

        def side(key: str, reverse: bool) -> list[BookLevel]:
            lv = []
            for x in data.get(key) or []:
                try:
                    lv.append(BookLevel(float(x["price"]), float(x["size"])))
                except (KeyError, TypeError, ValueError):
                    continue
            return sorted(lv, key=lambda l: l.price, reverse=reverse)

        return Book(token_id=token_id, bids=side("bids", True),
                    asks=side("asks", False), ts=time.time())

    async def books(self, token_ids: list[str], concurrency: int = 8) -> dict[str, Book]:
        sem = asyncio.Semaphore(concurrency)
        out: dict[str, Book] = {}

        async def one(tid: str) -> None:
            async with sem:
                try:
                    b = await self.book(tid)
                except Exception:
                    return
            if b is not None:
                out[tid] = b

        await asyncio.gather(*[one(t) for t in token_ids])
        return out
