# Polymarket edge research report

- markets in dataset: **89,751** (clean binary resolutions: **89,590**, ties/invalid: 160, unparseable: 1)
- price rows (12h fidelity): **3,138,587** across 66,905 markets
- total lifetime volume covered: **$64.00B**
- price data through: **2026-06-10**
- walk-forward cutoff (signals before=train, after=test): **2025-12-01**
- execution haircut model: `{'tiers': [0.0, 10000.0, 100000.0], 'half_spread': [0.005, 0.005, 0.005], 'source': 'active_book_snapshot', 'n_books': 425}`


## 1. Calibration / favorite-longshot bias

Snapshot = last mid at horizon h before the settle flatline (see dataio.settle_time). Wilson 95% intervals; FLB regression `outcome - p ~ a + b(p - 0.5)` with event-cluster-robust errors.

**24h before resolution** (n=40,119): FLB slope b=-0.0065 (t=-1.2, p=0.23) — no significant favorite-longshot bias. 

  - vol>=10k: b=-0.0082 (p=0.13, n=39,149)
  - vol>=100k: b=-0.0159 (p=0.0045, n=35,212)
  - cat:crypto: b=-0.0313 (p=0.0027, n=7,239)
  - cat:entertainment: b=0.0101 (p=0.68, n=763)
  - cat:geopolitics: b=0.1180 (p=2.1e-06, n=1,549)
  - cat:other: b=0.0070 (p=0.52, n=11,805)
  - cat:politics: b=0.0251 (p=0.0075, n=3,728)
  - cat:sports: b=-0.0254 (p=0.047, n=14,062)
  - cat:tech_ai: b=0.0063 (p=0.79, n=740)


Gross (cost-free) expected returns by zone at 24h:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 5883 |    0.0221422 |  0.0175081 |     -0.297694   |     0.00471759 |
| [0.05,0.10) | 1851 |    0.0708509 |  0.0880605 |      0.198733   |    -0.0187963  |
| [0.90,0.95) |  565 |    0.925779  |  0.904425  |     -0.0231068  |     0.285766   |
| [0.95,0.99) | 1276 |    0.975364  |  0.973354  |     -0.00212849 |     0.0156655  |
| [0.97,0.99) |  892 |    0.981751  |  0.985426  |      0.00378173 |    -0.139508   |

**72h before resolution** (n=35,131): FLB slope b=-0.0276 (t=-3.9, p=9.5e-05) — favorites OVERPRICED at this horizon (reverse FLB). 

  - vol>=10k: b=-0.0297 (p=3.3e-05, n=34,307)
  - vol>=100k: b=-0.0403 (p=5.3e-08, n=30,736)
  - cat:crypto: b=-0.1127 (p=3.9e-10, n=6,387)
  - cat:entertainment: b=-0.0246 (p=0.54, n=680)
  - cat:geopolitics: b=0.0866 (p=0.004, n=1,408)
  - cat:other: b=0.0073 (p=0.56, n=9,957)
  - cat:politics: b=0.0255 (p=0.02, n=3,541)
  - cat:sports: b=-0.0196 (p=0.15, n=12,233)
  - cat:tech_ai: b=0.0269 (p=0.25, n=693)


Gross (cost-free) expected returns by zone at 72h:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 4963 |    0.0235085 |  0.0257909 |       0.118927  |    -0.0023314  |
| [0.05,0.10) | 2130 |    0.0718216 |  0.0769953 |       0.0585165 |    -0.00566283 |
| [0.90,0.95) |  548 |    0.925628  |  0.879562  |      -0.049885  |     0.624727   |
| [0.95,0.99) | 1009 |    0.974265  |  0.9445    |      -0.0305527 |     1.52949    |
| [0.97,0.99) |  670 |    0.981498  |  0.952239  |      -0.0297487 |     1.93394    |

**7d before resolution** (n=21,746): FLB slope b=0.0142 (t=1.7, p=0.083) — no significant favorite-longshot bias. 

  - vol>=10k: b=0.0138 (p=0.094, n=21,163)
  - vol>=100k: b=0.0082 (p=0.34, n=18,503)
  - cat:crypto: b=0.2580 (p=3.4e-10, n=1,142)
  - cat:entertainment: b=-0.0809 (p=0.12, n=540)
  - cat:geopolitics: b=0.0820 (p=0.052, n=1,184)
  - cat:other: b=0.0122 (p=0.41, n=7,334)
  - cat:politics: b=0.0185 (p=0.17, n=3,157)
  - cat:sports: b=-0.0046 (p=0.79, n=7,534)
  - cat:tech_ai: b=0.0405 (p=0.18, n=631)


Gross (cost-free) expected returns by zone at 7d:

| zone        |    n |   mean_price |   emp_rate |   gross_ret_yes |   gross_ret_no |
|:------------|-----:|-------------:|-----------:|----------------:|---------------:|
| [0.01,0.05) | 3735 |    0.0228724 |   0.021419 |      -0.238204  |     0.00140093 |
| [0.05,0.10) | 1265 |    0.0714427 |   0.086166 |       0.214455  |    -0.0158208  |
| [0.90,0.95) |  239 |    0.926098  |   0.92887  |       0.003011  |    -0.0463464  |
| [0.95,0.99) |  449 |    0.97489   |   0.993318 |       0.0189275 |    -0.826345   |
| [0.97,0.99) |  316 |    0.980889  |   1        |       0.0195164 |    -1          |


## 2. Favorite strategy — walk-forward

Rule: in the final W days before end_date, first bar with p >= θ buys YES (p <= 1-θ buys NO); hold to resolution. Fills use the worse of the signal and next bar plus the tiered half-spread. Max 2 trades/event; min lifetime volume $10k. Grid below is fully disclosed; the chosen cell maximizes the train CI lower bound and is then frozen for OOS.


Train grid (top 10 by CI lower bound):

| cell                 |   n_trades |     mean_ret |      ci_lo |       ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:---------------------|-----------:|-------------:|-----------:|------------:|--------:|-----------:|--------------------:|
| fav θ=0.97 W=1d yes  |        212 | -0.000700534 | -0.0155477 |  0.00919332 | 0.576   |   0.990566 |          -0.0934154 |
| fav θ=0.97 W=1d both |       1063 | -0.00946065  | -0.0174347 | -0.00207925 | 0.9945  |   0.983067 |          -1.70286   |
| fav θ=0.97 W=3d both |       2279 | -0.013961    | -0.0206734 | -0.00768177 | 1       |   0.977183 |          -2.32103   |
| fav θ=0.97 W=1d no   |        864 | -0.0113431   | -0.0207153 | -0.00297111 | 0.99525 |   0.981481 |          -1.85298   |
| fav θ=0.97 W=3d no   |       1950 | -0.0149186   | -0.0224585 | -0.00833395 | 1       |   0.97641  |          -2.36118   |
| fav θ=0.97 W=7d both |       2835 | -0.0180068   | -0.0247143 | -0.0118079  | 1       |   0.971781 |          -2.40988   |
| fav θ=0.97 W=7d no   |       2484 | -0.0189894   | -0.0258793 | -0.0122482  | 1       |   0.971014 |          -2.60195   |
| fav θ=0.95 W=1d both |       1451 | -0.0164871   | -0.0259261 | -0.00812414 | 1       |   0.971744 |          -2.11299   |
| fav θ=0.95 W=1d no   |       1167 | -0.0168816   | -0.0264815 | -0.00776201 | 0.99975 |   0.971722 |          -2.23422   |
| fav θ=0.95 W=3d no   |       2270 | -0.0193798   | -0.0270541 | -0.0119585  | 1       |   0.96652  |          -2.72323   |


**Chosen cell:** `fav θ=0.97 W=1d yes` → **out-of-sample**: n=172 trades, mean ret/stake **-3.97%** (95% CI [-7.43%, -1.03%], cluster-bootstrap by event), hit rate 95.3%, weekly Sharpe -2.42 (26 wks), max drawdown $-5.8 per $1 stakes, annualized return on peak capital -119.0%.

Multiple-testing note: {'n_cells': 36, 'raw_p': 0.996, 'family_wise_p_bonferroni': 1.0, 'family_wise_p_independent_approx': 1.0}


Cost sensitivity (OOS, chosen cell):

| costs          |   mean_ret |      ci_lo |      ci_hi |   n |
|:---------------|-----------:|-----------:|-----------:|----:|
| no costs       | -0.0349064 | -0.0699304 | -0.005308  | 172 |
| 1x half-spread | -0.0397226 | -0.0745661 | -0.010265  | 172 |
| 2x half-spread | -0.0427848 | -0.0775493 | -0.0134803 | 172 |


Per-quarter stability of the chosen cell (quarters after the cutoff are out-of-sample):

| quarter   |   n |   mean_ret |   ci_lo |   ci_hi | oos   |
|:----------|----:|-----------:|--------:|--------:|:------|
| 2024Q1    |   4 |     0.0026 |  0.0013 |  0.004  | False |
| 2024Q2    |   4 |     0.0057 |  0.0033 |  0.0087 | False |
| 2024Q3    |  11 |     0.0074 |  0.0036 |  0.0117 | False |
| 2024Q4    |  49 |     0.0096 |  0.0081 |  0.0113 | False |
| 2025Q1    |  27 |     0.0074 |  0.0054 |  0.0094 | False |
| 2025Q2    |  33 |     0.0099 |  0.008  |  0.012  | False |
| 2025Q3    |  35 |     0.0079 |  0.006  |  0.01   | False |
| 2025Q4    |  85 |    -0.0384 | -0.0864 | -0.0024 | False |
| 2026Q1    |  90 |    -0.0271 | -0.0687 |  0.0061 | True  |
| 2026Q2    |  46 |    -0.0578 | -0.1441 |  0.0078 | True  |


OOS by category (chosen cell, n>=30):

| category   |   n |   mean_ret |   ci_lo |   ci_hi |
|:-----------|----:|-----------:|--------:|--------:|
| crypto     | 102 |    -0.0626 | -0.1098 | -0.0136 |


## 3. Momentum / mean reversion — walk-forward

Rule: |Δp| >= δ over 24h, price in [0.10, 0.90], market at least 48h old with 4 prior bars, enter with the move ('with') or against it ('against'); hold to resolution or time-exit. One trade per market. Fills use the worse of the signal and next bar plus the haircut (`entry_bar='next_worse'`).


**Execution-artifact check** (δ=0.15 against, hold to resolution, full sample): same-bar entry shows 15.3%/trade (n=8,991) but worse-of-next-bar entry — the executable version — shows 0.9%/trade (n=8,629). The gap is unfillable stale-print 'profit'; every number below uses the executable model.


Train grid (top 10 by CI lower bound):

| cell                        |   n_trades |    mean_ret |      ci_lo |       ci_hi |   p_le0 |   hit_rate |   sharpe_ann_weekly |
|:----------------------------|-----------:|------------:|-----------:|------------:|--------:|-----------:|--------------------:|
| mom δ=0.15 against hold=7d  |       4484 | -0.00898347 | -0.0383487 |  0.0228149  | 0.71925 |   0.458742 |           -0.231734 |
| mom δ=0.05 against hold=7d  |       7355 | -0.0184344  | -0.040916  |  0.00511627 | 0.93975 |   0.458464 |           -0.846144 |
| mom δ=0.1 against hold=7d   |       5878 | -0.0170913  | -0.0438665 |  0.0105658  | 0.8955  |   0.453386 |           -0.68398  |
| mom δ=0.1 against hold=res  |       5878 | -0.0120365  | -0.0460853 |  0.022671   | 0.7665  |   0.476012 |           -0.37014  |
| mom δ=0.05 with hold=res    |       7355 | -0.0235923  | -0.0516252 |  0.00486147 | 0.945   |   0.511489 |           -0.749602 |
| mom δ=0.15 against hold=res |       4484 | -0.0143409  | -0.0533989 |  0.0252924  | 0.766   |   0.462979 |           -0.376521 |
| mom δ=0.05 against hold=res |       7355 | -0.0267149  | -0.0564749 |  0.00340459 | 0.95825 |   0.488511 |           -0.974281 |
| mom δ=0.05 against hold=3d  |       7355 | -0.0419431  | -0.059522  | -0.0241961  | 1       |   0.425425 |           -2.29212  |
| mom δ=0.1 against hold=3d   |       5878 | -0.0428862  | -0.0648159 | -0.0212378  | 0.99975 |   0.436203 |           -2.32981  |
| mom δ=0.15 against hold=3d  |       4484 | -0.0440796  | -0.0682058 | -0.0190056  | 0.99875 |   0.437779 |           -1.45424  |


**Chosen cell:** `mom δ=0.15 against hold=7d` → **out-of-sample**: n=4,208, mean ret/stake **0.39%** (95% CI [-3.22%, 3.99%]), hit rate 42.4%, weekly Sharpe 0.23.

Multiple-testing note: {'n_cells': 18, 'raw_p': 0.4155, 'family_wise_p_bonferroni': 1.0, 'family_wise_p_independent_approx': 0.9999365953252657}


## 4. Neg-risk structural arbitrage (indicative)

Events analyzed: 2,585; grid snapshots: 316,563. Snapshots with sum-of-YES mispricing beyond per-leg half-spreads (> $0.01/set): **97,103** (30.67%) across **2,184 events**.

These are *mid-based and staleness-filtered but execution-unverified* — treat as an upper bound on frequency and use the live scanner (FOK basket orders) to harvest. Top events:

|   event_id |   max_edge |   n_snaps |           volume |   members |
|-----------:|-----------:|----------:|-----------------:|----------:|
|      64414 |    18.907  |      1539 |      5.52031e+06 |        51 |
|      63616 |    14.815  |      3442 |      1.25037e+06 |        32 |
|     139379 |    10.085  |        20 |      1.26183e+06 |        31 |
|     903197 |     8.925  |         4 |      1.22171e+06 |        20 |
|     258891 |     8.28   |        22 |      3.04211e+06 |        22 |
|     404235 |     7.16   |         7 |      1.99399e+06 |        20 |
|      50525 |     7.12   |        91 |      3.09162e+06 |        17 |
|      53882 |     7.0605 |        61 |      4.55784e+06 |        26 |
|      45227 |     6.934  |        91 |      3.49856e+06 |        30 |
|      19827 |     5.7685 |         1 | 978670           |        18 |


## 5. Verdict & caveats

- favorite strategy OOS-validated: **False**
- momentum OOS-validated: **False** (not armed in live bot at 12h fidelity regardless)
- neg-risk arbitrage: structural, always-on in live scanner with FOK baskets

Caveats: mid-price fills modeled with tiered half-spread haircuts (see cost sensitivity); lifetime volume used as liquidity filter (mild survivorship in favor of liquid markets); 12h price grid understates path risk for time-exits; resolution timestamps from price flatline detection; market microstructure (queue, partial fills) not modeled — stakes assumed small vs depth.
