#!/usr/bin/env python3
"""Full validation run: backtest, benchmarks, bootstrap, DSR, placebo,
sensitivity grid, attribution. Writes reports/REPORT.md, reports/results.json
and reports/figures/*.png.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ctabot import report as rpt
from ctabot import stats as st
from ctabot.backtest import run_strategy
from ctabot.config import PATHS, PRESETS, UNIVERSE, StrategyConfig
from ctabot.data import load_universe, pct_returns

FIG = ROOT / PATHS.figures_dir
REP = ROOT / PATHS.reports_dir


def constant_forecast(template: pd.DataFrame, value: float = 10.0,
                      only: list[str] | None = None) -> pd.DataFrame:
    out = template.notna().astype(float) * value
    out = out.where(template.notna())
    if only is not None:
        for col in out.columns:
            if col not in only:
                out[col] = np.nan
    return out


def main() -> None:  # noqa: PLR0915 - orchestration script
    t0 = time.time()
    cfg = StrategyConfig()
    data, meta = load_universe(ROOT / PATHS.raw_dir)
    is_end = pd.Timestamp(cfg.insample_end)

    print("== base strategy ==")
    base = run_strategy(data, meta, cfg)
    net = base.net.loc["1975":]
    results: dict = {"config": dataclasses.asdict(cfg)}

    results["summary_full"] = st.summary(net)
    results["summary_insample"] = st.summary(net.loc[:is_end])
    results["summary_oos"] = st.summary(net.loc[is_end + pd.Timedelta(days=1):])
    results["cost_drag_trade_ann"] = float(base.trade_costs.mean() * 256)
    results["cost_drag_roll_ann"] = float(base.roll_costs.mean() * 256)
    results["gross_sharpe"] = st.sharpe(base.gross.loc["1975":])
    results["avg_gross_exposure"] = float(base.held.abs().sum(axis=1).loc["1990":].mean())

    print("== benchmarks (same engine, same costs) ==")
    template = base.forecast
    benchmarks: dict[str, pd.Series] = {}
    long_only = run_strategy(data, meta, cfg, forecast_override=constant_forecast(template))
    benchmarks["Long-only risk parity (same engine)"] = long_only.net
    spx = run_strategy(data, meta, cfg, forecast_override=constant_forecast(template, only=["SP500"]))
    benchmarks["S&P 500 long, vol-targeted"] = spx.net
    results["benchmarks"] = {}
    for name, bnet in benchmarks.items():
        results["benchmarks"][name] = st.summary(bnet.loc["1975":])
        results["benchmarks"][name]["corr_to_strategy"] = float(net.corr(bnet))

    print("== presets vs S&P 500 ==")
    spx_1x = pct_returns(data["SP500"])
    preset_nets: dict[str, pd.Series] = {"S&P 500 futures 1x": spx_1x}
    for pname, pcfg in PRESETS.items():
        preset_nets[pname] = run_strategy(data, meta, pcfg).net
    results["presets"] = {}
    for pname, pnet in preset_nets.items():
        w = pnet.loc["1982":]  # common window: SP500 data starts 1982
        results["presets"][pname] = st.summary(w)
        results["presets"][pname]["oos_ann_return"] = float(w.loc[is_end:].mean() * 256)
        results["presets"][pname]["oos_sharpe"] = st.sharpe(w.loc[is_end:])
    diff = (preset_nets["stacked"] - spx_1x).dropna().loc["1982":]
    results["stacked_minus_spx"] = {
        "ann_outperformance_full": float(diff.mean() * 256),
        "ann_outperformance_oos": float(diff.loc[is_end:].mean() * 256),
        "bootstrap": st.stationary_bootstrap_sharpe(diff),
    }

    print("== sleeves ==")
    trend_cfg = dataclasses.replace(cfg, trend_weight=1.0, carry_weight=0.0)
    carry_cfg = dataclasses.replace(cfg, trend_weight=0.0, carry_weight=1.0)
    trend_res = run_strategy(data, meta, trend_cfg)
    carry_res = run_strategy(data, meta, carry_cfg)
    results["sleeves"] = {
        "trend_only": st.summary(trend_res.net.loc["1975":]),
        "carry_only": st.summary(carry_res.net.loc["1975":]),
        "trend_carry_corr": float(trend_res.net.corr(carry_res.net)),
    }
    results["sleeves"]["trend_only"]["oos_sharpe"] = st.sharpe(trend_res.net.loc[is_end:])
    results["sleeves"]["carry_only"]["oos_sharpe"] = st.sharpe(carry_res.net.loc[is_end:])

    print("== block bootstrap ==")
    results["bootstrap_full"] = st.stationary_bootstrap_sharpe(net)
    results["bootstrap_oos"] = st.stationary_bootstrap_sharpe(net.loc[is_end:])
    results["psr_full"] = st.probabilistic_sharpe(net)
    results["psr_oos"] = st.probabilistic_sharpe(net.loc[is_end:])

    print("== sensitivity grid ==")
    variants: list[tuple[str, StrategyConfig]] = []

    def add(label: str, **kw) -> None:
        variants.append((label, dataclasses.replace(cfg, **kw)))

    add("ewmac(16,64) only", ewmac_spans=((16, 64),), breakout_windows=(), carry_weight=0.0, trend_weight=1.0)
    add("ewmac(32,128) only", ewmac_spans=((32, 128),), breakout_windows=(), carry_weight=0.0, trend_weight=1.0)
    add("ewmac(64,256) only", ewmac_spans=((64, 256),), breakout_windows=(), carry_weight=0.0, trend_weight=1.0)
    add("breakout(80) only", ewmac_spans=(), breakout_windows=(80,), carry_weight=0.0, trend_weight=1.0)
    add("breakout(160) only", ewmac_spans=(), breakout_windows=(160,), carry_weight=0.0, trend_weight=1.0)
    add("trend 50 / carry 50", trend_weight=0.5, carry_weight=0.5)
    add("trend 70 / carry 30", trend_weight=0.7, carry_weight=0.3)
    add("trend 100 / carry 0", trend_weight=1.0, carry_weight=0.0)
    add("trend 0 / carry 100", trend_weight=0.0, carry_weight=1.0)
    add("vol span 22", vol_span=22)
    add("vol span 60", vol_span=60)
    add("vol pure EWMA (no blend)", vol_blend_short=1.0)
    add("buffer 0.05", position_buffer=0.05)
    add("buffer 0.20", position_buffer=0.20)
    add("no buffer", position_buffer=0.0)
    add("carry smooth 20d", carry_smooth_span=20)
    add("carry smooth 180d", carry_smooth_span=180)
    add("fdm 1.0", fdm=1.0)
    add("forecast cap 15", forecast_cap=15.0)
    add("forecast cap 30", forecast_cap=30.0)
    add("exec lag 0 (trade on signal close)", execution_lag_days=0)
    add("exec lag 2", execution_lag_days=2)
    add("costs x0.5", cost_multiplier=0.5)
    add("costs x2", cost_multiplier=2.0)
    add("costs x5", cost_multiplier=5.0)
    add("vol target 10%", vol_target_annual=0.10)
    add("idm fixed 1 (no idm)", idm_cap=1.0)

    sens_rows = []
    for label, vcfg in variants:
        vres = run_strategy(data, meta, vcfg)
        vnet = vres.net.loc["1975":]
        sens_rows.append({
            "label": label,
            "sharpe": st.sharpe(vnet),
            "sharpe_oos": st.sharpe(vnet.loc[is_end:]),
            "ann_ret": float(vnet.mean() * 256),
            "ann_vol": float(vnet.std() * np.sqrt(256)),
        })
        print(f"   {label:38s} SR {sens_rows[-1]['sharpe']:.2f}  (oos {sens_rows[-1]['sharpe_oos']:.2f})")
    sens = pd.DataFrame(sens_rows)
    results["sensitivity"] = sens_rows

    print("== deflated Sharpe ==")
    # Trials: every configuration evaluated in this project = base + sleeves
    # + benchmarks-as-strategies + the grid. Round up for safety.
    n_trials = len(variants) + 6
    trial_srs_daily = sens["sharpe"].to_numpy() / np.sqrt(256)
    results["dsr"] = st.deflated_sharpe(net, n_trials=n_trials,
                                        var_trial_sr_daily=float(np.var(trial_srs_daily)))
    results["dsr_oos"] = st.deflated_sharpe(net.loc[is_end:], n_trials=n_trials,
                                            var_trial_sr_daily=float(np.var(trial_srs_daily)))

    print("== placebo (circularly shifted forecasts) ==")
    def run_fn(forecast: pd.DataFrame) -> pd.Series:
        return run_strategy(data, meta, cfg, forecast_override=forecast).net.loc["1975":]
    results["placebo"] = st.placebo_test(run_fn, base.forecast, n_reps=200)

    print("== attribution ==")
    class_of = {i: c for c, members in UNIVERSE.items() for i in members}
    per_class = base.per_instrument_net.T.groupby(class_of).sum().T
    results["attribution_class_sharpe"] = {c: st.sharpe(per_class[c]) for c in per_class}
    results["attribution_class_ann_ret"] = {c: float(per_class[c].mean() * 256) for c in per_class}

    decades = [("1975", "1989"), ("1990", "1999"), ("2000", "2009"),
               ("2010", "2019"), ("2020", "2024")]
    results["subperiods"] = {f"{a}-{b}": st.summary(net.loc[a:b]) for a, b in decades}

    print("== figures ==")
    FIG.mkdir(parents=True, exist_ok=True)
    rpt.fig_equity({"Trend+Carry strategy": net, **{k: v.loc["1975":] for k, v in benchmarks.items()}},
                   FIG / "equity.png")
    rpt.fig_equity({"stacked (S&P + overlay)": preset_nets["stacked"].loc["1982":],
                    "aggressive (30% vol)": preset_nets["aggressive"].loc["1982":],
                    "base (20% vol)": preset_nets["base"].loc["1982":],
                    "S&P 500 futures 1x": spx_1x.loc["1982":]},
                   FIG / "presets.png")
    rpt.fig_rolling_sharpe(net, FIG / "rolling_sharpe.png")
    rpt.fig_yearly_returns(net, FIG / "yearly_returns.png")
    rpt.fig_placebo(results["placebo"], FIG / "placebo.png")
    rpt.fig_sensitivity(sens, results["summary_full"]["sharpe"], FIG / "sensitivity.png")
    rpt.fig_attribution(per_class.loc["1975":], FIG / "attribution.png")
    rpt.fig_bootstrap(results["bootstrap_full"], results["bootstrap_oos"], FIG / "bootstrap.png")

    results["placebo"].pop("null_sharpes")
    (REP / "results.json").write_text(json.dumps(results, indent=2, default=str))
    write_report(results)
    print(f"done in {time.time() - t0:.0f}s -> reports/REPORT.md")


def write_report(res: dict) -> None:
    f = res["summary_full"]; i = res["summary_insample"]; o = res["summary_oos"]

    def srow(name: str, s: dict) -> dict:
        return {"period": name, **s}

    cols = ["period", "start", "end", "ann_return", "ann_vol", "sharpe", "sortino",
            "max_drawdown", "skew_monthly", "pct_positive_months"]
    fmt = {"ann_return": "{:.1%}", "ann_vol": "{:.1%}", "sharpe": "{:.2f}",
           "sortino": "{:.2f}", "max_drawdown": "{:.1%}", "skew_monthly": "{:.2f}",
           "pct_positive_months": "{:.0%}"}

    lines = ["# Validation report", "",
             "Generated by `scripts/run_validation.py` from the pinned data snapshot.",
             "All returns are net of spread, commission and roll costs, with a one-day",
             "execution lag. See README for methodology and caveats.", "",
             "## Headline performance", "",
             rpt.md_table([srow("full sample", f),
                           srow(f"in-sample (≤ {res['config']['insample_end']})", i),
                           srow("out-of-sample (after)", o)], cols, fmt), "",
             f"- Gross (pre-cost) full-sample Sharpe: **{res['gross_sharpe']:.2f}**;"
             f" cost drag {res['cost_drag_trade_ann']:.2%}/yr trading + {res['cost_drag_roll_ann']:.2%}/yr rolling.",
             f"- Average gross notional exposure since 1990: **{res['avg_gross_exposure']:.1f}x** capital.", "",
             "![equity](figures/equity.png)", "",
             "## Statistical significance", "",
             "| test | full sample | out-of-sample |",
             "|---|---|---|"]

    bf, bo = res["bootstrap_full"], res["bootstrap_oos"]
    lines += [
        f"| Sharpe (point) | {bf['sharpe']:.2f} | {bo['sharpe']:.2f} |",
        f"| 95% CI (block bootstrap, {bf['n_boot']} reps) | [{bf['ci_2.5']:.2f}, {bf['ci_97.5']:.2f}] | [{bo['ci_2.5']:.2f}, {bo['ci_97.5']:.2f}] |",
        f"| p(SR ≤ 0), bootstrap | {bf['p_value_sr_le_0']:.4f} | {bo['p_value_sr_le_0']:.4f} |",
        f"| Probabilistic SR (non-normality adj.) | {res['psr_full']:.4f} | {res['psr_oos']:.4f} |",
        f"| Deflated SR ({res['dsr']['n_trials']} trials, hurdle SR* = {res['dsr']['sr_star_annual']:.2f} ann.) | {res['dsr']['dsr']:.4f} | {res['dsr_oos']['dsr']:.4f} |",
        "",
        f"Placebo test: {res['placebo']['n_reps']} runs with each instrument's forecast circularly",
        f"time-shifted by a random ≥1y offset, through the identical sizing and cost engine.",
        f"Null Sharpe: mean {res['placebo']['null_mean']:.2f} ± {res['placebo']['null_std']:.2f},",
        f"95th pct {res['placebo']['null_p95']:.2f}, max {res['placebo']['null_max']:.2f}.",
        f"Real Sharpe {res['placebo']['real_sharpe']:.2f} → **p = {res['placebo']['p_value']:.3f}**.",
        "",
        "![placebo](figures/placebo.png)", "",
        "![bootstrap](figures/bootstrap.png)", "",
        "## Benchmarks (identical engine, costs, vol target)", "",
    ]
    bcols = ["benchmark", "ann_return", "ann_vol", "sharpe", "max_drawdown", "corr_to_strategy"]
    bfmt = {**fmt, "corr_to_strategy": "{:.2f}"}
    brows = [{"benchmark": k, **v} for k, v in res["benchmarks"].items()]
    prows = [{"preset": k, **v} for k, v in res["presets"].items()]
    pcols = ["preset", "ann_return", "ann_vol", "sharpe", "max_drawdown",
             "oos_ann_return", "oos_sharpe"]
    pfmt = {**fmt, "oos_ann_return": "{:.1%}", "oos_sharpe": "{:.2f}"}
    sm = res["stacked_minus_spx"]
    lines += [rpt.md_table(brows, bcols, bfmt), "",
              "## Presets vs the S&P 500 (common window 1982–2024)", "",
              rpt.md_table(prows, pcols, pfmt), "",
              f"Stacked-minus-S&P daily difference: **{sm['ann_outperformance_full']:+.1%}/yr** full sample,",
              f"**{sm['ann_outperformance_oos']:+.1%}/yr** out-of-sample (2015–2024);",
              f"outperformance Sharpe {sm['bootstrap']['sharpe']:.2f},",
              f"95% CI [{sm['bootstrap']['ci_2.5']:.2f}, {sm['bootstrap']['ci_97.5']:.2f}],",
              f"p(≤0) = {sm['bootstrap']['p_value_sr_le_0']:.4f}.", "",
              "![presets](figures/presets.png)", "",
              "## Sleeves", "",
              rpt.md_table([
                  {"sleeve": "trend only", **res["sleeves"]["trend_only"]},
                  {"sleeve": "carry only", **res["sleeves"]["carry_only"]}],
                  ["sleeve", "ann_return", "ann_vol", "sharpe", "max_drawdown"], fmt), "",
              f"Trend/carry daily return correlation: {res['sleeves']['trend_carry_corr']:.2f};"
              f" out-of-sample Sharpe — trend {res['sleeves']['trend_only']['oos_sharpe']:.2f},"
              f" carry {res['sleeves']['carry_only']['oos_sharpe']:.2f}.", "",
              "## Parameter sensitivity", "",
              "Every parameter variation evaluated (each one full backtest):", "",
              rpt.md_table(res["sensitivity"], ["label", "sharpe", "sharpe_oos", "ann_ret", "ann_vol"],
                           {"sharpe": "{:.2f}", "sharpe_oos": "{:.2f}", "ann_ret": "{:.1%}", "ann_vol": "{:.1%}"}), "",
              "![sensitivity](figures/sensitivity.png)", "",
              "## Attribution", "",
              "Annualised net return contribution and Sharpe by asset class:", "",
              rpt.md_table([{"class": c,
                             "ann_return": res["attribution_class_ann_ret"][c],
                             "sharpe": res["attribution_class_sharpe"][c]}
                            for c in res["attribution_class_sharpe"]],
                           ["class", "ann_return", "sharpe"],
                           {"ann_return": "{:.2%}", "sharpe": "{:.2f}"}), "",
              "![attribution](figures/attribution.png)", "",
              "## Subperiods", "",
              rpt.md_table([{"period": k, **v} for k, v in res["subperiods"].items()],
                           cols, fmt), "",
              "![rolling](figures/rolling_sharpe.png)", "",
              "![yearly](figures/yearly_returns.png)", ""]

    (REP / "REPORT.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
