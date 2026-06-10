# Polymarket edge research report

- markets in dataset: **63,255** (clean binary resolutions: **63,151**, ties/invalid: 94, unparseable: 10)
- price rows (12h fidelity): **1,864,792** across 53,640 markets
- total lifetime volume covered: **$25.94B**
- price data through: **2026-01-05**
- walk-forward cutoff (signals before=train, after=test): **2025-06-01**
- execution haircut model: `{'tiers': [0.0, 10000.0, 100000.0], 'half_spread': [0.005, 0.005, 0.005], 'source': 'active_book_snapshot', 'n_books': 411}`


## 1. Calibration / favorite-longshot bias

Snapshot = last mid at horizon h before the settle flatline (see dataio.settle_time). Wilson 95% intervals; FLB regression `outcome - p ~ a + b(p - 0.5)` with event-cluster-robust errors.

**24h before resolution** (n=30,577): FLB slope b=0.0218 (t=3.1, p=0.0019) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0247 (p=4.3e-05, n=23,773)
  - vol>=100k: b=0.0257 (p=0.0019, n=10,007)
  - cat:crypto: b=0.0377 (p=0.001, n=5,854)
  - cat:entertainment: b=0.0301 (p=0.093, n=1,166)
  - cat:geopolitics: b=0.0685 (p=0.021, n=914)
  - cat:other: b=0.0154 (p=0.18, n=6,963)
  - cat:politics: b=0.0233 (p=0.054, n=5,017)
  - cat:sports: b=-0.0009 (p=0.96, n=10,071)
  - cat:tech_ai: b=-0.0059 (p=0.82, n=330)


Gross (cost-free) expected returns by zone at 24h:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 5770 |    0.0229506 |  0.0121317 |      -0.510344  |      0.0111109 |
| [0.05,0.10) | 1812 |    0.0700132 |  0.0540839 |      -0.249861  |      0.0170704 |
| [0.90,0.95) |  407 |    0.925461  |  0.968059  |       0.0461588 |     -0.576242  |
| [0.95,0.99) |  942 |    0.975118  |  0.990446  |       0.0157487 |     -0.660039  |
| [0.97,0.99) |  637 |    0.982194  |  0.99686   |       0.0149826 |     -0.753653  |

**72h before resolution** (n=22,574): FLB slope b=0.0149 (t=1.9, p=0.06) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0177 (p=0.023, n=18,547)
  - vol>=100k: b=0.0240 (p=0.018, n=8,630)
  - cat:crypto: b=0.0299 (p=0.12, n=3,723)
  - cat:entertainment: b=0.0063 (p=0.83, n=969)
  - cat:geopolitics: b=0.0652 (p=0.061, n=806)
  - cat:other: b=0.0249 (p=0.08, n=5,328)
  - cat:politics: b=0.0084 (p=0.56, n=4,254)
  - cat:sports: b=0.0010 (p=0.96, n=6,932)
  - cat:tech_ai: b=0.0403 (p=0.094, n=303)


Gross (cost-free) expected returns by zone at 72h:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 4611 |    0.0240631 |  0.0177836 |      -0.293134  |     0.00646599 |
| [0.05,0.10) | 1824 |    0.071477  |  0.0597588 |      -0.180442  |     0.0125841  |
| [0.90,0.95) |  339 |    0.925824  |  0.943953  |       0.0197281 |    -0.240074   |
| [0.95,0.99) |  692 |    0.974491  |  0.99422   |       0.0203343 |    -0.785091   |
| [0.97,0.99) |  468 |    0.981431  |  0.997863  |       0.0167923 |    -0.835635   |

**7d before resolution** (n=13,287): FLB slope b=0.0209 (t=2.3, p=0.021) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0285 (p=0.002, n=11,271)
  - vol>=100k: b=0.0519 (p=1.9e-05, n=5,647)
  - cat:crypto: b=0.1896 (p=1.8e-05, n=726)
  - cat:entertainment: b=-0.0640 (p=0.12, n=710)
  - cat:geopolitics: b=0.0134 (p=0.8, n=669)
  - cat:other: b=0.0057 (p=0.75, n=3,722)
  - cat:politics: b=0.0142 (p=0.34, n=3,199)
  - cat:sports: b=0.0388 (p=0.058, n=3,764)


Gross (cost-free) expected returns by zone at 7d:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 3365 |    0.0233741 |  0.0187221 |      -0.311118  |     0.00470991 |
| [0.05,0.10) | 1178 |    0.0712318 |  0.0509338 |      -0.292534  |     0.0218627  |
| [0.90,0.95) |  191 |    0.926175  |  0.95288   |       0.0290453 |    -0.354654   |
| [0.95,0.99) |  439 |    0.975266  |  0.995444  |       0.0207714 |    -0.868891   |
| [0.97,0.99) |  313 |    0.981224  |  1         |       0.019168  |    -1          |


## 2. Favorite strategy — walk-forward

Rule: in the final W days before end_date, first bar with p >= θ buys YES (p <= 1-θ buys NO) at mid + tiered half-spread; hold to resolution. Max 2 trades/event; min lifetime volume $10k. Grid below is fully disclosed; the chosen cell maximizes the train CI lower bound and is then frozen for OOS.


Train grid (top 10 by CI lower bound):

| cell                |   n_trades |   mean_ret |        ci_lo |      ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:--------------------|-----------:|-----------:|-------------:|-----------:|--------:|-----------:|--------------------:|
| fav θ=0.93 W=1d yes |        532 | 0.0119606  |  1.36749e-05 | 0.0217257  | 0.025   |   0.984962 |            1.63668  |
| fav θ=0.93 W=7d yes |        789 | 0.00939478 | -0.00255508  | 0.0202406  | 0.0575  |   0.974651 |            1.27419  |
| fav θ=0.95 W=7d yes |        650 | 0.00706179 | -0.00321558  | 0.0161688  | 0.08625 |   0.984615 |            1.13579  |
| fav θ=0.9 W=3d yes  |        755 | 0.010141   | -0.00336696  | 0.023114   | 0.06925 |   0.968212 |            1.20371  |
| fav θ=0.9 W=7d yes  |        905 | 0.0091593  | -0.00410138  | 0.0210467  | 0.0885  |   0.962431 |            1.09397  |
| fav θ=0.9 W=1d yes  |        608 | 0.00944096 | -0.00438627  | 0.0219737  | 0.0875  |   0.973684 |            1.07015  |
| fav θ=0.97 W=1d yes |        331 | 0.00454715 | -0.00483115  | 0.0110495  | 0.1375  |   0.993958 |            0.792271 |
| fav θ=0.93 W=3d yes |        666 | 0.00691571 | -0.00587009  | 0.0183475  | 0.1375  |   0.975976 |            0.875504 |
| fav θ=0.95 W=1d yes |        421 | 0.00510513 | -0.00666736  | 0.0147853  | 0.157   |   0.988124 |            0.711761 |
| fav θ=0.97 W=7d yes |        514 | 0.00158696 | -0.00865264  | 0.00982948 | 0.37125 |   0.988327 |            0.268108 |


**Chosen cell:** `fav θ=0.93 W=1d yes` → **out-of-sample**: n=484 trades, mean ret/stake **0.32%** (95% CI [-1.23%, 1.68%], cluster-bootstrap by event), hit rate 97.7%, weekly Sharpe 0.50 (19 wks), max drawdown $-2.9 per $1 stakes, annualized return on peak capital 26.5%.

Multiple-testing note: {'n_cells': 36, 'raw_p': 0.294, 'family_wise_p_bonferroni': 1.0, 'family_wise_p_independent_approx': 0.9999963944689674}


Cost sensitivity (OOS, chosen cell):

| costs          |    mean_ret |       ci_lo |     ci_hi |   n |
|:---------------|------------:|------------:|----------:|----:|
| no costs       |  0.00836012 | -0.00837868 | 0.0215792 | 484 |
| 1x half-spread |  0.00318675 | -0.0134661  | 0.0163352 | 484 |
| 2x half-spread | -0.00146151 | -0.0180537  | 0.011626  | 484 |


Per-quarter stability of the chosen cell (quarters after the cutoff are out-of-sample):

| quarter   |   n |   mean_ret |   ci_lo |   ci_hi | oos   |
|:----------|----:|-----------:|--------:|--------:|:------|
| 2023Q4    |   1 |     0.0204 |  0.0204 |  0.0204 | False |
| 2024Q1    |  33 |    -0.0365 | -0.1302 |  0.0287 | False |
| 2024Q2    |  53 |     0.0051 | -0.0359 |  0.0284 | False |
| 2024Q3    |  69 |     0.0309 |  0.0255 |  0.0372 | False |
| 2024Q4    | 157 |     0.013  | -0.0082 |  0.0277 | False |
| 2025Q1    | 119 |     0.0013 | -0.0325 |  0.0278 | False |
| 2025Q2    | 184 |     0.0176 |  0.0002 |  0.0304 | False |
| 2025Q3    | 399 |     0.003  | -0.0136 |  0.018  | True  |


OOS by category (chosen cell, n>=30):

| category   |   n |   mean_ret |   ci_lo |   ci_hi |
|:-----------|----:|-----------:|--------:|--------:|
| crypto     | 338 |     0.0016 | -0.0175 |  0.0181 |
| other      |  52 |     0.0087 | -0.0351 |  0.0332 |


## 3. Momentum / underreaction — walk-forward

Rule: |Δp| >= δ over 24h, price in [0.10, 0.90], enter at signal bar with the move ('with') or against it ('against'); hold to resolution or time-exit. One trade per market.


Train grid (top 10 by CI lower bound):

| cell                        |   n_trades |   mean_ret |       ci_lo |      ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:----------------------------|-----------:|-----------:|------------:|-----------:|--------:|-----------:|--------------------:|
| mom δ=0.15 against hold=res |       4896 |  0.13408   |  0.0913885  | 0.176628   | 0       |   0.428105 |            3.51593  |
| mom δ=0.15 against hold=7d  |       4896 |  0.124183  |  0.0881456  | 0.160828   | 0       |   0.470588 |            5.00544  |
| mom δ=0.15 against hold=3d  |       4896 |  0.10964   |  0.0799499  | 0.138804   | 0       |   0.487132 |            4.81537  |
| mom δ=0.1 against hold=3d   |       6148 |  0.0543718 |  0.0284641  | 0.0798928  | 0       |   0.466005 |            3.20364  |
| mom δ=0.1 against hold=res  |       6148 |  0.0631864 |  0.0246287  | 0.100151   | 0.00075 |   0.425667 |            2.41518  |
| mom δ=0.1 against hold=7d   |       6148 |  0.0557807 |  0.0232857  | 0.0857041  | 0       |   0.45218  |            3.18881  |
| mom δ=0.05 against hold=7d  |       7551 |  0.0287092 |  0.0015306  | 0.0547779  | 0.02075 |   0.452788 |            1.35808  |
| mom δ=0.05 against hold=3d  |       7551 |  0.0199819 | -0.00184105 | 0.0417711  | 0.0365  |   0.44312  |            1.23026  |
| mom δ=0.05 against hold=res |       7551 |  0.0276975 | -0.00622368 | 0.0601421  | 0.05125 |   0.444312 |            1.12519  |
| mom δ=0.05 with hold=res    |       7551 | -0.0199823 | -0.0453791  | 0.00592728 | 0.9325  |   0.555688 |           -0.822136 |


**Chosen cell:** `mom δ=0.15 against hold=res` → **out-of-sample**: n=2,317, mean ret/stake **12.79%** (95% CI [5.91%, 20.17%]), hit rate 40.5%, weekly Sharpe 4.69.

Multiple-testing note: {'n_cells': 18, 'raw_p': 0.00025, 'family_wise_p_bonferroni': 0.0045000000000000005, 'family_wise_p_independent_approx': 0.004490450238054722}


## 4. Neg-risk structural arbitrage (indicative)

Events analyzed: 3,417; grid snapshots: 173,011. Snapshots with sum-of-YES mispricing beyond per-leg half-spreads (> $0.01/set): **38,047** (21.99%) across **2,655 events**.

These are *mid-based and staleness-filtered but execution-unverified* — treat as an upper bound on frequency and use the live scanner (FOK basket orders) to harvest. Top events:

|   event_id |   max_edge |   n_snaps |           volume |   members |
|-----------:|-----------:|----------:|-----------------:|----------:|
|      32275 |     17.198 |         1 | 236132           |        75 |
|      30375 |     13.665 |         9 | 291891           |        40 |
|      17391 |     13.015 |         5 | 421635           |        31 |
|      27833 |     11.515 |         7 | 145356           |        27 |
|      17506 |     10.58  |         9 | 379374           |        24 |
|     903498 |      9.64  |        85 |      1.18326e+06 |        22 |
|      42303 |      9.08  |        20 |      1.79547e+06 |        30 |
|     903197 |      8.925 |         4 |      1.22171e+06 |        20 |
|      37213 |      7.91  |       494 | 108066           |        18 |
|      30380 |      7.601 |        24 |  92251           |        20 |


## 5. Verdict & caveats

- favorite strategy OOS-validated: **False**
- momentum OOS-validated: **True** (not armed in live bot at 12h fidelity regardless)
- neg-risk arbitrage: structural, always-on in live scanner with FOK baskets

Caveats: mid-price fills modeled with tiered half-spread haircuts (see cost sensitivity); lifetime volume used as liquidity filter (mild survivorship in favor of liquid markets); 12h price grid understates path risk for time-exits; resolution timestamps from price flatline detection; market microstructure (queue, partial fills) not modeled — stakes assumed small vs depth.
