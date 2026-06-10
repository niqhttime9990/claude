"""Paper futures account with exact daily-settlement accounting.

Futures P&L works by margining: every day each open position is settled
against the new close (variation margin), and trades settle the existing
lot at the trade price first. This model reproduces that, charges
half-spread + commission per contract traded, and marks open positions
against the latest quote for display.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Fill:
    ts: str
    instrument: str
    contracts: int
    price: float
    cost_usd: float
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PaperAccount:
    capital0: float
    specs: dict[str, dict]                      # instrument -> multiplier/currency/...
    commission_usd: float = 1.5
    equity: float = field(init=False)           # settled equity
    positions: dict[str, int] = field(default_factory=dict)
    basis: dict[str, float] = field(default_factory=dict)   # last settle/trade price
    fills: list[Fill] = field(default_factory=list)
    realized_costs: float = 0.0
    history: list[dict] = field(default_factory=list)       # daily snapshots

    def __post_init__(self) -> None:
        self.equity = self.capital0

    # -- core mechanics ----------------------------------------------------

    def _mult_usd(self, inst: str, fx: dict[str, float]) -> float:
        spec = self.specs[inst]
        return spec["multiplier"] * fx.get(spec["currency"], 1.0)

    def settle(self, closes: dict[str, float], fx: dict[str, float], ts: str,
               trading_days: int = 256) -> float:
        """Daily variation-margin settlement at the given closes (on the
        P&L/back-adjusted scale), plus the pro-rated cost of periodic
        contract rolls on open positions."""
        day_pnl = 0.0
        for inst, qty in self.positions.items():
            if qty == 0 or inst not in closes:
                continue
            px = closes[inst]
            mult = self._mult_usd(inst, fx)
            day_pnl += qty * mult * (px - self.basis.get(inst, px))
            self.basis[inst] = px
            spec = self.specs[inst]
            roll_cost = (abs(qty) * (spec["spread_points"] * mult + self.commission_usd)
                         * spec.get("rolls_per_year", 0) / trading_days)
            day_pnl -= roll_cost
            self.realized_costs += roll_cost
        self.equity += day_pnl
        return day_pnl

    def trade(self, inst: str, target_qty: int, settle_price: float,
              fx: dict[str, float], ts: str, note: str = "",
              display_price: float | None = None) -> Fill | None:
        """Trade to `target_qty`. `settle_price` is on the P&L scale (it
        settles the existing lot); `display_price` is the actual contract
        price recorded on the fill for humans."""
        cur = self.positions.get(inst, 0)
        delta = int(target_qty - cur)
        if delta == 0:
            return None
        mult = self._mult_usd(inst, fx)
        # settle the existing lot at the trade price (variation margin)
        if cur != 0:
            self.equity += cur * mult * (settle_price - self.basis.get(inst, settle_price))
        cost = abs(delta) * (self.specs[inst]["spread_points"] * mult + self.commission_usd)
        self.equity -= cost
        self.realized_costs += cost
        self.positions[inst] = cur + delta
        self.basis[inst] = settle_price
        fill = Fill(ts=ts, instrument=inst, contracts=delta,
                    price=display_price if display_price is not None else settle_price,
                    cost_usd=cost, note=note)
        self.fills.append(fill)
        return fill

    def marked_equity(self, quotes: dict[str, float], fx: dict[str, float]) -> float:
        """Settled equity plus open P&L vs latest quotes (display only)."""
        open_pnl = 0.0
        for inst, qty in self.positions.items():
            if qty == 0 or inst not in quotes:
                continue
            open_pnl += qty * self._mult_usd(inst, fx) * (quotes[inst] - self.basis.get(inst, quotes[inst]))
        return self.equity + open_pnl

    def gross_notional(self, quotes: dict[str, float], fx: dict[str, float]) -> float:
        return sum(abs(qty) * self._mult_usd(i, fx) * quotes.get(i, self.basis.get(i, 0.0))
                   for i, qty in self.positions.items() if qty != 0)

    def snapshot(self, ts: str, quotes: dict[str, float], fx: dict[str, float],
                 benchmark_equity: float) -> dict:
        snap = {
            "ts": ts,
            "equity": round(self.marked_equity(quotes, fx), 2),
            "benchmark": round(benchmark_equity, 2),
        }
        self.history.append(snap)
        return snap

    # -- persistence ---------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "capital0": self.capital0, "equity": self.equity,
            "positions": self.positions, "basis": self.basis,
            "realized_costs": self.realized_costs,
            "fills": [f.to_dict() for f in self.fills[-500:]],
            "history": self.history,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict()))

    @classmethod
    def load(cls, path: str | Path, specs: dict[str, dict],
             commission_usd: float = 1.5) -> "PaperAccount":
        raw = json.loads(Path(path).read_text())
        acct = cls(capital0=raw["capital0"], specs=specs, commission_usd=commission_usd)
        acct.equity = raw["equity"]
        acct.positions = {k: int(v) for k, v in raw["positions"].items()}
        acct.basis = {k: float(v) for k, v in raw["basis"].items()}
        acct.realized_costs = raw["realized_costs"]
        acct.fills = [Fill(**f) for f in raw["fills"]]
        acct.history = raw["history"]
        return acct
