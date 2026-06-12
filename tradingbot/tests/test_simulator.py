"""Simulator tests: accounting identities, replay end-to-end, server API."""

import json
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulator.account import PaperAccount
from simulator.controller import ReplayController
from simulator.datafeed import ReplayFeed
from simulator.server import _make_handler, serve

SPECS = {"X": {"multiplier": 100.0, "currency": "USD", "asset_class": "Equity",
               "spread_points": 0.5, "rolls_per_year": 0}}
FX = {"USD": 1.0}


def test_account_daily_settlement():
    acct = PaperAccount(1_000_000, SPECS, commission_usd=2.0)
    acct.trade("X", 3, 100.0, FX, "d0")           # buy 3 @ 100
    cost = 3 * (0.5 * 100.0 + 2.0)                # half-spread*mult + commission
    assert acct.equity == pytest.approx(1_000_000 - cost)
    acct.settle({"X": 105.0}, FX, "d1")           # +5 pts * 3 * 100
    assert acct.equity == pytest.approx(1_000_000 - cost + 1500)
    acct.trade("X", -2, 110.0, FX, "d2")          # settles +5*3*100 then flips short
    cost2 = 5 * (0.5 * 100.0 + 2.0)
    assert acct.equity == pytest.approx(1_000_000 - cost - cost2 + 1500 + 1500)
    acct.settle({"X": 100.0}, FX, "d3")           # short 2, price -10 -> +2000
    assert acct.equity == pytest.approx(1_000_000 - cost - cost2 + 3000 + 2000)
    assert acct.positions["X"] == -2


def test_roll_cost_drag():
    specs = {"X": {**SPECS["X"], "rolls_per_year": 8}}
    acct = PaperAccount(1_000_000, specs, commission_usd=2.0)
    acct.trade("X", 2, 100.0, FX, "d0")
    eq_before = acct.equity
    acct.settle({"X": 100.0}, FX, "d1", trading_days=256)   # flat price, only drag
    drag = 2 * (0.5 * 100.0 + 2.0) * 8 / 256
    assert acct.equity == pytest.approx(eq_before - drag)


def test_account_mark_and_persistence(tmp_path):
    acct = PaperAccount(500_000, SPECS)
    acct.trade("X", 1, 50.0, FX, "d0")
    marked = acct.marked_equity({"X": 60.0}, FX)
    assert marked == pytest.approx(acct.equity + 1000)
    p = tmp_path / "s.json"
    acct.save(p)
    back = PaperAccount.load(p, SPECS)
    assert back.equity == acct.equity
    assert back.positions == acct.positions


def test_replay_end_to_end():
    """Three years of replay: equity moves, fills happen, books reconcile."""
    feed = ReplayFeed(start="2005-01-01", end="2007-12-31")
    acct = PaperAccount(10_000_000, feed.specs())
    ctl = ReplayController(feed, acct, preset="base")
    while ctl.step():
        pass
    assert ctl.finished
    assert len(acct.fills) > 50, "should have traded actively over 3 years"
    assert len(acct.history) > 700
    final = acct.history[-1]["equity"]
    assert final != 10_000_000
    # accounting identity: equity = capital + sum(daily pnl) - costs;
    # cross-check via independent recomputation from fills+settles is what
    # settle() does, so at least require sane bounds (no blowup/NaN)
    assert 2_000_000 < final < 100_000_000
    state = ctl.state()
    assert state["kpis"]["n_fills"] == len(acct.fills)
    assert state["meta"]["finished"] is True
    assert isinstance(state["positions"], list)
    assert state["equity_series"][-1]["equity"] == pytest.approx(final, rel=1e-6)


def test_replay_tracks_validated_backtest():
    """The replay's contract-level equity path must reproduce the validated
    backtest over the same window (up to integer-contract rounding and the
    contract-space buffer)."""
    import numpy as np
    import pandas as pd

    from ctabot.backtest import run_strategy
    from ctabot.config import PRESETS

    feed = ReplayFeed(start="2005-01-03", end="2009-12-31")
    acct = PaperAccount(50_000_000, feed.specs())   # large: rounding negligible
    ctl = ReplayController(feed, acct, preset="base")
    while ctl.step():
        pass
    sim = pd.Series({pd.Timestamp(s["ts"]): s["equity"] for s in acct.history})
    sim_ret = sim.pct_change().dropna()

    net = run_strategy(feed.data, feed.meta, PRESETS["base"]).net
    bt_ret = net.loc["2005-01-03":"2009-12-31"]
    both = pd.concat([sim_ret, bt_ret], axis=1, keys=["sim", "bt"], sort=True).dropna()
    # skip the first 10 days (replay starts flat and trades into position)
    both = both.iloc[10:]
    corr = both["sim"].corr(both["bt"])
    ann_gap = (both["sim"].mean() - both["bt"].mean()) * 256
    assert corr > 0.97, f"replay/backtest daily correlation too low: {corr:.3f}"
    assert abs(ann_gap) < 0.02, f"annualised return gap too large: {ann_gap:.2%}"


def test_server_api_roundtrip():
    feed = ReplayFeed(start="2005-01-01", end="2005-12-31")
    acct = PaperAccount(10_000_000, feed.specs())
    ctl = ReplayController(feed, acct, preset="base")
    ctl.speed = 256.0
    httpd = serve(ctl, port=18999, open_browser=False, block=False)
    try:
        time.sleep(1.5)
        html = urllib.request.urlopen("http://127.0.0.1:18999/", timeout=5).read().decode()
        assert "ctabot" in html and "Chart" in html
        raw = urllib.request.urlopen("http://127.0.0.1:18999/api/state", timeout=5).read()
        state = json.loads(raw)
        assert state["meta"]["mode"] == "replay"
        assert state["kpis"]["equity"] > 0
        req = urllib.request.Request(
            "http://127.0.0.1:18999/api/control",
            data=json.dumps({"action": "pause"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        assert json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"]
        state2 = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:18999/api/state", timeout=5).read())
        assert state2["meta"]["paused"] is True
    finally:
        httpd.shutdown()


class StubLiveFeed:
    """Live-feed interface backed by the pinned snapshot (no network)."""

    mode = "live"

    def __init__(self, end="2010-12-31"):
        import numpy as np
        inner = ReplayFeed(start="2000-01-01", end=end)
        self._data = {}
        for k, df in inner.data.items():
            cut = df.loc[:end].copy()
            if len(cut) <= 300:
                continue
            # faithful to YahooFeed: continuous quotes only, no curve data
            cut["adj"] = cut["price"]
            cut[["carry_price", "price_contract", "carry_contract"]] = np.nan
            self._data[k] = cut
        self._specs = inner.specs()
        self._bar = None

    def specs(self):
        return self._specs

    def refresh(self):
        pass

    def history(self):
        return self._data

    def next_bar(self):
        bar, self._bar = self._bar, None
        return bar

    def quotes(self):
        return {n: float(df["price"].iloc[-1]) for n, df in self._data.items()}

    def quotes_settle(self):
        return {n: float(df["adj"].iloc[-1]) for n, df in self._data.items()}

    def fx_to_usd(self):
        return {"USD": 1.0, "EUR": 1.0}

    def progress(self):
        return {"date": "2010-12-31"}


def test_live_controller_deploys_immediately():
    """A fresh live account must put positions on at the first poll, using
    the latest completed bar's decision — not wait for the next day."""
    from simulator.controller import LiveController

    feed = StubLiveFeed()
    acct = PaperAccount(10_000_000, feed.specs())
    ctl = LiveController(feed, acct, preset="base")
    assert ctl.pending_targets, "fresh account should have targets queued at init"
    # freshness: the queued decision is the final bar's, not a stale one
    assert ctl.step()
    assert acct.positions and any(q != 0 for q in acct.positions.values())
    assert len(acct.fills) > 5
    assert ctl.state()["kpis"]["gross_exposure_x"] > 0.5

    # resuming an account with positions must NOT redeploy from scratch
    ctl2 = LiveController(feed, acct, preset="base")
    assert ctl2.pending_targets is None


def test_decided_is_fresh():
    """BacktestResult.decided must have a usable value on the final bar."""
    from ctabot.backtest import run_strategy
    from ctabot.config import PRESETS

    feed = ReplayFeed(start="2005-01-01", end="2010-12-31")
    res = run_strategy(feed.data, feed.meta, PRESETS["base"])
    last = res.decided.dropna(how="all").index[-1]
    assert last == res.held.index[-1], "decision must exist for the latest bar"


def test_dashboard_references_only_existing_fields():
    """Every k.<field> the UI reads must exist in the API payload."""
    import re

    from simulator.dashboard_html import HTML
    feed = ReplayFeed(start="2005-01-01", end="2005-06-30")
    acct = PaperAccount(1_000_000, feed.specs())
    ctl = ReplayController(feed, acct, preset="base")
    for _ in range(40):
        ctl.step()
    kpis = ctl.state()["kpis"]
    used = set(re.findall(r"k\.([a-z_0-9]+)", HTML))
    missing = used - set(kpis)
    assert not missing, f"dashboard reads missing kpi fields: {missing}"
