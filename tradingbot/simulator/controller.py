"""Simulation controllers: glue between feed, strategy pipeline and account.

ReplayController precomputes the whole backtest once (identical code path
to the validated backtest) and then walks through it bar by bar, doing
contract-level accounting at each step. LiveController re-runs the pipeline
each time a trading day completes, on data from the live feed.

Execution convention matches the backtest: a target decided on bar D's
close is executed at the next observed price (replay: bar D+1's close;
live: the first quote poll after the new bar is detected).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ctabot.backtest import run_strategy
from ctabot.config import PRESETS, StrategyConfig

from .account import PaperAccount

MARGIN_PCT = {"Equity": 0.06, "Bond": 0.015, "Metals": 0.07,
              "OilGas": 0.10, "Ags": 0.06}


def _max_drawdown(values: list[float]) -> float:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return 0.0
    peak = np.maximum.accumulate(arr)
    return float((arr / peak - 1.0).min())


def _daily_perf(history: list[dict]) -> dict:
    """Stats on one-snapshot-per-day equity, robust to intraday marks."""
    by_day: dict[str, float] = {}
    for snap in history:
        by_day[snap["ts"][:10]] = snap["equity"]
    eq = list(by_day.values())
    out = {"ann_vol": None, "sharpe": None, "max_drawdown": _max_drawdown(eq)}
    if len(eq) > 20:
        rets = np.diff(eq) / np.asarray(eq[:-1])
        if rets.std() > 0:
            out["ann_vol"] = float(rets.std() * np.sqrt(256))
            out["sharpe"] = float(rets.mean() / rets.std() * np.sqrt(256))
    return out


class BaseController:
    def __init__(self, feed, account: PaperAccount, preset: str = "base"):
        self.feed = feed
        self.account = account
        self.preset = preset
        self.cfg: StrategyConfig = PRESETS[preset]
        self.lock = threading.Lock()
        self.paused = False
        self.speed = 25.0          # replay bars/second
        self.day_pnl = 0.0
        self.last_forecast: dict[str, float] = {}
        self.pending_targets: dict[str, float] | None = None   # notional fracs
        self.bench_units: float | None = None
        self.bench_price0: float | None = None
        self.finished = False
        self.last_error: str | None = None

    # -- shared mechanics --------------------------------------------------

    def _bench_equity(self, settle_quotes: dict[str, float],
                      px_quotes: dict[str, float]) -> float:
        """Buy-and-hold S&P futures with the same starting capital. Sized on
        the real contract price, P&L accrued on the back-adjusted scale."""
        adj = settle_quotes.get("SP500")
        px = px_quotes.get("SP500")
        if adj is None or px is None:
            return self.account.capital0 if self.bench_units is None else self._last_bench
        if self.bench_units is None:
            mult = self.account.specs["SP500"]["multiplier"]
            self.bench_units = self.account.capital0 / (px * mult)
            self.bench_price0 = adj
        mult = self.account.specs["SP500"]["multiplier"]
        self._last_bench = self.account.capital0 + self.bench_units * mult * (adj - self.bench_price0)
        return self._last_bench

    def _execute_pending(self, px_prices: dict[str, float],
                         settle_prices: dict[str, float], ts: str) -> None:
        if not self.pending_targets:
            return
        fx = self.feed.fx_to_usd()
        equity = self.account.equity
        for inst, frac in self.pending_targets.items():
            px = px_prices.get(inst)
            settle = settle_prices.get(inst)
            if px is None or settle is None or px <= 0 or np.isnan(frac):
                continue
            spec = self.account.specs[inst]
            cv = px * spec["multiplier"] * fx.get(spec["currency"], 1.0)
            target = frac * equity / cv
            cur = self.account.positions.get(inst, 0)
            buffer = max(1.0, 0.10 * max(abs(target), 1.0))
            if abs(target - cur) > buffer:
                self.account.trade(inst, int(round(target)), settle, fx, ts,
                                   note=f"target {target:+.1f}", display_price=px)
        self.pending_targets = None

    def _settle_and_snapshot(self, date: pd.Timestamp, settle_closes: dict[str, float],
                             px_closes: dict[str, float]) -> None:
        fx = self.feed.fx_to_usd()
        ts = str(date.date())
        self.day_pnl = self.account.settle(settle_closes, fx, ts)
        self._execute_pending(px_closes, settle_closes, ts)
        self.account.snapshot(ts, self.feed.quotes_settle(), fx,
                              self._bench_equity(self.feed.quotes_settle(),
                                                 self.feed.quotes()))

    # -- API surface ---------------------------------------------------------

    def control(self, action: str, value=None) -> None:
        with self.lock:
            if action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "speed":
                self.speed = float(np.clip(float(value), 0.2, 256.0))

    def state(self) -> dict:
        with self.lock:
            quotes = self.feed.quotes()              # real contract prices
            settle_q = self.feed.quotes_settle()     # P&L scale
            fx = self.feed.fx_to_usd()
            acct = self.account
            equity = acct.marked_equity(settle_q, fx)
            bench = self._bench_equity(settle_q, quotes)
            gross = acct.gross_notional(quotes, fx)
            perf = _daily_perf(acct.history)

            positions = []
            margin = 0.0
            class_exposure: dict[str, float] = {}
            for inst, qty in sorted(acct.positions.items()):
                spec = acct.specs[inst]
                px = quotes.get(inst)
                adj = settle_q.get(inst, acct.basis.get(inst))
                if px is None or qty == 0:
                    continue
                mult = spec["multiplier"] * fx.get(spec["currency"], 1.0)
                notional = qty * px * mult
                margin += abs(notional) * MARGIN_PCT.get(spec["asset_class"], 0.08)
                class_exposure[spec["asset_class"]] = (
                    class_exposure.get(spec["asset_class"], 0.0) + notional / equity)
                positions.append({
                    "instrument": inst, "class": spec["asset_class"],
                    "contracts": qty, "price": round(px, 4),
                    "notional": round(notional, 0),
                    "open_pnl": round(qty * mult * (adj - acct.basis.get(inst, adj)), 0),
                    "forecast": round(self.last_forecast.get(inst, float("nan")), 1)
                    if self.last_forecast.get(inst) is not None else None,
                })

            hist = acct.history
            step = max(1, len(hist) // 2000)
            series = hist[::step]
            if hist and (not series or series[-1] is not hist[-1]):
                series = series + [hist[-1]]

            return {
                "meta": {"mode": self.feed.mode, "preset": self.preset,
                         "paused": self.paused, "speed": self.speed,
                         "finished": self.finished, "error": self.last_error,
                         "progress": self.feed.progress(),
                         "server_time": datetime.now(timezone.utc).isoformat()},
                "kpis": {
                    "capital0": acct.capital0,
                    "equity": equity,
                    "total_pnl": equity - acct.capital0,
                    "total_return": equity / acct.capital0 - 1.0,
                    "day_pnl": self.day_pnl,
                    "benchmark_equity": bench,
                    "benchmark_return": bench / acct.capital0 - 1.0,
                    "vs_benchmark": (equity - bench) / acct.capital0,
                    "gross_exposure_x": gross / equity if equity > 0 else 0.0,
                    "margin_est": margin,
                    "costs_paid": acct.realized_costs,
                    "ann_vol": perf["ann_vol"],
                    "sharpe": perf["sharpe"],
                    "max_drawdown": perf["max_drawdown"],
                    "n_fills": len(acct.fills),
                },
                "positions": positions,
                "class_exposure": class_exposure,
                "fills": [f.to_dict() for f in acct.fills[-40:]][::-1],
                "equity_series": series,
            }


class ReplayController(BaseController):
    def __init__(self, feed, account: PaperAccount, preset: str = "base"):
        super().__init__(feed, account, preset)
        res = run_strategy(feed.data, feed.meta, self.cfg)
        lag = 1 + self.cfg.execution_lag_days
        self.decided = res.held.shift(-lag)        # decision rows, by decision date
        self.forecast = res.forecast

    def step(self) -> bool:
        """Process one trading day. Returns False when the replay is done."""
        with self.lock:
            if self.paused or self.finished:
                return not self.finished
            bar = self.feed.next_bar()
            if bar is None:
                self.finished = True
                return False
            date, settle_closes, px_closes = bar
            self._settle_and_snapshot(date, settle_closes, px_closes)
            if date in self.decided.index:
                row = self.decided.loc[date]
                self.pending_targets = {k: v for k, v in row.items() if pd.notna(v)}
                frow = self.forecast.loc[date]
                self.last_forecast = {k: float(v) for k, v in frow.items() if pd.notna(v)}
            return True


class LiveController(BaseController):
    """Polls the live feed; recomputes the pipeline when a day completes.

    Live mode has no futures-curve data, so the carry sleeve is disabled
    (trend weight renormalises to 100%)."""

    def __init__(self, feed, account: PaperAccount, preset: str = "base"):
        super().__init__(feed, account, preset)
        import dataclasses
        self.cfg = dataclasses.replace(self.cfg, trend_weight=1.0, carry_weight=0.0)
        self._meta = self._build_meta()

    def _build_meta(self) -> pd.DataFrame:
        rows = []
        for inst, spec in self.feed.specs().items():
            rows.append({"instrument": inst, "asset_class": spec["asset_class"],
                         "point_size": spec["multiplier"], "currency": spec["currency"],
                         "spread_cost_points": spec["spread_points"],
                         "rolls_per_year": spec["rolls_per_year"]})
        return pd.DataFrame(rows).set_index("instrument")

    def step(self) -> bool:
        """One poll cycle: refresh quotes, mark, act on a completed bar."""
        with self.lock:
            if self.paused:
                return True
            try:
                self.feed.refresh()
                self._execute_pending(self.feed.quotes(), self.feed.quotes_settle(),
                                      datetime.now(timezone.utc).isoformat())
                bar = self.feed.next_bar()
                if bar is not None:
                    date, settle_closes, _px = bar
                    fx = self.feed.fx_to_usd()
                    self.day_pnl = self.account.settle(settle_closes, fx, str(date.date()))
                    res = run_strategy(self.feed.history(), self._meta, self.cfg)
                    lag = 1 + self.cfg.execution_lag_days
                    decided = res.held.shift(-lag)
                    if date in decided.index:
                        row = decided.loc[date]
                        self.pending_targets = {k: v for k, v in row.items() if pd.notna(v)}
                        frow = res.forecast.loc[date]
                        self.last_forecast = {k: float(v) for k, v in frow.items()
                                              if pd.notna(v)}
                self.account.snapshot(datetime.now(timezone.utc).isoformat(),
                                      self.feed.quotes_settle(), self.feed.fx_to_usd(),
                                      self._bench_equity(self.feed.quotes_settle(),
                                                         self.feed.quotes()))
                self.last_error = None
            except Exception as err:  # noqa: BLE001 - keep serving on feed hiccups
                self.last_error = f"{type(err).__name__}: {err}"
            return True
