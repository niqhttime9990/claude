#!/usr/bin/env python3
"""Fetch the pinned futures data snapshot into data/raw."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctabot.config import PATHS
from ctabot.data import fetch_universe


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = fetch_universe(root / PATHS.raw_dir, root / PATHS.manifest)
    n = len(manifest["instruments"])
    print(f"\nfetched {n} instruments, manifest written to {PATHS.manifest}")


if __name__ == "__main__":
    main()
