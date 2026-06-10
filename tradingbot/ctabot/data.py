"""Data layer.

Source: robcarver17/pysystemtrade futures data (Barchart-sourced, maintained
by Rob Carver), pinned to a single upstream commit so every result in this
repo is reproducible byte-for-byte. Two files per instrument:

- adjusted_prices_csv/<X>.csv : back-adjusted continuous price (points).
  Differences of this series are tradable P&L per contract point.
- multiple_prices_csv/<X>.csv : current-contract price (PRICE), the price of
  the "carry" contract (CARRY) and both contract labels (YYYYMM). Needed to
  convert point P&L into percent returns and to compute the carry signal.

Back-adjusted levels are NOT prices you could have traded at (the adjustment
shifts old levels), so percent returns are computed as

    r_t = (adj_t - adj_{t-1}) / price_{t-1}

i.e. point P&L over the actual contract price — the standard convention for
back-adjusted futures (Carver 2015, ch. 15).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_REPO, DATA_SHA, UNIVERSE, all_instruments

RAW_BASE = "https://raw.githubusercontent.com/{repo}/{sha}/data/futures/{kind}/{name}.csv"
CFG_BASE = "https://raw.githubusercontent.com/{repo}/{sha}/data/futures/csvconfig/{name}.csv"

_UA = {"User-Agent": "ctabot-research/0.1 (+https://github.com)"}


def _http_get(url: str, retries: int = 4, timeout: int = 60) -> bytes:
    delay = 2.0
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as err:  # noqa: BLE001 - retry any transport error
            last_err = err
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _to_daily(raw_csv: bytes, columns: list[str]) -> pd.DataFrame:
    """Parse an upstream CSV and collapse to one row per calendar day (last)."""
    df = pd.read_csv(io.BytesIO(raw_csv), parse_dates=["DATETIME"])
    df["date"] = df["DATETIME"].dt.normalize()
    df = df.groupby("date")[columns].last()
    df.index.name = "date"
    return df


def fetch_universe(raw_dir: str | Path, manifest_path: str | Path,
                   repo: str = DATA_REPO, sha: str = DATA_SHA) -> dict:
    """Download, daily-resample and cache the pinned data snapshot.

    Writes one csv.gz per instrument (merged adjusted+multiple columns) plus
    the upstream config CSVs, and a manifest recording the source URL and
    sha256 of every upstream payload.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "source_repo": repo,
        "source_sha": sha,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "instruments": {},
        "configs": {},
    }

    for cfg in ("instrumentconfig", "spreadcosts", "rollconfig"):
        url = CFG_BASE.format(repo=repo, sha=sha, name=cfg)
        payload = _http_get(url)
        (raw_dir / f"{cfg}.csv").write_bytes(payload)
        manifest["configs"][cfg] = {"url": url, "sha256": _sha256(payload)}

    for name in all_instruments():
        adj_url = RAW_BASE.format(repo=repo, sha=sha, kind="adjusted_prices_csv", name=name)
        mul_url = RAW_BASE.format(repo=repo, sha=sha, kind="multiple_prices_csv", name=name)
        adj_raw = _http_get(adj_url)
        mul_raw = _http_get(mul_url)

        adj = _to_daily(adj_raw, ["price"]).rename(columns={"price": "adj"})
        mul = _to_daily(mul_raw, ["PRICE", "CARRY", "PRICE_CONTRACT", "CARRY_CONTRACT"])
        mul = mul.rename(columns={
            "PRICE": "price", "CARRY": "carry_price",
            "PRICE_CONTRACT": "price_contract", "CARRY_CONTRACT": "carry_contract",
        })
        df = adj.join(mul, how="left")
        # Contract prices/labels can be missing on days the adjusted series
        # has a print but the multiple-prices file does not; forward fill is
        # safe (uses only past values).
        df[["price", "carry_price", "price_contract", "carry_contract"]] = (
            df[["price", "carry_price", "price_contract", "carry_contract"]].ffill()
        )
        df = df.dropna(subset=["adj", "price"])

        out = raw_dir / f"{name}.csv.gz"
        with gzip.open(out, "wt") as fh:
            df.to_csv(fh)
        manifest["instruments"][name] = {
            "adjusted_url": adj_url, "adjusted_sha256": _sha256(adj_raw),
            "multiple_url": mul_url, "multiple_sha256": _sha256(mul_raw),
            "rows": int(len(df)),
            "start": str(df.index.min().date()),
            "end": str(df.index.max().date()),
            "min_contract_price": float(df["price"].min()),
        }
        print(f"fetched {name:9s} {len(df):6d} rows  "
              f"{df.index.min().date()} -> {df.index.max().date()}")

    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2))
    return manifest


# ----------------------------------------------------------------------------
# Loading


def load_instrument(name: str, raw_dir: str | Path) -> pd.DataFrame:
    df = pd.read_csv(Path(raw_dir) / f"{name}.csv.gz", index_col="date", parse_dates=["date"])
    return df


def load_metadata(raw_dir: str | Path) -> pd.DataFrame:
    """Per-instrument static metadata: asset class, point size, costs, rolls."""
    raw_dir = Path(raw_dir)
    icfg = pd.read_csv(raw_dir / "instrumentconfig.csv", index_col="Instrument")
    spread = pd.read_csv(raw_dir / "spreadcosts.csv", index_col="Instrument")
    roll = pd.read_csv(raw_dir / "rollconfig.csv", index_col="Instrument")

    class_of = {i: cls for cls, instruments in UNIVERSE.items() for i in instruments}
    rows = []
    for name in all_instruments():
        rows.append({
            "instrument": name,
            "asset_class": class_of[name],
            "point_size": float(icfg.loc[name, "Pointsize"]),
            "currency": icfg.loc[name, "Currency"],
            "spread_cost_points": float(spread.loc[name, "SpreadCost"]),
            "rolls_per_year": len(str(roll.loc[name, "HoldRollCycle"])),
        })
    return pd.DataFrame(rows).set_index("instrument")


def load_universe(raw_dir: str | Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    data = {name: load_instrument(name, raw_dir) for name in all_instruments()}
    meta = load_metadata(raw_dir)
    return data, meta


# ----------------------------------------------------------------------------
# Derived series


def pct_returns(df: pd.DataFrame) -> pd.Series:
    """Daily percent return: back-adjusted point P&L over the prior
    current-contract price. Denominator floored away from zero so a single
    distressed print (e.g. WTI April 2020) cannot produce absurd returns."""
    denom = df["price"].shift(1)
    floor = df["price"].rolling(252, min_periods=20).median().shift(1) * 0.1
    denom = denom.where(denom > floor.fillna(0), floor)
    r = df["adj"].diff() / denom
    return r.replace([np.inf, -np.inf], np.nan)


def _contract_year_frac(price_contract: pd.Series, carry_contract: pd.Series) -> pd.Series:
    """Signed year fraction between carry and price contract.

    Upstream labels are YYYYMM00 (eight digits, day always 00)."""
    pc = (price_contract.astype("Int64") // 100)
    cc = (carry_contract.astype("Int64") // 100)
    months = (cc // 100 - pc // 100) * 12 + (cc % 100 - pc % 100)
    yf = months.astype(float) / 12.0
    return yf.replace(0.0, np.nan)


def annualised_carry(df: pd.DataFrame) -> pd.Series:
    """Expected annualised percent return from roll-down, assuming the curve
    is static: (price - carry_price) / year_gap, as a fraction of price.

    Works for either carry-contract convention (earlier or later than the
    priced contract) because the year fraction is signed.
    """
    yf = _contract_year_frac(df["price_contract"], df["carry_contract"])
    raw_points_per_year = (df["price"] - df["carry_price"]) / yf
    denom = df["price"].abs().clip(lower=df["price"].abs().rolling(252, min_periods=20).median() * 0.1)
    return (raw_points_per_year / denom).replace([np.inf, -np.inf], np.nan)
