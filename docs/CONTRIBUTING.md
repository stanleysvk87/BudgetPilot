# Contributing

BudgetPilot is meant to stay a small, understandable personal tool. Please
keep contributions in that spirit.

## Ground rules

- **Keep changes small.** Prefer a focused slice over a broad rewrite.
  Don't refactor unrelated code while fixing something else.
- **Add tests.** New pure-function logic (forecast rules, obligation
  helpers) should land with `unittest`-based tests in `tests/`. This
  project uses only the Python standard library for testing — please don't
  introduce `pytest` or another framework.
- **No casual new dependencies**, especially:
  - no bank integration or Open Banking libraries
  - no AI/LLM SDKs
  - no cloud sync or hosted-backend services
  These may be discussed for the future (see
  [ROADMAP.md](ROADMAP.md)), but should never be added as a side effect of
  an unrelated change.
- **Preserve local-first design.** No network calls except serving the
  local web UI. No telemetry.
- **Preserve data compatibility.** `data/*.json` fields already carry
  several backward-compatible aliases (e.g. `paid` vs. `state`, `day` vs.
  `due_day`). Prefer adding a new optional field over changing the meaning
  of an existing one, so existing data files keep working unmodified.
- **Document calculation changes.** If you change anything in
  `forecast.py` or `obligations.py`, update
  [docs/cashflow_rules.md](cashflow_rules.md) and/or
  [docs/monthly_cycle.md](monthly_cycle.md) in the same change — these
  documents are meant to describe the actual current behavior, not the
  original design intent.
- **Never let a test, verification, migration, or diagnostic script touch
  the live `data/` directory.** Real household payments/payment_events
  data was lost this way in July 2026. Every module that reads or writes
  a data file goes through `json_store.read_json()`/`atomic_write_json()`,
  and both call `paths.guard_against_production_dir()` first — this
  aborts immediately (raising `paths.ProductionDataGuardError`) if a
  test/verification/migration/diagnostic run is about to touch the real
  `~/BudgetPilot/data`. It's a permanent, always-on safety net, not
  something to configure per change. New tests and one-off scripts should
  isolate themselves with `paths.isolated_runtime_dir()` (or the existing
  `tempfile.TemporaryDirectory()` + `mock.patch.object(module, "DATA", ...)`
  pattern already used throughout `tests/`) rather than relying on it as a
  first line of defense — it exists to catch the mistake, not to be routinely
  triggered. See [ARCHITECTURE.md](ARCHITECTURE.md#test-isolation-and-the-production-data-guard)
  for how it's wired up, and `tests/test_production_data_guard.py` for the
  regression tests that pin this behavior down.

## Before submitting a change

```bash
python3 -m unittest discover -s tests
python3 budgetpilot.py
```

Both should succeed without errors, and the test count shouldn't silently
shrink.

If you are preparing a public push or release, also run through
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). In particular, never commit
live `data/*.json`, receipt photos, or `backups/`.

## Where things live

See [ARCHITECTURE.md](ARCHITECTURE.md) for a map of the codebase.
