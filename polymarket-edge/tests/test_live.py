import json

import pytest

from polyedge.live.execution import OrderIntent, PaperExecutor
from polyedge.live.gateway import Book, BookLevel
from polyedge.live.risk import PortfolioView, RiskLimits, RiskManager


def book(token, asks, bids=()):
    return Book(
        token_id=token,
        asks=[BookLevel(p, s) for p, s in asks],
        bids=[BookLevel(p, s) for p, s in bids],
        ts=0.0,
    )


def intent(token="t1", price=0.95, usd=10.0, group=None, market="m1"):
    return OrderIntent(strategy="test", market_id=market, event_id="e1",
                       token_id=token, side="BUY", limit_price=price,
                       usd=usd, edge=0.05, reason="r", all_or_none_group=group)


def test_paper_fill_walks_asks(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=100.0)
    b = {"t1": book("t1", asks=[(0.90, 5.0), (0.95, 100.0)])}
    res = ex.execute_batch([intent(price=0.95, usd=10.0)], b)
    assert res[0]["status"] == "filled"
    # 5 shares at .90 = $4.5, remaining $5.5 at .95
    shares = 5.0 + 5.5 / 0.95
    assert res[0]["shares"] == pytest.approx(shares)
    assert ex.state["cash"] == pytest.approx(90.0)
    pos = ex.state["positions"]["t1"]
    assert pos["shares"] == pytest.approx(shares)


def test_paper_respects_limit_price(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=100.0)
    b = {"t1": book("t1", asks=[(0.97, 100.0)])}
    res = ex.execute_batch([intent(price=0.95, usd=10.0)], b)
    assert res[0]["status"] == "unfilled"
    assert ex.state["cash"] == 100.0


def test_aon_group_all_or_nothing(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=100.0)
    books = {
        "t1": book("t1", asks=[(0.40, 100.0)]),
        "t2": book("t2", asks=[(0.45, 0.5)]),  # not enough depth
    }
    legs = [intent("t1", 0.41, 10.0, group="g"), intent("t2", 0.46, 10.0, group="g")]
    res = ex.execute_batch(legs, books)
    assert all(r["status"] == "aon_unfillable" for r in res)
    assert ex.state["cash"] == 100.0
    # with depth fixed, both fill
    books["t2"] = book("t2", asks=[(0.45, 100.0)])
    res = ex.execute_batch(legs, books)
    assert all(r["status"] == "filled" for r in res)


def test_paper_settlement(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=100.0)
    b = {"t1": book("t1", asks=[(0.50, 100.0)])}
    ex.execute_batch([intent(price=0.55, usd=10.0)], b)
    evs = ex.settle({"t1": 1.0})
    assert len(evs) == 1
    assert ex.state["cash"] == pytest.approx(90.0 + 20.0)  # 20 shares * $1
    assert ex.state["positions"] == {}
    # state survives reload
    ex2 = PaperExecutor(tmp_path / "s.json")
    assert ex2.state["cash"] == pytest.approx(110.0)


def test_risk_caps_and_halt():
    rm = RiskManager(RiskLimits(max_order_usd=50, max_market_usd=80,
                                max_gross_usd=100, min_edge=0.01,
                                drawdown_kill_frac=0.10))
    view = PortfolioView(equity=100, start_equity=100, gross_exposure=70,
                         market_exposure={"m1": 60}, event_exposure={})
    ok, why = rm.approve(market_id="m1", event_id=None, price=0.5, usd=30,
                         spread=0.01, edge=0.05, view=view)
    assert not ok and "market exposure" in why
    ok, why = rm.approve(market_id="m2", event_id=None, price=0.5, usd=40,
                         spread=0.01, edge=0.05, view=view)
    assert not ok and "gross" in why
    ok, why = rm.approve(market_id="m2", event_id=None, price=0.5, usd=20,
                         spread=0.01, edge=0.001, view=view)
    assert not ok and "edge" in why
    ok, why = rm.approve(market_id="m2", event_id=None, price=0.5, usd=20,
                         spread=0.01, edge=0.05, view=view)
    assert ok
    rm.check_portfolio(PortfolioView(equity=85, start_equity=100,
                                     gross_exposure=0))
    assert rm.halted
    ok, why = rm.approve(market_id="m2", event_id=None, price=0.5, usd=20,
                         spread=0.01, edge=0.05, view=view)
    assert not ok and "halted" in why


def test_buy_cost_depth():
    b = book("t", asks=[(0.50, 10.0), (0.60, 10.0)])
    avg, shares = b.buy_cost(8.0)
    # $5 at .5 -> 10 sh, $3 at .6 -> 5 sh
    assert shares == pytest.approx(15.0)
    assert avg == pytest.approx(8.0 / 15.0)
    assert b.buy_cost(100.0) is None


def test_aon_group_respects_cash(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=15.0)
    books = {
        "t1": book("t1", asks=[(0.50, 1000.0)]),
        "t2": book("t2", asks=[(0.50, 1000.0)]),
    }
    legs = [intent("t1", 0.55, 10.0, group="g"), intent("t2", 0.55, 10.0, group="g")]
    res = ex.execute_batch(legs, books)
    assert all(r["status"] == "aon_unfillable" for r in res)
    assert ex.state["cash"] == 15.0


def test_gate_batch_cumulative_exposure(tmp_path):
    import asyncio

    from polyedge.live.bot import Bot
    from polyedge.live.risk import RiskLimits

    bot = Bot.__new__(Bot)  # avoid network-touching __init__
    bot.params = {}
    bot.live = False
    bot.paper = PaperExecutor(tmp_path / "s.json", start_cash=1000.0)
    from polyedge.live.risk import RiskManager
    bot.risk = RiskManager(RiskLimits(max_order_usd=100, max_market_usd=1000,
                                      max_event_usd=1000, max_gross_usd=150,
                                      min_edge=0.0))
    bot.log_path = tmp_path / "log.jsonl"
    intents = [intent(f"t{i}", 0.5, 60.0, market=f"m{i}") for i in range(4)]
    approved = bot.gate(intents)
    # 60*2=120 <= 150 but 60*3=180 > 150: only two may pass
    assert len(approved) == 2


def test_record_external_fill(tmp_path):
    ex = PaperExecutor(tmp_path / "s.json", start_cash=100.0)
    ex.record_external_fill(intent("t9", 0.50, 10.0))
    assert ex.state["cash"] == pytest.approx(90.0)
    assert ex.state["positions"]["t9"]["shares"] == pytest.approx(20.0)
