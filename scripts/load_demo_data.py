#!/usr/bin/env python3
"""Load fake demo data into the local runtime data directory.

Existing data is backed up first. This is meant for local demos and UI
smoke testing, not as part of normal household use.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paths import app_base, data_dir  # noqa: E402


def _has_runtime_data(path: Path) -> bool:
    return path.exists() and any(path.glob("*.json"))


def main() -> int:
    source = ROOT / "data.example"
    target = data_dir()

    if not source.exists():
        print(f"Demo data not found: {source}", file=sys.stderr)
        return 1

    if _has_runtime_data(target):
        backup = app_base() / "backups" / f"{datetime.now():%Y%m%d-%H%M%S}-before-demo-load"
        shutil.copytree(target, backup / "data")
        print(f"Backed up current data to {backup / 'data'}")

    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(source.glob("*.json")):
        shutil.copy2(src, target / src.name)

    print(f"Loaded demo data into {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
