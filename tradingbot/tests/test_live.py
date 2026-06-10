import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctabot.config import StrategyConfig
from ctabot.live import PaperBroker, buffer_in_contracts, compute_targets
from tests.test_engine import synth_universe

CFG = StrategyConfig(forecast_scalar_min_periods=100, vol_min_periods=50,
                     idm_min_periods=300)


def test_compute_targets_and_orders(tmp_path):
    data, meta = synth_universe()
    book = compute_targets(data, meta, capital_usd=1_000_000, cfg=CFG)
    assert book.asof == str(data["SYN0"].index[-1].date())
    assert {"forecast", "notional_frac", "target_contracts"} <= set(book.targets.columns)
    # contract conversion identity: notional = contracts * contract value
    row = book.targets.dropna().iloc[0]
    assert abs(row["target_contracts"] * row["contract_value_usd"]
               - row["notional_frac"] * 1_000_000) < 1e-6

    buf = buffer_in_contracts(book, meta, CFG)
    state = tmp_path / "paper.json"
    broker = PaperBroker(state)
    orders = book.orders_against(broker.positions(), buf)
    assert orders, "fresh account should generate at least one order"
    broker.submit(orders, book.asof)

    # idempotence: after filling, re-running produces no orders
    broker2 = PaperBroker(state)
    again = book.orders_against(broker2.positions(), buf)
    assert again == []
    saved = json.loads(state.read_text())
    assert len(saved["fills"]) == len(orders)


def test_non_usd_skipped_without_fx():
    data, meta = synth_universe()
    meta.loc["SYN0", "currency"] = "EUR"
    book = compute_targets(data, meta, capital_usd=1_000_000, cfg=CFG)
    assert "SYN0" not in book.targets.index
    book_fx = compute_targets(data, meta, capital_usd=1_000_000, cfg=CFG,
                              fx_to_usd={"EUR": 1.1})
    assert "SYN0" in book_fx.targets.index
