# Architecture

BudgetPilot is deliberately simple: a scripting-language app over flat JSON
files, no database, no build step, no frontend framework.

```
budgetpilot.py     CLI entry point: loads data/*.json, runs calc_month(),
                    prints a forecast, has a `spend <amount>` subcommand.

budgetpilot_web.py  Flask app. Renders an HTML dashboard via
                    render_template_string (no separate templates/
                    directory), calls budgetpilot.py as a subprocess for
                    the CLI-derived forecast text, and reads/writes the
                    same data/*.json files directly for everything else
                    (settings, payments, incomes, expenses, setup flow).

forecast.py         Pure function: forecast(balance, payments, today,
                    next_income) -> dict. No file I/O, no globals — this
                    is what the payment-state rules actually run through.
                    Fully covered by tests/test_forecast.py.

obligations.py       Pure helpers for the monthly cycle: recurring
                    obligation active/cancelled resolution, one-time
                    obligations, debts, account-balance snapshot
                    resolution, first-run needs_setup() check. Covered by
                    tests/test_obligations.py.

receipts.py          Placeholder-only OCR extension point. No OCR engine,
                    no image reading, not called from anywhere yet.
                    Covered by tests/test_receipts.py (asserts it stays
                    inert).

data/                JSON data files (settings, payments, incomes,
                    expenses, snapshots). No database.

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
- The web server binds `0.0.0.0` so it's reachable on your LAN (e.g. from a
  phone), but has no authentication — see [SECURITY.md](SECURITY.md).

## Historical files

`budgetpilot_gui.py`, `budgetpilot_gui_v2.py`, `budgetpilot_gui_v3.py`
(Tkinter prototypes), `add_gui_lists.py`, and the `fix_*.py` /
`rollback_latest.sh` scripts are earlier, ad-hoc iterations of this project
kept for history. They are not part of the supported CLI/web-UI
architecture described above and aren't required to run BudgetPilot today.
