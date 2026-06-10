#!/usr/bin/env python3
"""Fetch Polymarket historical data (Gamma metadata + CLOB price histories).

Designed to run on a GitHub Actions runner (or any machine with open egress).
Writes parquet shards + a MANIFEST.json into --out. Defensive by design:
every network call retries with backoff, partial results are always saved,
and the process exits 0 with error details in the manifest unless nothing
at all could be fetched.

Data fetched:
  1. Resolved (closed) binary markets from Gamma, volume-filtered.
  2. Sibling completion for neg-risk events (so multi-outcome events are whole).
  3. 12h-fidelity full-lifetime price history for every market's YES token.
  4. 1h-fidelity history for the top markets (works only if the API still
     serves sub-12h granularity for resolved markets; auto-detected).
  5. Snapshot of active markets + their live order books (for spread/depth
     calibration of backtest haircuts).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

UA = {"User-Agent": "polyedge-research/0.1 (academic backtesting; contact in repo)"}


# ----------------------------------------------------------------------------
# Adaptive rate limiter (AIMD): halve rate on 429, slowly recover.
# ----------------------------------------------------------------------------
class Pacer:
    def __init__(self, rps: float, floor: float = 3.0, ceiling: float = 30.0):
        self.rate = rps
        self.floor = floor
        self.ceiling = ceiling
        self._next_ok = 0.0
        self._lock = asyncio.Lock()
        self._clean = 0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_ok - now)
            self._next_ok = max(now, self._next_ok) + 1.0 / self.rate
        if delay > 0:
            await asyncio.sleep(delay)

    def punish(self) -> None:
        self.rate = max(self.floor, self.rate / 2.0)
        self._clean = 0

    def reward(self) -> None:
        self._clean += 1
        if self._clean >= 100:
            self.rate = min(self.ceiling, self.rate + 1.0)
            self._clean = 0


@dataclass
class Stats:
    requests: int = 0
    retries: int = 0
    failures: int = 0
    rate_limited: int = 0
    errors: list = field(default_factory=list)

    def note_error(self, where: str, err: str) -> None:
        self.failures += 1
        if len(self.errors) < 200:
            self.errors.append({"where": where, "error": err[:500]})


STATS = Stats()


async def get_json(
    client: httpx.AsyncClient,
    pacer: Pacer,
    url: str,
    params: dict | None = None,
    max_tries: int = 6,
) -> Any | None:
    """GET with retries/backoff. Returns parsed JSON or None on hard failure."""
    for attempt in range(max_tries):
        await pacer.wait()
        STATS.requests += 1
        try:
            r = await client.get(url, params=params, timeout=30.0)
            if r.status_code == 429 or r.status_code >= 500:
                STATS.rate_limited += r.status_code == 429
                pacer.punish()
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            if r.status_code in (400, 422):
                # Parameter problem — retrying identical params is futile.
                return {"__http_400__": True, "status": r.status_code,
                        "body": r.text[:300]}
            r.raise_for_status()
            pacer.reward()
            return r.json()
        except Exception as e:  # noqa: BLE001 - we genuinely want to survive anything
            STATS.retries += 1
            if attempt == max_tries - 1:
                STATS.note_error(url, repr(e))
                return None
            await asyncio.sleep(min(60.0, (2.0**attempt) + random.random()))
    return None


# ----------------------------------------------------------------------------
# Gamma: resolved market metadata
# ----------------------------------------------------------------------------
def parse_json_field(raw: Any) -> list:
    """Gamma encodes list fields (outcomes, outcomePrices, clobTokenIds) as JSON strings."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def resolution_label(outcome_prices: list) -> float | None:
    """1.0 if YES won, 0.0 if NO won, 0.5 for ties, None if unparseable."""
    if len(outcome_prices) != 2:
        return None
    try:
        y, n = float(outcome_prices[0]), float(outcome_prices[1])
    except (TypeError, ValueError):
        return None
    if y > 0.99 and n < 0.01:
        return 1.0
    if y < 0.01 and n > 0.99:
        return 0.0
    if abs(y - 0.5) < 0.01 and abs(n - 0.5) < 0.01:
        return 0.5
    return None


def normalize_market(m: dict, source: str) -> dict | None:
    """Any two-outcome market qualifies (Yes/No, team-vs-team, Up/Down...).
    `outcome` refers to outcomes[0]; its token is stored as yes_token."""
    outcomes = [str(o).strip() for o in parse_json_field(m.get("outcomes"))]
    if len(outcomes) != 2:
        return None
    tokens = parse_json_field(m.get("clobTokenIds"))
    prices = parse_json_field(m.get("outcomePrices"))
    events = m.get("events") or []
    ev = events[0] if events else {}
    tags = []
    for t in (ev.get("tags") or m.get("tags") or []):
        label = t.get("label") if isinstance(t, dict) else None
        if label:
            tags.append(str(label))
    category = m.get("category") or (tags[0] if tags else None)
    return {
        "market_id": str(m.get("id")),
        "condition_id": m.get("conditionId"),
        "question": m.get("question"),
        "slug": m.get("slug"),
        "category": category,
        "tags": ",".join(tags[:6]),
        "outcome0": outcomes[0],
        "outcome1": outcomes[1],
        "event_id": str(ev.get("id")) if ev.get("id") is not None else None,
        "event_slug": ev.get("slug"),
        "event_title": ev.get("title"),
        "event_neg_risk": bool(ev.get("negRisk", False)),
        "neg_risk": bool(m.get("negRisk", False)),
        "yes_token": str(tokens[0]) if len(tokens) == 2 else None,
        "no_token": str(tokens[1]) if len(tokens) == 2 else None,
        "volume": float(m.get("volumeNum") or m.get("volume") or 0.0),
        "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0.0),
        "start_date": m.get("startDate"),
        "end_date": m.get("endDate"),
        "created_at": m.get("createdAt"),
        "closed_time": m.get("closedTime"),
        "uma_status": m.get("umaResolutionStatus"),
        "best_bid": m.get("bestBid"),
        "best_ask": m.get("bestAsk"),
        "spread_snapshot": m.get("spread"),
        "volume_24h": float(m.get("volume24hr") or 0.0),
        "outcome": resolution_label(prices),
        "closed": bool(m.get("closed", False)),
        "active": bool(m.get("active", False)),
        "source": source,
    }


MAX_OFFSET = 9_500  # Gamma 422s past offset 10000; windows keep us under it


def iso_z(ts: pd.Timestamp) -> str:
    """Gamma 422s on timezone-naive ISO strings; it wants the Z suffix."""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


async def _scan_window(
    client: httpx.AsyncClient,
    pacer: Pacer,
    out: dict[str, dict],
    vol_min: float,
    lo: str,
    hi: str,
    depth: int = 0,
) -> None:
    """Scan one end_date window, volume-descending. If the window saturates
    the offset cap, split it in half (Gamma rejects offset > 10000).

    Gamma silently caps `limit` at 100 regardless of the requested value, so
    pagination must advance by the length actually returned."""
    offset = 0
    page_size = 100
    while True:
        params = {
            "closed": "true", "limit": page_size, "offset": offset,
            "order": "volumeNum", "ascending": "false",
            "end_date_min": lo, "end_date_max": hi,
        }
        page = await get_json(client, pacer, f"{GAMMA}/markets", params)
        if isinstance(page, dict) and page.get("__http_400__"):
            STATS.note_error("gamma/markets", f"400 in window {lo}..{hi}: {page.get('body')}")
            return
        if not isinstance(page, list):
            return
        vols = []
        for m in page:
            row = normalize_market(m, "volume_scan")
            if row is None:
                continue
            vols.append(row["volume"])
            if row["volume"] >= vol_min:
                out[row["market_id"]] = row
        if len(page) < page_size:
            return
        # volume-desc ordering: once a whole page is below threshold, stop
        if vols and max(vols) < vol_min:
            return
        offset += len(page)
        if offset > MAX_OFFSET:
            if depth >= 4:
                STATS.note_error("gamma/markets", f"window {lo}..{hi} still saturated at depth {depth}")
                return
            mid = pd.Timestamp(lo.rstrip("Z")) + (pd.Timestamp(hi.rstrip("Z")) - pd.Timestamp(lo.rstrip("Z"))) / 2
            mid_s = iso_z(mid)
            print(f"[gamma] window {lo}..{hi} saturated; splitting at {mid_s}")
            await _scan_window(client, pacer, out, vol_min, lo, mid_s, depth + 1)
            await _scan_window(client, pacer, out, vol_min, mid_s, hi, depth + 1)
            return


async def fetch_closed_markets(
    client: httpx.AsyncClient,
    pacer: Pacer,
    vol_min: float,
    end_date_min: str,
    max_markets: int,
) -> list[dict]:
    """Monthly end_date windows from end_date_min through ~18 months ahead
    (early-resolved markets keep far-future end dates)."""
    out: dict[str, dict] = {}
    start = pd.Timestamp(end_date_min.replace("Z", ""))
    horizon = pd.Timestamp.now("UTC").tz_localize(None) + pd.Timedelta(days=550)
    edges = pd.date_range(start, horizon, freq="MS")
    # fail fast and loud if the window param format is rejected — a silent
    # per-window failure once cost a whole run (and very nearly the dataset)
    probe = await get_json(client, pacer, f"{GAMMA}/markets", {
        "closed": "true", "limit": 1, "offset": 0,
        "end_date_min": iso_z(edges[0]), "end_date_max": iso_z(edges[1]),
    })
    if isinstance(probe, dict) and probe.get("__http_400__"):
        raise RuntimeError(f"gamma rejected window params: {probe}")
    for lo, hi in zip(edges, edges[1:]):
        before = len(out)
        await _scan_window(client, pacer, out, vol_min, iso_z(lo), iso_z(hi))
        print(f"[gamma] window {lo:%Y-%m}: +{len(out) - before} (total {len(out)})")
    # cut to the volume top-N only AFTER scanning every window — breaking
    # early silently drops the most recent months (it cost run 5 its
    # entire out-of-sample period)
    rows = sorted(out.values(), key=lambda r: -r["volume"])[:max_markets]
    print(f"[gamma] closed two-outcome markets kept: {len(rows)}")
    return rows


async def complete_negrisk_events(
    client: httpx.AsyncClient, pacer: Pacer, markets: list[dict], cap_events: int = 2500
) -> list[dict]:
    """Fetch sibling markets of neg-risk events so each event is complete."""
    have = {m["market_id"] for m in markets}
    ev_ids: list[str] = []
    seen = set()
    for m in markets:
        if (m["neg_risk"] or m["event_neg_risk"]) and m["event_id"] and m["event_id"] not in seen:
            seen.add(m["event_id"])
            ev_ids.append(m["event_id"])
    ev_ids = ev_ids[:cap_events]
    print(f"[gamma] completing {len(ev_ids)} neg-risk events")
    added: list[dict] = []

    async def one(ev_id: str) -> None:
        data = await get_json(client, pacer, f"{GAMMA}/events/{ev_id}")
        if not isinstance(data, dict):
            return
        for m in data.get("markets") or []:
            m = dict(m)
            m.setdefault("events", [{
                "id": data.get("id"), "slug": data.get("slug"),
                "title": data.get("title"), "negRisk": data.get("negRisk"),
            }])
            row = normalize_market(m, "event_completion")
            if row and row["closed"] and row["market_id"] not in have:
                have.add(row["market_id"])
                added.append(row)

    await asyncio.gather(*[one(e) for e in ev_ids])
    print(f"[gamma] event completion added {len(added)} sibling markets")
    return added


# ----------------------------------------------------------------------------
# CLOB: price histories
# ----------------------------------------------------------------------------
async def fetch_history(
    client: httpx.AsyncClient, pacer: Pacer, token: str, fidelity: int
) -> list[dict]:
    data = await get_json(
        client, pacer, f"{CLOB}/prices-history",
        {"market": token, "interval": "max", "fidelity": fidelity},
    )
    if isinstance(data, dict):
        hist = data.get("history") or []
        return hist if isinstance(hist, list) else []
    return []


async def fetch_all_histories(
    client: httpx.AsyncClient,
    pacer: Pacer,
    markets: list[dict],
    fidelity: int,
    out_dir: Path,
    tag: str,
    shard_rows: int = 2_500_000,
) -> dict:
    """Fetch histories for all markets' YES tokens, sharded parquet output."""
    todo = [(m["market_id"], m["yes_token"]) for m in markets if m["yes_token"]]
    print(f"[clob] fetching {len(todo)} histories at fidelity={fidelity} ({tag})")
    buf_mid: list[str] = []
    buf_t: list[int] = []
    buf_p: list[float] = []
    shard_idx = 0
    n_empty = 0
    n_done = 0
    t0 = time.monotonic()

    def flush(force: bool = False) -> None:
        nonlocal shard_idx, buf_mid, buf_t, buf_p
        if not buf_t or (not force and len(buf_t) < shard_rows):
            return
        df = pd.DataFrame({
            "market_id": pd.array(buf_mid, dtype="string"),
            "t": pd.array(buf_t, dtype="int64"),
            "p": pd.array(buf_p, dtype="float32"),
        })
        path = out_dir / f"prices_{tag}_{shard_idx:03d}.parquet"
        df.to_parquet(path, compression="zstd", index=False)
        print(f"[clob] wrote {path.name} rows={len(df)}")
        shard_idx += 1
        buf_mid, buf_t, buf_p = [], [], []

    sem = asyncio.Semaphore(16)

    async def one(market_id: str, token: str) -> tuple[str, list[dict]]:
        async with sem:
            return market_id, await fetch_history(client, pacer, token, fidelity)

    chunk = 800
    for i in range(0, len(todo), chunk):
        results = await asyncio.gather(*[one(mid, tok) for mid, tok in todo[i : i + chunk]])
        for market_id, hist in results:
            n_done += 1
            if not hist:
                n_empty += 1
                continue
            for pt in hist:
                t, p = pt.get("t"), pt.get("p")
                if t is None or p is None:
                    continue
                buf_mid.append(market_id)
                buf_t.append(int(t))
                buf_p.append(float(p))
        flush()
        el = time.monotonic() - t0
        print(
            f"[clob:{tag}] {n_done}/{len(todo)} empty={n_empty} rate={STATS.rate_limited}rl "
            f"rps_target={pacer.rate:.0f} elapsed={el:.0f}s"
        )
    flush(force=True)
    return {"fetched": n_done, "empty": n_empty, "shards": shard_idx}


async def probe_fidelity(
    client: httpx.AsyncClient, pacer: Pacer, markets: list[dict], fidelity: int, n: int = 15
) -> bool:
    """Check whether resolved markets return data at the given fidelity."""
    sample = [m for m in markets if m["yes_token"]][:n]
    hits = 0
    for m in sample:
        h = await fetch_history(client, pacer, m["yes_token"], fidelity)
        hits += bool(h)
    print(f"[clob] fidelity={fidelity} probe: {hits}/{len(sample)} non-empty")
    return hits >= max(2, n // 3)


# ----------------------------------------------------------------------------
# Active snapshot + books (for spread/depth calibration)
# ----------------------------------------------------------------------------
async def fetch_active_snapshot(
    client: httpx.AsyncClient, pacer: Pacer, top_n: int
) -> tuple[list[dict], list[dict]]:
    markets: list[dict] = []
    offset = 0
    while len(markets) < top_n and offset <= MAX_OFFSET:
        page = await get_json(
            client, pacer, f"{GAMMA}/markets",
            {"active": "true", "closed": "false", "limit": 100, "offset": offset,
             "order": "volume24hr", "ascending": "false"},
        )
        if not isinstance(page, list) or not page:
            break
        for m in page:
            row = normalize_market(m, "active_snapshot")
            if row and row["yes_token"]:
                markets.append(row)
        offset += len(page)
    markets = sorted(markets, key=lambda r: -r["volume_24h"])[:top_n]
    print(f"[active] snapshot of {len(markets)} active markets; fetching books")

    books: list[dict] = []
    sem = asyncio.Semaphore(12)

    async def one(m: dict) -> None:
        async with sem:
            b = await get_json(client, pacer, f"{CLOB}/book", {"token_id": m["yes_token"]})
        if not isinstance(b, dict) or b.get("__http_400__"):
            return
        bids = b.get("bids") or []
        asks = b.get("asks") or []

        def lvl(side: list, i: int, key: str) -> float | None:
            # CLOB book sides are sorted away from the touch; take extremes safely.
            try:
                arr = sorted((float(x["price"]), float(x["size"])) for x in side)
                if not arr:
                    return None
                px = arr[-1] if key == "bid" else arr[0]
                return px[0] if i == 0 else px[1]
            except (KeyError, TypeError, ValueError):
                return None

        best_bid = lvl(bids, 0, "bid")
        best_ask = lvl(asks, 0, "ask")
        depth_bid = sum(float(x.get("size", 0)) * float(x.get("price", 0)) for x in bids[-5:]) if bids else 0.0
        depth_ask = sum(float(x.get("size", 0)) * float(x.get("price", 0)) for x in asks[:5]) if asks else 0.0
        books.append({
            "market_id": m["market_id"],
            "yes_token": m["yes_token"],
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size_at_touch": lvl(bids, 1, "bid"),
            "ask_size_at_touch": lvl(asks, 1, "ask"),
            "depth_bid_top5_usd": depth_bid,
            "depth_ask_top5_usd": depth_ask,
            "ts": int(time.time()),
        })

    await asyncio.gather(*[one(m) for m in markets])
    print(f"[active] books fetched: {len(books)}")
    return markets, books


# ----------------------------------------------------------------------------
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_out")
    ap.add_argument("--vol-min", type=float, default=2000.0)
    ap.add_argument("--end-date-min", default="2024-01-01T00:00:00Z")
    ap.add_argument("--max-markets", type=int, default=80000)
    ap.add_argument("--hourly-top", type=int, default=4000)
    ap.add_argument("--active-top", type=int, default=500)
    ap.add_argument("--rps", type=float, default=25.0)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "started_utc": pd.Timestamp.now("UTC").isoformat(),
        "params": vars(args),
        "status": "running",
    }

    gamma_pacer = Pacer(8.0, floor=2.0, ceiling=15.0)
    clob_pacer = Pacer(args.rps, ceiling=40.0)

    limits = httpx.Limits(max_connections=32, max_keepalive_connections=32)
    async with httpx.AsyncClient(headers=UA, limits=limits, http2=False) as client:
        try:
            markets = await fetch_closed_markets(
                client, gamma_pacer, args.vol_min, args.end_date_min, args.max_markets
            )
            if not markets:
                raise RuntimeError("no closed markets fetched — aborting")
            siblings = await complete_negrisk_events(client, gamma_pacer, markets)
            markets.extend(siblings)

            df_m = pd.DataFrame(markets).drop_duplicates(subset="market_id")
            df_m.to_parquet(out_dir / "markets.parquet", compression="zstd", index=False)
            manifest["markets"] = {
                "rows": int(len(df_m)),
                "resolved_yes": int((df_m["outcome"] == 1.0).sum()),
                "resolved_no": int((df_m["outcome"] == 0.0).sum()),
                "ties": int((df_m["outcome"] == 0.5).sum()),
                "unparseable_outcome": int(df_m["outcome"].isna().sum()),
                "missing_tokens": int(df_m["yes_token"].isna().sum()),
                "total_volume_usd": float(df_m["volume"].sum()),
            }
            print(f"[manifest] markets: {manifest['markets']}")

            mkts = df_m.to_dict("records")

            def lifetime_h(m: dict) -> float:
                start = m.get("created_at") or m.get("start_date")
                end = m.get("end_date")
                try:
                    s = pd.Timestamp(start)
                    e = pd.Timestamp(end)
                    return float((e - s).total_seconds() / 3600)
                except (TypeError, ValueError):
                    return 1e9  # unparseable dates: fetch to be safe

            # Hourly up/down dust lives <24h and yields <=2 points at 12h
            # fidelity; skip those histories (metadata is still kept).
            mkts_hist = [m for m in mkts if lifetime_h(m) >= 24.0]
            manifest["skipped_short_lived"] = len(mkts) - len(mkts_hist)
            manifest["hist_12h"] = await fetch_all_histories(
                client, clob_pacer, mkts_hist, 720, out_dir, "12h"
            )

            top = sorted(mkts_hist, key=lambda r: -r["volume"])[: args.hourly_top]
            if await probe_fidelity(client, clob_pacer, top, 60):
                manifest["hist_1h"] = await fetch_all_histories(
                    client, clob_pacer, top, 60, out_dir, "1h"
                )
            else:
                manifest["hist_1h"] = {"skipped": "fidelity=60 empty for resolved markets"}

            act_markets, books = await fetch_active_snapshot(client, gamma_pacer, args.active_top)
            if act_markets:
                pd.DataFrame(act_markets).to_parquet(
                    out_dir / "active_markets.parquet", compression="zstd", index=False
                )
            if books:
                pd.DataFrame(books).to_parquet(
                    out_dir / "active_books.parquet", compression="zstd", index=False
                )
            manifest["active"] = {"markets": len(act_markets), "books": len(books)}
            manifest["status"] = "ok"
        except Exception:
            manifest["status"] = "partial_failure"
            manifest["fatal"] = traceback.format_exc()[-2000:]
            print("[FATAL]", manifest["fatal"], file=sys.stderr)

    manifest["finished_utc"] = pd.Timestamp.now("UTC").isoformat()
    manifest["http"] = {
        "requests": STATS.requests,
        "retries": STATS.retries,
        "failures": STATS.failures,
        "rate_limited_429": STATS.rate_limited,
        "sample_errors": STATS.errors[:50],
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({k: v for k, v in manifest.items() if k != "fatal"}, indent=2, default=str))
    return 0 if manifest["status"] == "ok" else (0 if manifest.get("markets") else 1)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
