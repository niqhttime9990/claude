"""Market data feeds for the simulator.

Two implementations of the same interface:

- ReplayFeed: steps through the pinned historical snapshot one trading day
  at a time. Works offline, includes futures-curve data (so carry trades),
  and lets you replay decades in minutes.
- YahooFeed: live mode. Pulls continuous front-month futures quotes from
  Yahoo Finance (delayed ~10-15 min for most contracts) on a real schedule.
  No curve data is available there, so live mode runs the trend sleeve
  only; the engine renormalises automatically.

Live contract specs (multipliers) are hard-coded from CME/ICE contract
specifications — they are what convert prices into dollars, so they must
not be guessed from any data file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ctabot.config import PATHS
from ctabot.data import load_universe


@dataclass(frozen=True)
class ContractSpec:
    instrument: str
    yahoo: str
    multiplier: float        # USD (or EUR) per 1.0 price point, per contract
    currency: str
    asset_class: str
    spread_points: float     # half-spread, in price points
    rolls_per_year: int


# Verified against CME/ICE/Eurex contract specs. EUROSTX uses the index
# quote as a proxy for the FESX future (no continuous future on Yahoo).
# BUND has no usable Yahoo symbol and is omitted from live mode.
LIVE_SPECS: list[ContractSpec] = [
    ContractSpec("SP500",   "ES=F", 50.0,    "USD", "Equity", 0.25,  4),
    ContractSpec("NASDAQ",  "NQ=F", 20.0,    "USD", "Equity", 0.50,  4),
    ContractSpec("DOW",     "YM=F", 5.0,     "USD", "Equity", 2.0,   4),
    ContractSpec("EUROSTX", "^STOXX50E", 10.0, "EUR", "Equity", 1.0, 4),
    ContractSpec("US2",     "ZT=F", 2000.0,  "USD", "Bond", 0.0039, 4),
    ContractSpec("US5",     "ZF=F", 1000.0,  "USD", "Bond", 0.0078, 4),
    ContractSpec("US10",    "ZN=F", 1000.0,  "USD", "Bond", 0.0156, 4),
    ContractSpec("US30",    "ZB=F", 1000.0,  "USD", "Bond", 0.0313, 4),
    ContractSpec("GOLD",    "GC=F", 100.0,   "USD", "Metals", 0.10, 6),
    ContractSpec("SILVER",  "SI=F", 5000.0,  "USD", "Metals", 0.005, 5),
    ContractSpec("COPPER",  "HG=F", 25000.0, "USD", "Metals", 0.0005, 5),
    ContractSpec("PLAT",    "PL=F", 50.0,    "USD", "Metals", 0.30, 4),
    ContractSpec("CRUDE_W", "CL=F", 1000.0,  "USD", "OilGas", 0.01, 12),
    ContractSpec("BRENT_W", "BZ=F", 1000.0,  "USD", "OilGas", 0.01, 12),
    ContractSpec("GAS_US",  "NG=F", 10000.0, "USD", "OilGas", 0.001, 12),
    ContractSpec("HEATOIL", "HO=F", 42000.0, "USD", "OilGas", 0.0004, 12),
    ContractSpec("CORN",    "ZC=F", 50.0,    "USD", "Ags", 0.25, 5),
    ContractSpec("WHEAT",   "ZW=F", 50.0,    "USD", "Ags", 0.25, 5),
    ContractSpec("SOYBEAN", "ZS=F", 50.0,    "USD", "Ags", 0.25, 7),
    ContractSpec("SUGAR11", "SB=F", 1120.0,  "USD", "Ags", 0.01, 4),
    ContractSpec("COFFEE",  "KC=F", 375.0,   "USD", "Ags", 0.05, 4),
    ContractSpec("LIVECOW", "LE=F", 400.0,   "USD", "Ags", 0.025, 6),
]

COMMISSION_USD = 1.5


class ReplayFeed:
    """Replays the pinned snapshot. Curve data included -> carry is live."""

    mode = "replay"

    def __init__(self, raw_dir: str | Path | None = None,
                 start: str = "1982-01-01", end: str | None = None):
        if raw_dir is None:
            # cwd first (data/ copied next to a packaged exe), then the repo
            candidates = [Path.cwd() / PATHS.raw_dir,
                          Path(__file__).resolve().parents[1] / PATHS.raw_dir]
            raw_dir = next((c for c in candidates if c.is_dir()), candidates[-1])
        self.data, self.meta = load_universe(raw_dir)
        dates = pd.DatetimeIndex(sorted(set().union(*[df.index for df in self.data.values()])))
        dates = dates[dates >= pd.Timestamp(start)]
        if end:
            dates = dates[dates <= pd.Timestamp(end)]
        self.dates = dates
        self._i = -1

    def specs(self) -> dict[str, dict]:
        out = {}
        for name in self.data:
            m = self.meta.loc[name]
            out[name] = {
                "multiplier": float(m["point_size"]), "currency": m["currency"],
                "asset_class": m["asset_class"],
                "spread_points": float(m["spread_cost_points"]),
                "rolls_per_year": int(m["rolls_per_year"]),
            }
        return out

    def next_bar(self):
        """Advance one trading day.

        Returns (date, settle_closes, contract_prices) or None. P&L must be
        settled on the *back-adjusted* series (its differences are the true
        per-contract point P&L; the raw front-contract series jumps at every
        roll), while position sizing and notionals use the actual contract
        price."""
        if self._i + 1 >= len(self.dates):
            return None
        self._i += 1
        d = self.dates[self._i]
        settle, px = {}, {}
        for name, df in self.data.items():
            if d in df.index:
                settle[name] = float(df.loc[d, "adj"])
                px[name] = float(df.loc[d, "price"])
        return d, settle, px

    def _asof(self, col: str) -> dict[str, float]:
        if self._i < 0:
            return {}
        d = self.dates[self._i]
        out = {}
        for name, df in self.data.items():
            if df.index.min() <= d:
                v = df[col].asof(d)
                if not np.isnan(v):
                    out[name] = float(v)
        return out

    def quotes(self) -> dict[str, float]:
        """Latest actual contract prices (sizing, notional, display)."""
        return self._asof("price")

    def quotes_settle(self) -> dict[str, float]:
        """Latest prices on the P&L (back-adjusted) scale."""
        return self._asof("adj")

    def fx_to_usd(self) -> dict[str, float]:
        # Replay accounting treats EUR P&L 1:1 (the backtest sizes in
        # percent terms, where FX is second-order).
        return {"USD": 1.0, "EUR": 1.0}

    def progress(self) -> dict:
        return {"index": self._i, "total": len(self.dates),
                "date": str(self.dates[self._i].date()) if self._i >= 0 else None}


class YahooFeed:
    """Live mode. Daily history once a day + quote refresh every poll."""

    mode = "live"

    def __init__(self, lookback: str = "3y"):
        import yfinance  # imported lazily: live mode only

        self._yf = yfinance
        self._specs = {s.instrument: s for s in LIVE_SPECS}
        self._symbols = [s.yahoo for s in LIVE_SPECS] + ["EURUSD=X"]
        self.lookback = lookback
        self._hist: dict[str, pd.DataFrame] = {}
        self._quotes: dict[str, float] = {}
        self._eurusd = 1.0
        self._last_bar_date: pd.Timestamp | None = None
        self._pending: tuple | None = None
        self.refresh()

    def specs(self) -> dict[str, dict]:
        return {n: {"multiplier": s.multiplier, "currency": s.currency,
                    "asset_class": s.asset_class, "spread_points": s.spread_points,
                    "rolls_per_year": s.rolls_per_year}
                for n, s in self._specs.items()}

    def refresh(self) -> None:
        """Download daily bars for all symbols; update quotes and detect a
        newly completed trading day."""
        raw = self._yf.download(self._symbols, period=self.lookback,
                                interval="1d", auto_adjust=False,
                                progress=False, group_by="ticker", threads=True)
        closes = {}
        for name, spec in self._specs.items():
            try:
                s = raw[spec.yahoo]["Close"].dropna()
            except KeyError:
                continue
            if s.empty:
                continue
            df = pd.DataFrame({"adj": s, "price": s})
            df["carry_price"] = np.nan
            df["price_contract"] = np.nan
            df["carry_contract"] = np.nan
            df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
            df = df.groupby(df.index).last()
            self._hist[name] = df
            self._quotes[name] = float(s.iloc[-1])
            closes[name] = float(s.iloc[-1])
        try:
            self._eurusd = float(raw["EURUSD=X"]["Close"].dropna().iloc[-1])
        except Exception:  # noqa: BLE001 - keep previous rate on any failure
            pass

        # A bar counts as complete once a later calendar date has printed
        # for the majority of instruments (i.e. the trading day rolled).
        dates = [df.index[-1] for df in self._hist.values() if len(df)]
        if dates:
            latest = max(dates)
            prev = max([d for df in self._hist.values()
                        for d in [df.index[df.index < latest].max()] if pd.notna(d)],
                       default=None)
            if prev is not None and self._last_bar_date is None:
                self._last_bar_date = prev  # don't replay history as "new" bars
            if prev is not None and prev > (self._last_bar_date or prev - pd.Timedelta(days=1)):
                bar_closes = {n: float(df["price"].asof(prev))
                              for n, df in self._hist.items() if prev in df.index}
                self._pending = (prev, bar_closes)
                self._last_bar_date = prev

    def next_bar(self):
        bar, self._pending = self._pending, None
        if bar is None:
            return None
        date, closes = bar
        # Yahoo continuous quotes have no separate adjusted series: settle
        # and contract price are the same. The series jumps when the front
        # month rolls (a few times a year per market); over a multi-month
        # paper test this adds bounded noise to P&L. Disclosed in the UI.
        return date, closes, closes

    def history(self) -> dict[str, pd.DataFrame]:
        return self._hist

    def quotes(self) -> dict[str, float]:
        return dict(self._quotes)

    def quotes_settle(self) -> dict[str, float]:
        return dict(self._quotes)

    def fx_to_usd(self) -> dict[str, float]:
        return {"USD": 1.0, "EUR": self._eurusd}

    def progress(self) -> dict:
        return {"date": str(self._last_bar_date.date()) if self._last_bar_date is not None else None}
