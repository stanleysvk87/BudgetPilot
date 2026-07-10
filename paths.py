#!/usr/bin/env python3
"""Shared filesystem locations for BudgetPilot.

The app is local-first and stores runtime data as JSON files. Keep the
default location compatible with the original scripts
(`~/BudgetPilot/data`), while allowing tests or deployments to override it
with BUDGETPILOT_HOME.
"""
import os
from pathlib import Path


def app_base() -> Path:
    return Path(os.environ.get("BUDGETPILOT_HOME", Path.home() / "BudgetPilot"))


def data_dir() -> Path:
    return app_base() / "data"
