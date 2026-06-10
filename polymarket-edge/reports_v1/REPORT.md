# Polymarket edge research report

- markets in dataset: **7,070** (clean binary resolutions: **7,070**, ties/invalid: 0, unparseable: 0)
- price rows (12h fidelity): **876,298** across 5,689 markets
- total lifetime volume covered: **$28.78B**
- price data through: **2026-06-08**
- walk-forward cutoff (signals before=train, after=test): **2025-12-01**
- execution haircut model: `{'tiers': [0.0, 10000.0, 100000.0], 'half_spread': [0.005, 0.005, 0.005], 'source': 'active_book_snapshot', 'n_books': 70}`


## 1. Calibration / favorite-longshot bias

Snapshot = last mid at horizon h before the settle flatline (see dataio.settle_time). Wilson 95% intervals; FLB regression `outcome - p ~ a + b(p - 0.5)` with HC1 errors.

**24h before resolution** (n=4,558): FLB slope b=0.0134 (t=0.8, p=0.41) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0127 (p=0.43, n=4,402)
  - vol>=100k: b=0.0154 (p=0.35, n=4,131)
  - cat:uncat: b=0.0134 (p=0.41, n=4,558)


Gross (cost-free) expected returns by zone at 24h:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 1041 |    0.0215793 |  0.0144092 |      -0.305594  |     0.00738898 |
| [0.05,0.10) |  270 |    0.0689759 |  0.0444444 |      -0.389873  |     0.0262284  |
| [0.90,0.95) |   40 |    0.925875  |  0.95      |       0.0258603 |    -0.379699   |
| [0.95,0.99) |   73 |    0.976253  |  1         |       0.0244666 |    -1          |
| [0.97,0.99) |   52 |    0.982596  |  1         |       0.0177414 |    -1          |

**72h before resolution** (n=4,241): FLB slope b=-0.0004 (t=-0.0, p=0.98) — no significant favorite-longshot bias. 

  - vol>=10k: b=-0.0014 (p=0.94, n=4,108)
  - vol>=100k: b=-0.0012 (p=0.95, n=3,861)
  - cat:uncat: b=-0.0004 (p=0.98, n=4,241)


Gross (cost-free) expected returns by zone at 72h:

| zone        |   n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 916 |    0.0228745 |  0.0163755 |    -0.122056    |     0.00677859 |
| [0.05,0.10) | 384 |    0.0723073 |  0.0598958 |    -0.164019    |     0.0134794  |
| [0.90,0.95) |  52 |    0.924942  |  0.961538  |     0.0400924   |    -0.43889    |
| [0.95,0.99) |  71 |    0.978247  |  0.985915  |     0.0080706   |     0.00603632 |
| [0.97,0.99) |  58 |    0.982491  |  0.982759  |     0.000366144 |     0.231527   |

**7d before resolution** (n=3,422): FLB slope b=0.0067 (t=0.3, p=0.74) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0066 (p=0.74, n=3,322)
  - vol>=100k: b=0.0086 (p=0.67, n=3,113)
  - cat:uncat: b=0.0067 (p=0.74, n=3,422)


Gross (cost-free) expected returns by zone at 7d:

| zone        |   n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 780 |    0.0226571 |  0.0166667 |      -0.347155  |     0.00612991 |
| [0.05,0.10) | 281 |    0.0721512 |  0.0996441 |       0.437465  |    -0.0293856  |
| [0.95,0.99) |  62 |    0.974653  |  1         |       0.0261389 |    -1          |
| [0.97,0.99) |  43 |    0.980698  |  1         |       0.0197263 |    -1          |


## 2. Favorite strategy — walk-forward

Rule: in the final W days before end_date, first bar with p >= θ buys YES (p <= 1-θ buys NO) at mid + tiered half-spread; hold to resolution. Max 2 trades/event; min lifetime volume $10k. Grid below is fully disclosed; the chosen cell maximizes the train CI lower bound and is then frozen for OOS.


Train grid (top 10 by CI lower bound):

| cell                 |   n_trades |    mean_ret |       ci_lo |      ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:---------------------|-----------:|------------:|------------:|-----------:|--------:|-----------:|--------------------:|
| fav θ=0.97 W=7d yes  |         51 |  0.0110437  |  0.00902216 | 0.0132559  | 0       |   1        |           11.3923   |
| fav θ=0.97 W=3d yes  |         43 |  0.0101526  |  0.00785608 | 0.012613   | 0       |   1        |            9.65064  |
| fav θ=0.97 W=1d yes  |         30 |  0.00960789 |  0.00719554 | 0.0122448  | 0       |   1        |            9.63339  |
| fav θ=0.97 W=3d both |        240 | -0.00178059 | -0.0181618  | 0.0107905  | 0.57825 |   0.9875   |           -0.227105 |
| fav θ=0.97 W=1d both |        172 | -0.00225312 | -0.020721   | 0.00992129 | 0.60425 |   0.988372 |           -0.261394 |
| fav θ=0.97 W=7d both |        282 | -0.00564153 | -0.0228569  | 0.00857612 | 0.7355  |   0.98227  |           -0.651508 |
| fav θ=0.97 W=3d no   |        203 | -0.00389615 | -0.0231555  | 0.0110119  | 0.58175 |   0.985222 |           -0.435779 |
| fav θ=0.95 W=7d yes  |         69 |  0.0084572  | -0.0236923  | 0.0261862  | 0.25875 |   0.985507 |            0.606101 |
| fav θ=0.97 W=1d no   |        146 | -0.00455643 | -0.0267875  | 0.00973119 | 0.61025 |   0.986301 |           -0.46292  |
| fav θ=0.97 W=7d no   |        244 | -0.00806525 | -0.0273126  | 0.00848538 | 0.786   |   0.979508 |           -0.825244 |


**Chosen cell:** `fav θ=0.97 W=3d both` → **out-of-sample**: n=203 trades, mean ret/stake **-4.47%** (95% CI [-7.77%, -1.56%], cluster-bootstrap by event), hit rate 94.6%, weekly Sharpe -3.40 (27 wks), max drawdown $-9.4 per $1 stakes, annualized return on peak capital -80.0%.

Multiple-testing note: {'n_cells': 36, 'raw_p': 0.9995, 'family_wise_p_bonferroni': 1.0, 'family_wise_p_independent_approx': 1.0}


Cost sensitivity (OOS, chosen cell):

| costs          |   mean_ret |      ci_lo |      ci_hi |   n |
|:---------------|-----------:|-----------:|-----------:|----:|
| no costs       | -0.0398466 | -0.0719773 | -0.0101182 | 203 |
| 1x half-spread | -0.0446736 | -0.0766259 | -0.0151001 | 203 |
| 2x half-spread | -0.0482674 | -0.0799847 | -0.0188216 | 203 |


Per-quarter stability of the chosen cell (quarters after the cutoff are out-of-sample):

| quarter   |   n |   mean_ret |   ci_lo |   ci_hi | oos   |
|:----------|----:|-----------:|--------:|--------:|:------|
| 2024Q1    |   4 |     0.0168 |  0.0045 |  0.0209 | False |
| 2024Q2    |   1 |     0.0076 |  0.0076 |  0.0076 | False |
| 2024Q3    |  10 |     0.0115 |  0.0058 |  0.017  | False |
| 2024Q4    |  51 |     0.0097 |  0.0075 |  0.0121 | False |
| 2025Q1    |  35 |     0.013  |  0.0103 |  0.0154 | False |
| 2025Q2    |  61 |    -0.0246 | -0.0728 |  0.0094 | False |
| 2025Q3    |  29 |    -0.0222 | -0.1007 |  0.0147 | False |
| 2025Q4    |  90 |    -0.0011 | -0.0257 |  0.0112 | False |
| 2026Q1    | 111 |    -0.0625 | -0.1145 | -0.017  | True  |
| 2026Q2    |  49 |    -0.0301 | -0.0945 |  0.0127 | True  |


## 3. Momentum / underreaction — walk-forward

Rule: |Δp| >= δ over 24h, price in [0.10, 0.90], enter at signal bar with the move ('with') or against it ('against'); hold to resolution or time-exit. One trade per market.


Train grid (top 10 by CI lower bound):

| cell                        |   n_trades |   mean_ret |       ci_lo |     ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:----------------------------|-----------:|-----------:|------------:|----------:|--------:|-----------:|--------------------:|
| mom δ=0.15 against hold=3d  |        445 | 0.0593604  | -0.00145998 | 0.119658  | 0.0295  |   0.521348 |           1.51695   |
| mom δ=0.1 against hold=3d   |        543 | 0.0481663  | -0.00243042 | 0.10148   | 0.0325  |   0.548803 |           1.34854   |
| mom δ=0.15 against hold=7d  |        445 | 0.0708079  | -0.00413199 | 0.150108  | 0.032   |   0.534831 |           1.57921   |
| mom δ=0.1 against hold=7d   |        543 | 0.0591795  | -0.00579338 | 0.127337  | 0.04    |   0.504604 |           1.38445   |
| mom δ=0.05 against hold=res |        625 | 0.0821166  | -0.0248496  | 0.189738  | 0.07025 |   0.5536   |           1.10528   |
| mom δ=0.05 against hold=3d  |        625 | 0.0016636  | -0.0354441  | 0.0403841 | 0.48425 |   0.496    |           0.0578624 |
| mom δ=0.05 against hold=7d  |        625 | 0.00786048 | -0.0399693  | 0.0534655 | 0.38525 |   0.5248   |           0.235642  |
| mom δ=0.1 against hold=res  |        543 | 0.0593869  | -0.0533147  | 0.185035  | 0.15425 |   0.502762 |           0.722996  |
| mom δ=0.05 with hold=res    |        625 | 0.0497178  | -0.0712971  | 0.18005   | 0.23075 |   0.4464   |           0.453661  |
| mom δ=0.1 with hold=res     |        543 | 0.0252843  | -0.0767193  | 0.130423  | 0.32675 |   0.497238 |           0.328452  |


**Chosen cell:** `mom δ=0.15 against hold=3d` → **out-of-sample**: n=241, mean ret/stake **8.45%** (95% CI [-2.29%, 19.83%]), hit rate 49.8%, weekly Sharpe 1.66.

Multiple-testing note: {'n_cells': 18, 'raw_p': 0.06425, 'family_wise_p_bonferroni': 1.0, 'family_wise_p_independent_approx': 0.6973943419107863}


## 4. Neg-risk structural arbitrage (indicative)

Events analyzed: 312; grid snapshots: 67,419. Snapshots with sum-of-YES mispricing beyond per-leg half-spreads (> $0.01/set): **7,231** (10.73%) across **246 events**.

These are *mid-based and staleness-filtered but execution-unverified* — treat as an upper bound on frequency and use the live scanner (FOK basket orders) to harvest. Top events:

|   event_id |   max_edge |   n_snaps |      volume |   members |
|-----------:|-----------:|----------:|------------:|----------:|
|      27829 |     5.045  |      1442 | 7.71137e+07 |        30 |
|      27830 |     4.175  |       394 | 3.53597e+08 |        28 |
|      13887 |     4.14   |        23 | 1.20867e+07 |        12 |
|     241861 |     3.78   |       255 | 7.80696e+06 |        25 |
|      20798 |     2.605  |        35 | 6.43686e+07 |        20 |
|      10228 |     2.535  |        96 | 6.59445e+06 |         9 |
|     514882 |     2.015  |         8 | 7.8569e+06  |        26 |
|      43172 |     1.975  |       115 | 6.20942e+06 |         6 |
|      32203 |     1.575  |         1 | 4.49077e+06 |         5 |
|      11910 |     1.5375 |         4 | 1.24039e+08 |        17 |


## 5. Verdict & caveats

- favorite strategy OOS-validated: **False**
- momentum OOS-validated: **False** (not armed in live bot at 12h fidelity regardless)
- neg-risk arbitrage: structural, always-on in live scanner with FOK baskets

Caveats: mid-price fills modeled with tiered half-spread haircuts (see cost sensitivity); lifetime volume used as liquidity filter (mild survivorship in favor of liquid markets); 12h price grid understates path risk for time-exits; resolution timestamps from price flatline detection; market microstructure (queue, partial fills) not modeled — stakes assumed small vs depth.
