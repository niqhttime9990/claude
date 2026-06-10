"""Live strategy scanners. Each returns OrderIntents; the bot risk-gates and
executes them. Parameters come from reports/params.json, which is written by
the research pipeline — strategies stay disabled until a backtest has
produced parameters, by design."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from .execution import OrderIntent
from .gateway import Gateway, parse_json_field

DEFAULT_PARAMS = {
    "favorite": {"enabled": False},
    "negrisk": {"enabled": False},
}


def load_params(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return DEFAULT_PARAMS
    try:
        return {**DEFAULT_PARAMS, **json.loads(p.read_text())}
    except json.JSONDecodeError:
        return DEFAULT_PARAMS


async def favorite_scan(
    gw: Gateway, params: dict, held_tokens: set[str], stake_usd: float
) -> list[OrderIntent]:
    """Buy heavy favorites in their final window when the ask still sits in
    the band the backtest validated."""
    cfg = params.get("favorite") or {}
    if not cfg.get("enabled"):
        return []
    theta = float(cfg["theta"])
    window_s = float(cfg["window_days"]) * 86400
    min_vol = float(cfg.get("min_volume", 10_000))
    expected_ret = float(cfg.get("expected_ret", 0.0))
    side_mode = cfg.get("side_mode", "both")
    now = time.time()

    intents: list[OrderIntent] = []
    markets = await gw.active_markets(limit=1000)
    cands = []
    for m in markets:
        try:
            end_ts = m.get("endDate")
            if not end_ts:
                continue
            end_t = datetime.fromisoformat(end_ts.replace("Z", "+00:00")).timestamp()
            if not (0 < end_t - now <= window_s):
                continue
            if float(m.get("volume24hr") or 0) < min_vol / 10:
                continue
            if float(m.get("volumeNum") or 0) < min_vol:
                continue
            # any two-outcome market qualifies (Yes/No, team-vs-team, ...),
            # matching the backtest universe
            if len(parse_json_field(m.get("outcomes"))) != 2:
                continue
            tokens = parse_json_field(m.get("clobTokenIds"))
            if len(tokens) != 2:
                continue
            cands.append((m, str(tokens[0]), str(tokens[1])))
        except (TypeError, ValueError):
            continue

    books = await gw.books([c[1] for c in cands])
    for m, yes_tok, no_tok in cands:
        book = books.get(yes_tok)
        if book is None or book.best_ask is None or book.best_bid is None:
            continue
        spread = book.best_ask - book.best_bid
        mid = (book.best_ask + book.best_bid) / 2
        ev = (m.get("events") or [{}])[0]
        # YES favorite: ask within validated band
        if side_mode in ("yes", "both") and theta <= book.best_ask <= 0.985 and yes_tok not in held_tokens:
            intents.append(OrderIntent(
                strategy="favorite", market_id=str(m["id"]),
                event_id=str(ev.get("id")) if ev.get("id") else None,
                token_id=yes_tok, side="BUY", limit_price=book.best_ask,
                usd=stake_usd, edge=expected_ret,
                reason=f"favorite YES mid={mid:.3f} spread={spread:.3f} q='{str(m.get('question'))[:60]}'",
            ))
        # NO favorite: yes bid below 1-theta means NO trades above theta
        if side_mode in ("no", "both") and book.best_bid <= 1 - theta and no_tok not in held_tokens:
            no_book = await gw.book(no_tok)
            if no_book and no_book.best_ask and theta <= no_book.best_ask <= 0.985:
                intents.append(OrderIntent(
                    strategy="favorite", market_id=str(m["id"]),
                    event_id=str(ev.get("id")) if ev.get("id") else None,
                    token_id=no_tok, side="BUY", limit_price=no_book.best_ask,
                    usd=stake_usd, edge=expected_ret,
                    reason=f"favorite NO yes_mid={mid:.3f} q='{str(m.get('question'))[:60]}'",
                ))
    return intents


async def negrisk_scan(
    gw: Gateway, params: dict, stake_sets: float = 10.0
) -> list[OrderIntent]:
    """Structural arbitrage on neg-risk (mutually exclusive, exhaustive)
    events: if one full set of NO shares costs < n-1 (resp. YES set < 1),
    buy the set; payout is deterministic at resolution.

    Execution must be atomic: legs are tagged all_or_none and the executor
    uses FOK orders (live) or all-or-nothing planning (paper)."""
    cfg = params.get("negrisk") or {}
    if not cfg.get("enabled"):
        return []
    min_edge_per_set = float(cfg.get("min_edge_per_set", 0.02))  # $ per set
    max_members = int(cfg.get("max_members", 25))

    intents: list[OrderIntent] = []
    events = await gw.negrisk_events(limit=200)
    for ev in events:
        markets = [m for m in (ev.get("markets") or [])
                   if m.get("active") and not m.get("closed")]
        n = len(markets)
        if not (3 <= n <= max_members):
            continue
        legs = []
        ok = True
        for m in markets:
            toks = parse_json_field(m.get("clobTokenIds"))
            if len(toks) != 2:
                ok = False
                break
            legs.append((str(m["id"]), str(toks[0]), str(toks[1])))
        if not ok:
            continue

        # --- buy-all-NO: cost < n-1 ---
        no_books = await gw.books([l[2] for l in legs])
        if len(no_books) == len(legs):
            cost, depth_ok = 0.0, True
            for _, _, no_tok in legs:
                b = no_books[no_tok]
                plan = b.buy_cost(stake_sets * (b.best_ask or 1.0)) if b.asks else None
                if b.best_ask is None or plan is None:
                    depth_ok = False
                    break
                cost += plan[0]  # avg price for the sized clip
            if depth_ok and (n - 1) - cost >= min_edge_per_set:
                gid = f"negrisk-no-{ev.get('id')}-{int(time.time())}"
                for mid_, _, no_tok in legs:
                    b = no_books[no_tok]
                    intents.append(OrderIntent(
                        strategy="negrisk", market_id=mid_,
                        event_id=str(ev.get("id")), token_id=no_tok, side="BUY",
                        limit_price=min(0.999, (b.best_ask or 1.0) + 0.002),
                        usd=stake_sets * (b.best_ask or 1.0),
                        edge=((n - 1) - cost) / max(cost, 1e-9),
                        reason=f"negrisk NO set cost={cost:.3f} < n-1={n - 1} ev='{str(ev.get('title'))[:50]}'",
                        all_or_none_group=gid,
                    ))

        # --- buy-all-YES: cost < 1 ---
        yes_books = await gw.books([l[1] for l in legs])
        if len(yes_books) == len(legs):
            cost, depth_ok = 0.0, True
            for _, yes_tok, _ in legs:
                b = yes_books[yes_tok]
                if b.best_ask is None:
                    depth_ok = False
                    break
                cost += b.best_ask
            if depth_ok and 1.0 - cost >= min_edge_per_set:
                gid = f"negrisk-yes-{ev.get('id')}-{int(time.time())}"
                for mid_, yes_tok, _ in legs:
                    b = yes_books[yes_tok]
                    intents.append(OrderIntent(
                        strategy="negrisk", market_id=mid_,
                        event_id=str(ev.get("id")), token_id=yes_tok, side="BUY",
                        limit_price=min(0.999, (b.best_ask or 1.0) + 0.002),
                        usd=stake_sets * (b.best_ask or 1.0),
                        edge=(1.0 - cost) / max(cost, 1e-9),
                        reason=f"negrisk YES set cost={cost:.3f} < 1 ev='{str(ev.get('title'))[:50]}'",
                        all_or_none_group=gid,
                    ))
    return intents
