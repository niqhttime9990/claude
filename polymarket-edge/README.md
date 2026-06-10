# polyedge — a research-validated Polymarket trading bot

A complete pipeline: **historical data ingestion → rigorous backtests →
live bot armed only with what survived out-of-sample validation.**

The design principle is that the bot refuses to trade a strategy that the
research pipeline hasn't validated: `reports/params.json` is written by the
backtests and read by the bot. No parameters, no trades.

## What's inside

```
pipeline/fetch_data.py     Pulls resolved-market metadata (Gamma) + lifetime
                           price histories (CLOB) + live order-book snapshot.
                           Runs in GitHub Actions (.github/workflows/
                           polymarket-data.yml) and pushes parquet snapshots
                           to the claude/brave-mendel-mvive7-data branch.
polyedge/
  dataio.py                Loading, settle-time detection, snapshotting,
                           empirical spread model (execution haircuts)
  calibration.py           Calibration curves, favorite-longshot bias tests
  strategies.py            Ex-ante signal rules (favorite, momentum, neg-risk)
  backtest.py              Trade accounting, event-cluster bootstrap CIs,
                           walk-forward selection (train pick, frozen OOS)
  stats.py                 Wilson intervals, cluster bootstrap, Sharpe, etc.
  live/                    The bot: gateway (public endpoints), risk gate,
                           paper + real executors, strategy scanners
research/run_research.py   Produces reports/REPORT.md, figures, params.json
tests/                     19 tests incl. an explicit no-lookahead test
```

## The edges (and what the data says)

1. **Neg-risk structural arbitrage** — in a "negative risk" event (mutually
   exclusive & exhaustive outcomes), one full set of NO shares pays exactly
   `n-1`; whenever the set trades below that (equivalently sum of YES asks
   > 1 on the other side), buying the basket locks a deterministic profit.
   This is a true arbitrage, not a statistical bet. The live scanner prices
   full baskets against real order books and fires all-or-none (FOK) legs.
   The backtest chapter measures how often mid-level mispricings appeared
   historically; execution certainty exists only at the moment of the scan.

2. **Favorite carry** — buying heavy favorites in their final days. Whether
   this clears transaction costs is exactly what the walk-forward decides;
   see `reports/REPORT.md`. The bot arms it only if the out-of-sample
   confidence interval excludes zero.

3. **Momentum / underreaction** — measured at 12h fidelity in the report as
   evidence; deliberately **not armed** in the live bot (the public API only
   serves 12h-fidelity history for resolved markets, so live execution at
   finer horizons would be trading a different strategy than the backtest).

Read `reports/REPORT.md` for the actual numbers, full parameter grids,
cluster-bootstrap confidence intervals, cost sensitivity, and the
multiple-testing accounting.

## Run the research

```bash
pip install -r requirements.txt
# data/ comes from the data branch:
git fetch origin claude/brave-mendel-mvive7-data
git --work-tree=polymarket-edge/data checkout origin/claude/brave-mendel-mvive7-data -- .
cd polymarket-edge
python research/run_research.py --data data --out reports --cutoff 2025-12-01
pytest tests/
```

To refresh the dataset, re-run the `polymarket-data` workflow (push any
change under `polymarket-edge/pipeline/` or trigger it manually), or run
`python pipeline/fetch_data.py --out data` on any machine with open egress.

## Run the bot

```bash
# one-shot scan, prints intents, places nothing:
python -m polyedge.cli scan

# paper trading loop (default; state in state/paper_state.json):
python -m polyedge.cli paper --stake 25

# real money (after a long paper run, at your own risk):
pip install -r requirements-live.txt
export POLY_PRIVATE_KEY=0x...        # Polygon key holding USDC
# export POLY_FUNDER=0x...           # if using a Polymarket proxy wallet
python -m polyedge.cli live --i-accept-real-money-risk
```

The bot needs egress to `gamma-api.polymarket.com` and
`clob.polymarket.com`. Risk limits live in `polyedge/live/risk.py`
(per-order/market/event/gross caps, daily order cap, spread cap, price
bands, drawdown kill switch); every order is logged with the limit that
approved or rejected it (`state/bot_log.jsonl`).

## Honesty section

- Backtests fill at mid + an empirical half-spread by liquidity tier,
  measured from a live order-book snapshot; real fills can be worse in thin
  books or fast markets. Cost sensitivity (0x/1x/2x haircuts) is in the
  report.
- Polymarket charges no trading fees on most markets today; a fee would eat
  thin edges first. Gas is relayer-covered for CLOB orders.
- Lifetime volume is used as the liquidity filter (slightly forward-looking
  as a *filter*, not as a signal); capacity estimates assume small stakes
  relative to book depth.
- Past favorite-carry premia can compress as more bots harvest them. The
  neg-risk basket arb is structural but competitive — speed matters.
- Nothing here is financial advice; prediction markets can be illegal in
  some jurisdictions. Know your local rules.
