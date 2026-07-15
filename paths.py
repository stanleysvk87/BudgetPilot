#!/usr/bin/env python3
"""Shared filesystem locations for BudgetPilot.

The app is local-first and stores runtime data as JSON files. Keep the
default location compatible with the original scripts
(`~/BudgetPilot/data`), while allowing tests or deployments to override it
with BUDGETPILOT_HOME.
"""
import contextlib
import os
import sys
import tempfile
from pathlib import Path


def app_base() -> Path:
    return Path(os.environ.get("BUDGETPILOT_HOME", Path.home() / "BudgetPilot"))


def data_dir() -> Path:
    return app_base() / "data"


# ---- Production-data safety net ----
#
# A test, verification, migration, or diagnostic run that forgets to
# redirect BUDGETPILOT_HOME (or monkeypatch a module's DATA/BASE constant)
# to an isolated directory silently falls back to the real default below
# and can read or overwrite the user's actual household data -- this is
# how real payments/payment_events data was lost in July 2026. This check
# closes that hole: every read/write in json_store.py calls
# guard_against_production_dir() first, and it aborts immediately if it's
# about to touch the real production data directory from anything other
# than the actual running app.
#
# PRODUCTION_DATA_DIR intentionally ignores BUDGETPILOT_HOME so it always
# names the *real* default location, regardless of what a test has
# temporarily pointed the app at.
PRODUCTION_BASE_DIR = (Path.home() / "BudgetPilot").resolve()
PRODUCTION_DATA_DIR = PRODUCTION_BASE_DIR / "data"

# Scripts that can't rely on unittest/pytest being importable (e.g. a
# one-off migration or diagnostic run executed directly) opt into the same
# protection by setting this environment variable, ideally via
# isolated_runtime_dir() below rather than by hand.
TEST_MODE_ENV_VAR = "BUDGETPILOT_TEST_MODE"


class ProductionDataGuardError(RuntimeError):
    """Raised when a test/verification/migration/diagnostic run is about
    to read or write BudgetPilot's live production data/ directory."""


def _test_mode_active() -> bool:
    if os.environ.get(TEST_MODE_ENV_VAR) == "1":
        return True
    # unittest/pytest being loaded is a strong, zero-configuration signal
    # that we're inside a test run rather than the real app -- the actual
    # server never imports either.
    return "unittest" in sys.modules or "pytest" in sys.modules


def guard_against_production_dir(path) -> None:
    """Abort immediately if `path` resolves inside the real production
    data/ directory while running as a test/verification/migration/
    diagnostic script (see _test_mode_active). Always a no-op for the
    real running app, which is the only legitimate caller that has
    neither BUDGETPILOT_TEST_MODE set nor unittest/pytest loaded.
    """
    if not _test_mode_active():
        return
    try:
        resolved = Path(path).resolve()
    except OSError:
        return
    if resolved == PRODUCTION_DATA_DIR or PRODUCTION_DATA_DIR in resolved.parents:
        raise ProductionDataGuardError(
            "Refusing to read/write the production data directory "
            f"({PRODUCTION_DATA_DIR}) from a test/verification/migration/"
            "diagnostic run. Point BUDGETPILOT_HOME (and any module-level "
            "DATA/BASE/*_PATH constants it already captured) at an "
            "isolated directory instead -- see paths.isolated_runtime_dir()."
        )


@contextlib.contextmanager
def isolated_runtime_dir():
    """Create a throwaway BudgetPilot home for tests, verification runs,
    migrations, and diagnostic scripts, and activate the production-data
    guard for the duration.

    Sets BUDGETPILOT_HOME to a fresh temp directory and BUDGETPILOT_TEST_MODE
    to "1" (so guard_against_production_dir() is active even for code paths
    that don't have unittest/pytest loaded), then restores both on exit.

    Code that calls app_base()/data_dir() fresh (e.g. scripts/load_demo_data.py)
    picks this up automatically. Modules that cache DATA/BASE (or derived
    *_PATH constants) at import time still need those specific attributes
    monkeypatched to a path under the yielded directory, same as existing
    tests already do with mock.patch.object(...) -- this context manager
    doesn't (and can't generically) reach into every module's already-bound
    constants.

    Usage:
        with paths.isolated_runtime_dir() as tmp:
            ...  # BUDGETPILOT_HOME == str(tmp) for the duration
    """
    prev_home = os.environ.get("BUDGETPILOT_HOME")
    prev_test_mode = os.environ.get(TEST_MODE_ENV_VAR)
    with tempfile.TemporaryDirectory(prefix="budgetpilot-test-") as tmp:
        os.environ["BUDGETPILOT_HOME"] = tmp
        os.environ[TEST_MODE_ENV_VAR] = "1"
        try:
            yield Path(tmp)
        finally:
            if prev_home is None:
                os.environ.pop("BUDGETPILOT_HOME", None)
            else:
                os.environ["BUDGETPILOT_HOME"] = prev_home
            if prev_test_mode is None:
                os.environ.pop(TEST_MODE_ENV_VAR, None)
            else:
                os.environ[TEST_MODE_ENV_VAR] = prev_test_mode
