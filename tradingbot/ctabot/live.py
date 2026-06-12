"""Live trading: turn the latest data into target positions and orders.

The exact pipeline used in the backtest produces today's target notional per
instrument; this module converts notionals into integer contract counts,
applies the same buffering rule against currently-held positions, and emits
orders.

Broker integration is deliberately thin: `Broker` is the interface,
`PaperBroker` (a local JSON state file) is the only implementation shipped,
because it is the only one that can be tested here. Wiring a real broker
(e.g. ib_insync for Interactive Brokers) means implementing two methods —
but do that only after running the paper broker long enough to trust the
plumbing, and start with the smallest contracts available.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run_strategy
from .config import StrategyConfig


@dataclass
class Order:
    instrument: str
    contracts: int          # signed: + buy, - sell
    reference_price: float
    notional_usd: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TargetBook:
    asof: str
    capital_usd: float
    targets: pd.DataFrame   # per instrument: forecast, notional frac, contracts

    def orders_against(self, held: dict[str, int], buffer_contracts: pd.Series) -> list[Order]:
        orders = []
        for name, row in self.targets.iterrows():
            cur = held.get(name, 0)
            tgt = row["target_contracts"]
            if np.isnan(tgt):
                continue
            buf = max(buffer_contracts.get(name, 0.0), 0.0)
            if abs(tgt - cur) <= buf:
                continue
            # trade to the nearest edge of the buffer band, in whole contracts
            edge = tgt - np.sign(tgt - cur) * buf
            qty = int(round(edge - cur))
            if qty != 0:
                orders.append(Order(
                    instrument=name, contracts=qty,
                    reference_price=float(row["price"]),
                    notional_usd=float(qty * row["contract_value_usd"]),
                    reason=f"target {tgt:+.1f} held {cur:+d} buffer {buf:.1f}",
                ))
        return orders


def compute_targets(data: dict[str, pd.DataFrame], meta: pd.DataFrame,
                    capital_usd: float, cfg: StrategyConfig | None = None,
                    fx_to_usd: dict[str, float] | None = None) -> TargetBook:
    """Run the full pipeline and convert the latest target row to contracts.

    `fx_to_usd` maps currency code -> USD rate for non-USD instruments
    (e.g. {"EUR": 1.08}); without it, non-USD instruments are skipped rather
    than mis-sized.
    """
    cfg = cfg or StrategyConfig()
    fx_to_usd = {"USD": 1.0, **(fx_to_usd or {})}
    res = run_strategy(data, meta, cfg)
    asof = res.held.index[-1]

    rows = {}
    for name in res.held.columns:
        price = data[name]["price"].asof(asof)
        cur = meta.loc[name, "currency"]
        if cur not in fx_to_usd or np.isnan(price):
            continue
        contract_value = price * meta.loc[name, "point_size"] * fx_to_usd[cur]
        notional_frac = res.decided[name].asof(asof)
        forecast = res.forecast[name].asof(asof)
        target_contracts = notional_frac * capital_usd / contract_value
        rows[name] = {
            "forecast": forecast,
            "notional_frac": notional_frac,
            "price": price,
            "contract_value_usd": contract_value,
            "target_contracts": target_contracts,
        }
    targets = pd.DataFrame(rows).T.sort_index()
    return TargetBook(asof=str(asof.date()), capital_usd=capital_usd, targets=targets)


def buffer_in_contracts(book: TargetBook, meta: pd.DataFrame,
                        cfg: StrategyConfig) -> pd.Series:
    """10% of the average-forecast position, in contracts (same rule the
    backtest uses, so live turnover matches backtested turnover)."""
    tgt = book.targets
    avg_position = (tgt["target_contracts"].abs()
                    / (tgt["forecast"].abs() / 10.0).clip(lower=0.5))
    return (avg_position * cfg.position_buffer).fillna(0.0)


class Broker:
    def positions(self) -> dict[str, int]:
        raise NotImplementedError

    def submit(self, orders: list[Order], asof: str) -> None:
        raise NotImplementedError


class PaperBroker(Broker):
    """Tracks fills in a local JSON file at reference prices. No slippage is
    modelled here; the backtest's cost model is the estimate of live costs."""

    def __init__(self, state_path: str | Path):
        self.path = Path(state_path)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "positions": {}, "fills": []}

    def positions(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.state["positions"].items()}

    def submit(self, orders: list[Order], asof: str) -> None:
        for o in orders:
            pos = self.state["positions"].get(o.instrument, 0) + o.contracts
            self.state["positions"][o.instrument] = pos
            self.state["fills"].append({
                "ts": datetime.now(timezone.utc).isoformat(), "asof": asof,
                **o.to_dict()})
        self.path.write_text(json.dumps(self.state, indent=2))
