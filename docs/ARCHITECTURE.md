# Architecture

BudgetPilot is deliberately simple: a scripting-language app over flat JSON
files, no database, no build step, no frontend framework.

```
budgetpilot.py     CLI entry point: loads data/*.json, runs calc_month(),
                    prints a forecast, has a `spend <amount>` subcommand.

budgetpilot_web.py  Flask app. Renders the main UI from templates/ and a
                    small inline auth/setup flow, calls budgetpilot.py as a
                    subprocess for the CLI-derived forecast text, and
                    reads/writes the same runtime JSON files for settings,
                    payments, incomes, expenses, setup, and auth state.

forecast.py         Pure function: forecast(balance, payments, today,
                    next_income) -> dict. No file I/O, no globals — this
                    is what the payment-state rules actually run through.
                    Fully covered by tests/test_forecast.py.

obligations.py       Pure helpers for the monthly cycle: recurring
                    obligation active/cancelled resolution, one-time
                    obligations, debts, account-balance snapshot
                    resolution, first-run needs_setup() check. Covered by
                    tests/test_obligations.py.

receipts.py          Optional local/offline receipt OCR boundary. Uses
                    Tesseract through pytesseract when available, falls
                    back inertly when unavailable, and never saves an
                    OCR result without user review.

data/                JSON data files (settings, users, payments, incomes,
                    expenses, snapshots). Runtime state, ignored by git.

data.example/        Fake demo/example JSON files that can be copied into
                    data/ for a throwaway demo state.

tests/               Standard-library unittest, no pytest or other test
                    framework dependency.
```

## Why a subprocess call from the web app

`budgetpilot_web.py` shells out to `budgetpilot.py` for the forecast text
(`run_core()`) rather than importing and calling its functions directly.
This keeps the CLI's exact printed output as the single source of truth for
the numbers shown on the dashboard, at the cost of a small amount of text
parsing (`parse_dash()`). This is pre-existing behavior, not something
introduced by this documentation pass.

## Local-first design

- No network calls anywhere except serving the local Flask app.
- No external services, no accounts, no API keys.
- Data is plain JSON any text editor can read — nothing proprietary or
  binary.
- The web server host/port are configurable with `BUDGETPILOT_HOST` and
  `BUDGETPILOT_PORT`. The historical default is `0.0.0.0:8765`; Docker
  Compose binds the host side to `127.0.0.1` by default.
- First launch requires creation of a local administrator account stored in
  `data/users.json` as a password hash. Optional Basic Auth remains for
  compatibility through `BUDGETPILOT_PASSWORD`; see [SECURITY.md](SECURITY.md).

## Test isolation and the production-data guard

Every module that persists state funnels through `json_store.py`'s
`read_json()`/`atomic_write_json()` — `budgetpilot.py`, `budgetpilot_web.py`,
`first_run_wizard.py`, `balance_first_summary.py`, `payment_events.py`,
`envelope_editor.py`, and `audit_log.py` all call one of those two
functions rather than opening files themselves. That single chokepoint is
what makes a hard safety rule enforceable: **no test, verification,
migration, or diagnostic run may ever read or write the live `data/`
directory.**

Real household `payments.json`/`payment_events.json` data was lost in
July 2026 because something operated against the live directory instead
of an isolated one. The mechanism below exists specifically to make that
failure mode impossible to reintroduce silently, and it is meant to stay
enabled permanently — it isn't a lint rule to relax under time pressure.

How it works (`paths.py`):

- `paths.PRODUCTION_DATA_DIR` is the real default (`~/BudgetPilot/data`),
  computed independently of any `BUDGETPILOT_HOME` override, so it always
  names the one true production location regardless of what a given
  process has redirected itself to.
- `paths.guard_against_production_dir(path)` raises
  `paths.ProductionDataGuardError` if `path` resolves inside
  `PRODUCTION_DATA_DIR` **and** the process looks like a test/verification/
  migration/diagnostic run — either `unittest`/`pytest` is loaded
  (`sys.modules`), or the `BUDGETPILOT_TEST_MODE=1` environment variable is
  set. It is a no-op otherwise, so the real running server (which imports
  neither test framework and sets no such variable) is never affected.
- `json_store.read_json()` and `json_store.atomic_write_json()` both call
  the guard before doing anything else, so the protection applies
  everywhere data is read or written, with no per-call-site opt-in needed.
- Code that writes outside `json_store` (there's exactly one case,
  `scripts/load_demo_data.py`, which uses `shutil` to seed
  `data.example/*.json`) calls `paths.guard_against_production_dir()`
  explicitly for the same coverage.
- `paths.isolated_runtime_dir()` is a context manager that creates a fresh
  temp directory, points `BUDGETPILOT_HOME` at it, and sets
  `BUDGETPILOT_TEST_MODE=1` for the duration (restoring both on exit) —
  the one-line way for a new test or one-off script to get an isolated
  runtime directory automatically. Modules that cache `DATA`/`BASE` (or
  derived `*_PATH` constants) at import time still need those specific
  attributes monkeypatched with `mock.patch.object(...)`, same as existing
  tests already do; `isolated_runtime_dir()` covers code that calls
  `data_dir()`/`app_base()` fresh (e.g. `scripts/load_demo_data.py`) and
  activates the guard for everything else regardless.

`tests/test_production_data_guard.py` is the regression suite for this
mechanism: it checks the guard fires for the real production path and
stays silent for isolated ones, that `json_store` actually consults it,
that `isolated_runtime_dir()` sets up and tears down its environment
correctly, and — via real subprocesses, since the in-process test suite
always has `unittest` loaded and can't exercise the "bare script" case —
that a plain script with neither `unittest`/`pytest` nor
`BUDGETPILOT_TEST_MODE` set is left alone, while one with
`BUDGETPILOT_TEST_MODE=1` set is blocked from touching production data.

## Historical files

`legacy/` contains earlier Tkinter prototypes and one-off patch scripts
kept for history. They are not part of the supported CLI/web-UI architecture
described above and aren't required to run BudgetPilot today. Some of them
write directly to `~/BudgetPilot`, so treat them as historical reference
only, not release tooling.
