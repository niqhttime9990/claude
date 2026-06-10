# ctabot — systematic trend + carry futures strategy

A complete, tested, multi-asset systematic trading system: diversified
trend-following and futures carry with volatility targeting, over 23 liquid
futures markets (equity indices, government bonds, metals, energy,
agriculturals), backed by ~50 years of real daily futures data, a
lookahead-safe backtest engine with measured per-instrument costs, and a
statistical validation suite built to answer one question honestly:

> **Is this distinguishable from luck, after costs, out of sample, and after
> accounting for every variant that was tried?**

The result (details below): full-sample net Sharpe ≈ 0.7 over 49 years,
positive and significant under a block bootstrap, surviving a deflated-Sharpe
multiple-testing correction and a placebo test — but with a clearly weaker
last decade, exactly as the published literature says. This is a real but
modest and slowly decaying edge, not a money printer.

**This is research code, not investment advice. Futures are leveraged
instruments; this strategy's own backtest contains a 7-year drawdown.
Do not trade money you cannot afford to lose.**

---

## The edge, and why it might be real

This strategy combines two return premia with distinct economic foundations:
time-series momentum (trend-following) and futures carry. Both have long
academic pedigrees, both have structural explanations that do not depend on
mispricing alone, and both have real drawbacks that a skeptical reader
should weigh.

### Time-series momentum

Moskowitz, Ooi, and Pedersen (2012, *Journal of Financial Economics*)
documented that buying recent winners and selling recent losers across 58
futures markets — equities, bonds, currencies, commodities — produced
positive risk-adjusted returns over 25+ years. The effect was not
concentrated in a single asset class or time window. Hurst, Ooi, and
Pedersen (2017, AQR) extended this backward through historical records
covering roughly 140 years, finding that trend-following delivered positive
Sharpe ratios in nearly every decade, including through major crises.

Two behavioral mechanisms are invoked to explain this. Early in a trend,
investors underreact: anchoring to prior prices and the slow diffusion of
fundamental information cause prices to adjust gradually rather than
immediately. Later, extrapolation and herding extend the move beyond fair
value before a reversal. Neither mechanism requires the majority of market
participants to be irrational simultaneously — only that the marginal
price-setter is often slow or momentum-driven.

A structural mechanism is arguably more durable: large, non-profit-seeking
flows. Central banks smoothing exchange rates, commodity producers hedging
output, and risk-managed funds mechanically increasing or decreasing
exposure as volatility changes are not trying to maximize Sharpe. They
create and sustain trends as a byproduct of institutional mandates. This
matters because it identifies a source of premium that does not disappear
merely because traders notice it.

### Futures carry

Koijen, Moskowitz, Pedersen, and Vrugt (2018, *JFE*) documented that carry —
the return to holding an asset assuming prices stay constant — predicts
returns across asset classes. The economic story differs by class. In
commodities, Keynes' "normal backwardation": producers pay speculators a
premium to absorb inventory price risk. Bond carry compensates duration and
funding risk. Carry and trend have low correlation in practice (≈0.2 in
this implementation), so the combination diversifies: carry earns in stable
markets, trend earns in persistent moves.

### Why these premia might persist — and why they might not

The limits-to-arbitrage case: both strategies require leverage, shorting,
and the willingness to sit through multi-year drawdowns. Agency-constrained
institutional capital cannot do this; a manager who underperforms for three
years loses assets before the premium pays. The counterparties — hedgers
and mechanical flows — are not competed away because they are not trying to
win this game.

Honesty requires acknowledging the decay: post-2010 trend Sharpe is roughly
half its pre-2010 level (visible in this backtest too — see the rolling
Sharpe figure), the managed-futures industry runs hundreds of billions of
dollars, and crowding produces synchronized drawdowns. The premium is
partially competed. There is no guarantee of persistence.

### What would falsify the edge

Treat the edge as falsified if live returns fall persistently outside the
lower tail of the backtest's bootstrap distribution (not one bad year — a
sustained pattern), or if industry-wide trend/carry returns are
statistically indistinguishable from zero over a full cycle. Either outcome
warrants halting, not rationalizing.

---

## What's in the box

```
tradingbot/
├── ctabot/
│   ├── config.py      # all parameters, fixed a priori from the literature
│   ├── data.py        # pinned data snapshot, integrity manifest, returns/carry math
│   ├── signals.py     # EWMAC, breakout, carry forecasts; expanding lagged scaling
│   ├── portfolio.py   # vol targeting, class risk parity, IDM, buffering
│   ├── backtest.py    # engine: execution lag, spread+commission+roll costs
│   ├── stats.py       # block bootstrap, PSR/DSR, placebo tests
│   ├── report.py      # figures + markdown report
│   └── live.py        # target book -> integer contracts -> orders; paper broker
├── scripts/
│   ├── fetch_data.py      # re-download the pinned snapshot
│   ├── run_backtest.py    # quick summary
│   ├── run_validation.py  # full statistical validation (writes reports/)
│   └── run_live.py        # today's orders (dry-run / paper)
├── data/              # committed snapshot (2.1 MB) + sha256 manifest
├── reports/           # generated: REPORT.md, results.json, figures/
└── tests/             # incl. hard no-lookahead invariance tests
```

### Strategy, in one paragraph

For each of 23 futures markets, six forecasts are computed daily: three
EWMA crossovers (16/64, 32/128, 64/256 days), two channel breakouts (80,
160 days) — together the trend sleeve, 60% weight — and annualized
roll-yield over volatility (carry sleeve, 40%). Forecasts are scaled to a
common expected magnitude using only past data, capped, combined, and
turned into positions by volatility targeting: each instrument is sized to
contribute equal risk within its asset class, each class equally, scaled by
an estimated diversification multiplier, to a 20% annualized portfolio vol
target. A ±10% buffer suppresses trades that wouldn't move the position
materially. Signals decided at close *t* execute at close *t+1* and pay
measured per-instrument spread + commission + roll costs.

## Methodology: how the backtest earns trust

- **No lookahead, enforced by test.** `tests/test_engine.py` verifies that
  truncating the data or corrupting all prices after a date leaves every
  earlier daily return bit-identical. Every estimated quantity (forecast
  scalars, vols, diversification multiplier, class weights) is expanding or
  rolling and lagged.
- **Parameters fixed a priori.** Every number in `config.py` is a published
  default from Carver (*Systematic Trading*, 2015) or the academic papers
  above — chosen before the first backtest ran and not changed after.
  Development history (verifiable from git): the only post-first-run code
  changes were turnover bug fixes (holiday-gap churn) and a carry
  contract-label parsing fix verified against external facts (gold carry ≈
  −funding rate), not signal tuning.
- **Out-of-sample discipline.** The config declares `insample_end =
  2014-12-31`: all design choices replicate pre-2015 published work, so
  2015→2024 is structurally out-of-sample — and it is reported separately
  everywhere.
- **Costs are real and stressed.** Per-instrument half-spreads from
  pysystemtrade's measured `spreadcosts.csv`, $1.50/contract commission,
  plus roll costs charged `rolls_per_year` times annually on held notional.
  Sensitivity grid re-runs everything at 0.5×, 2×, 5× costs.
- **Execution is pessimistic.** One full day between signal and fill
  (sensitivity includes same-close and two-day variants).
- **Multiple testing is accounted for.** Every config variant evaluated in
  this project feeds the Deflated Sharpe Ratio (Bailey & López de Prado
  2014); the placebo test runs randomly time-shifted forecasts through the
  identical engine to measure how much Sharpe the machinery can produce
  from zero information.

## Results

See [reports/REPORT.md](reports/REPORT.md) for the full generated report
with all tables and figures. Headline numbers from the committed run are in
the "Validation results" section below.

## How to run

```bash
cd tradingbot
pip install -r requirements.txt
python -m pytest tests/ -q          # engine correctness, incl. no-lookahead
python scripts/run_backtest.py      # quick summary
python scripts/run_validation.py    # full suite (~10 min), writes reports/
python scripts/run_live.py --capital 250000 --eurusd 1.08          # dry run
python scripts/run_live.py --capital 250000 --paper                # paper trading
```

The committed `data/` snapshot reproduces the report exactly. To refresh
data, `python scripts/fetch_data.py` re-downloads the pinned upstream
commit (edit `DATA_SHA` in `config.py` to move the pin; the manifest
records the sha256 of every payload).

## Going live (read this before even paper trading)

1. **Data.** The committed snapshot ends 2024-03-28 (the pinned upstream
   commit). Live trading needs a maintained daily feed for the same
   instruments — e.g. Norgate, CSI, Barchart, or broker data — plugged in
   at `ctabot/data.py::load_universe`. The pysystemtrade repo data updates
   only sporadically; do not trade off a stale snapshot.
2. **Capital.** At $250k with full-size contracts, many instruments round
   to 0–2 contracts: position granularity meaningfully degrades the
   diversification. Micro/mini contracts (MES, MGC, MCL, …) or more capital
   fix this; below ~$100k with full-size contracts this strategy does not
   implement faithfully.
3. **Brokers.** `PaperBroker` (local JSON) is the only shipped
   implementation, deliberately: it is the only one testable here.
   Implement `ctabot.live.Broker` (two methods) for e.g. Interactive
   Brokers, run paper for months first, compare realized turnover and
   slippage against the backtest's assumptions, and start at minimum size.
4. **Risk.** The backtest's worst drawdown is ~−40% at the 20% vol target,
   and its longest high-water-mark gap is roughly seven years. If that is
   not survivable — financially or psychologically — run a lower
   `vol_target_annual` or do not run this at all.

## Honest limitations

- **Historical costs are understated before ~2005.** Spreads are today's
  measurements applied to all of history; pit-era trading was several times
  more expensive. The 0.5×/2×/5× cost stress brackets this, and the
  out-of-sample decade uses realistic costs, but pre-2000 net numbers are
  optimistic.
- **Instrument-selection survivorship.** The universe is today's liquid
  markets, chosen for liquidity and class coverage before any backtest ran
  — but markets that died (pork bellies, lumber's liquidity collapse) are
  absent. Published research (e.g. the 140-year AQR study) suggests the
  trend effect is not an artifact of market selection, but the bias exists.
- **Single data vendor.** Back-adjusted continuous prices embed roll-date
  and adjustment choices. The carry signal uses the vendor's choice of
  carry contract. Cross-vendor replication was not possible in this
  environment (network policy); the data layer verifies integrity by
  sha256, not by cross-source agreement.
- **EUR instruments (EUROSTX, BUND)** are sized in local-currency percent
  terms; USD conversion of their P&L is ignored in the backtest
  (second-order at these weights) and handled by a manual FX input in the
  live runner.
- **Returns are excess-of-cash.** Futures margin earns interest; total
  return at the account level adds roughly T-bill yield on unencumbered
  cash, which the backtest does not credit. (This makes reported numbers
  conservative, not optimistic.)
- **The last decade is the weakest decade.** That is what the literature
  predicts (crowding), and what you should extrapolate from — not the
  1990s.

## Validation results

From the committed run ([full report](reports/REPORT.md), regenerate with
`python scripts/run_validation.py`). All numbers net of costs, one-day
execution lag, 20% vol target.

| | ann. return | ann. vol | Sharpe | max DD |
|---|---|---|---|---|
| **Full sample 1975–2024** | 14.0% | 19.1% | **0.73** | −47% |
| In-sample (≤ 2014) | 16.2% | 19.9% | 0.82 | −47% |
| **Out-of-sample (2015–2024)** | 5.5% | 15.9% | **0.35** | −29% |
| Long-only risk parity (same engine) | 10.5% | 17.9% | 0.59 | −75% |
| S&P 500, vol-targeted (same engine) | 8.3% | 18.1% | 0.46 | −58% |

Correlation of the strategy to the long-only benchmark is **0.06** and to
vol-targeted S&P **0.12**: whatever this is, it is not repackaged market
beta. Every asset class contributes positive Sharpe (bonds 0.58, ags 0.52,
energy 0.34, metals 0.24, equities 0.20). 2022 — the year stocks and bonds
fell together — was a +17% year, the classic crisis-convexity profile.

**Significance.**
- Stationary block bootstrap (10,000 reps): full-sample SR 95% CI
  **[0.46, 1.00]**, p(SR ≤ 0) < 10⁻⁴.
- Deflated Sharpe Ratio across the 33 configurations evaluated in this
  project: ≈ 1.000 (hurdle SR* = 0.18).
- Placebo: 200 runs with every instrument's forecast circularly shifted by
  a random ≥ 1-year offset through the identical engine produce null
  Sharpe 0.22 ± 0.14 (max 0.57). The real 0.73 lies outside the entire
  null distribution (p = 0.000). Note the null mean is *positive* — the
  machinery collects some static risk premium with zero information — so
  this test correctly sets the bar above zero.
- Out-of-sample alone: SR 0.35, bootstrap CI [−0.25, 0.98], p = 0.12 —
  positive but **not independently significant**. Nine years of a
  Sharpe-0.35 process is simply too short to reject zero; this is the
  honest state of the evidence for the post-publication era, and it matches
  the industry-wide finding that trend Sharpe roughly halved post-2010.

**Sensitivity.** Every variation tried sits on a plateau: full-sample SR
0.67–0.75 across signal subsets, vol estimators, buffers, caps, execution
lags, and 0.5×/2× costs. Only 5× costs (SR 0.54) and carry-only (0.31)
leave the plateau. Nothing about the result depends on a magic parameter.

**A temptation resisted.** Trend-only (SR 0.75 full, 0.42 OOS) slightly
beats the 60/40 trend/carry combination (0.73 full, 0.35 OOS): in this
universe the carry sleeve standalone is weak (0.31 full, ≈ 0.00 OOS — no
FX or rates-curve markets where carry is strongest, and commodity carry has
crowded). Dropping carry *now, because of these numbers,* would be exactly
the in-sample selection this repo exists to avoid, so the a priori 60/40
design stands and both variants are reported. A defensible redesign would
add the missing carry-rich asset classes, not delete the sleeve after
peeking.

## References

- Moskowitz, Ooi, Pedersen (2012). *Time Series Momentum.* JFE 104(2).
- Koijen, Moskowitz, Pedersen, Vrugt (2018). *Carry.* JFE 127(2).
- Hurst, Ooi, Pedersen (2017). *A Century of Evidence on Trend-Following
  Investing.* Journal of Portfolio Management 44(1).
- Carver (2015). *Systematic Trading.* Harriman House. (Forecast scaling,
  buffering, vol targeting and the 60/40 trend/carry default.)
- Bailey, López de Prado (2014). *The Deflated Sharpe Ratio.* Journal of
  Portfolio Management 40(5).
- Politis, Romano (1994). *The Stationary Bootstrap.* JASA 89(428).
- Data: [robcarver17/pysystemtrade](https://github.com/robcarver17/pysystemtrade)
  futures data, pinned at commit `883c868`, sha256-manifested in
  `data/manifest.json`.
