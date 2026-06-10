"""Risk gate every order must pass. Deny-by-default: anything not provably
inside limits is rejected with a reason string (logged, auditable)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RiskLimits:
    max_order_usd: float = 50.0
    max_market_usd: float = 100.0
    max_event_usd: float = 200.0
    max_gross_usd: float = 1000.0
    max_orders_per_day: int = 200
    price_min: float = 0.02
    price_max: float = 0.985
    max_spread: float = 0.05
    min_edge: float = 0.01
    drawdown_kill_frac: float = 0.15  # halt if equity falls 15% from start
    blackout_before_end_h: float = 0.0  # optionally stop entering near end_date


@dataclass
class PortfolioView:
    """Minimal view the risk manager needs; executors supply it."""
    equity: float
    start_equity: float
    gross_exposure: float
    market_exposure: dict[str, float] = field(default_factory=dict)
    event_exposure: dict[str, float] = field(default_factory=dict)


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._orders_today = 0
        self._day = time.strftime("%Y-%m-%d")
        self.halted = False
        self.halt_reason = ""

    def _roll_day(self) -> None:
        d = time.strftime("%Y-%m-%d")
        if d != self._day:
            self._day, self._orders_today = d, 0

    def halt(self, reason: str) -> None:
        self.halted, self.halt_reason = True, reason

    def check_portfolio(self, view: PortfolioView) -> None:
        if view.start_equity > 0:
            dd = 1.0 - view.equity / view.start_equity
            if dd >= self.limits.drawdown_kill_frac:
                self.halt(f"drawdown {dd:.1%} >= kill threshold")

    def approve(
        self,
        *,
        market_id: str,
        event_id: str | None,
        price: float,
        usd: float,
        spread: float | None,
        edge: float,
        view: PortfolioView,
    ) -> tuple[bool, str]:
        self._roll_day()
        L = self.limits
        if self.halted:
            return False, f"halted: {self.halt_reason}"
        if self._orders_today >= L.max_orders_per_day:
            return False, "daily order cap"
        if not (L.price_min <= price <= L.price_max):
            return False, f"price {price:.3f} outside [{L.price_min},{L.price_max}]"
        if usd <= 0 or usd > L.max_order_usd:
            return False, f"order size {usd:.2f} > {L.max_order_usd}"
        if spread is not None and spread > L.max_spread:
            return False, f"spread {spread:.3f} > {L.max_spread}"
        if edge < L.min_edge:
            return False, f"edge {edge:.4f} < min {L.min_edge}"
        if view.market_exposure.get(market_id, 0.0) + usd > L.max_market_usd:
            return False, "market exposure cap"
        if event_id and view.event_exposure.get(event_id, 0.0) + usd > L.max_event_usd:
            return False, "event exposure cap"
        if view.gross_exposure + usd > L.max_gross_usd:
            return False, "gross exposure cap"
        self._orders_today += 1
        return True, "ok"
