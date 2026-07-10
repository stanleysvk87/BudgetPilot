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
