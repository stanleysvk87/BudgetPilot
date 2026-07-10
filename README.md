# BudgetPilot

BudgetPilot is a small, local-first household **forward-cashflow** app. It
answers one question: *between now and my next payday, what still has to
happen to my account balance, and how much can I actually spend?*

It is not a bookkeeping app and not a bank-sync budgeting app — it does not
try to categorize your past transactions. It looks forward, not backward.

## What problem it solves

Most budgeting apps show you what you already spent. BudgetPilot instead
tracks what's still coming:

- what must still be paid before your next payday
- what's due soon vs. what can be deferred
- what's already been paid (and by whom, or from which account)
- how many days remain until payday
- how much you can safely spend today without missing an upcoming bill

## What it is not

- **Not a bank-sync app.** No bank login, no Open Banking, no scraping.
  Balances and payments are entered by hand.
- **Not AI-powered.** No LLM, no "smart" categorization.
- **Not a cloud service.** No account, no server other than the one you run
  yourself, no data leaves your machine.
- **Receipt OCR is local/offline and optional.** Photo upload uses
  Tesseract when installed, then always requires manual review before an
  expense is saved. See [`docs/receipt_ocr.md`](docs/receipt_ocr.md).
- **No authentication.** It's built for trusted use on your own LAN, not for
  exposing to the public internet. See [`docs/SECURITY.md`](docs/SECURITY.md).

## Main features

- Forward cashflow forecast: safe-to-spend today and per day until payday
- Payment states per bill: `pending`, `paid_me`, `paid_other`, `paid_reserve`,
  `deferred` — see [`docs/cashflow_rules.md`](docs/cashflow_rules.md)
- Recurring obligations (rent, loan, insurance, subscriptions) that persist
  month to month until cancelled
- Payday balance snapshot as the source of truth for each new cycle
- Manual expense log
- Both a CLI (`budgetpilot.py`) and a Flask web dashboard
  (`budgetpilot_web.py`) reachable from other devices on your LAN (e.g. a
  phone)

## Current project status

Active MVP under development. The forecast engine, payment-state model,
envelopes, debts, receipt review flow, and multi-month forecast are
implemented and unit-tested. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for
what's next.

Older Tkinter GUI prototypes (`budgetpilot_gui*.py`) and one-off patch
scripts (`fix_*.py`) exist from earlier iterations of this project and are
kept for history; the supported way to use BudgetPilot today is the CLI and
the Flask web UI.

## Local-first philosophy

Your financial data stays in plain JSON files on your own disk
(`data/*.json`). Runtime data is ignored by git; demo/example data lives in
`data.example/` and test fixtures live in `tests/fixtures/`. There is no
network call anywhere in this codebase except serving the local web UI. You
can inspect, back up, or edit the data files directly with a text editor.

## Screenshots

*(not yet captured — the web dashboard is at `http://localhost:8765` once
running; add screenshots here once available)*

## Quick start

Requires Python 3.10+. Flask is needed for the web UI; `pytesseract` and
Pillow are optional for receipt OCR.

```bash
git clone <this-repo>
cd BudgetPilot
pip install -r requirements.txt
```

On a fresh install, BudgetPilot will start at the first-run setup flow. To
try the fake demo numbers instead, run `python3 scripts/load_demo_data.py`
before starting the app.

### Run the CLI

```bash
python3 budgetpilot.py
```

Prints the current month's forecast: totals, safe-to-spend, and a verdict.
Check whether you can afford a purchase:

```bash
python3 budgetpilot.py spend 45.90
```

### Run the web UI

```bash
python3 budgetpilot_web.py
```

Open `http://localhost:8765` in a browser.

### Open it from another device on your LAN (e.g. your phone)

The web server already binds to `0.0.0.0`, so it's reachable from other
devices on the same network. Find your computer's LAN IP
(`ip addr` / `hostname -I` on Linux) and open
`http://<your-lan-ip>:8765` from your phone or another computer on the same
Wi-Fi. Do not port-forward this to the public internet — see
[`docs/SECURITY.md`](docs/SECURITY.md).

### Run the tests

```bash
python3 -m unittest discover -s tests
```

## Project structure

```
budgetpilot.py         CLI: forecast, print_month, spend check
budgetpilot_web.py      Flask web dashboard + /setup first-run flow
forecast.py             Pure forecast function + payment-state rules
obligations.py          Pure helpers: recurring/one-time obligations, debts,
                         account-balance snapshot resolution
receipts.py              Local OCR parsing + mandatory review helper
data/                    Your local JSON runtime data (gitignored)
data.example/            Fake demo/example JSON data you can copy into data/
backups/                 Local backups made by rollback_latest.sh (gitignored)
docs/                    Documentation (see below)
tests/                   Unit tests (stdlib unittest, no extra dependency)
budgetpilot_gui*.py      Older Tkinter prototypes, kept for history
fix_*.py, rollback_latest.sh   One-off historical patch scripts, kept for history
```

## Documentation

- [docs/QUICKSTART.md](docs/QUICKSTART.md) — fastest path to running it
- [docs/INSTALL.md](docs/INSTALL.md) — Python/Flask setup, troubleshooting
- [docs/USAGE.md](docs/USAGE.md) — first-run setup, payday snapshots, states
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — the JSON files explained
- [docs/CASHFLOW_LOGIC.md](docs/CASHFLOW_LOGIC.md) — the forecast rules in
  plain language
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the pieces fit together
- [docs/ROADMAP.md](docs/ROADMAP.md) — what's built, what's next
- [docs/PRIVACY.md](docs/PRIVACY.md) — what data BudgetPilot keeps and where
- [docs/SECURITY.md](docs/SECURITY.md) — LAN-only assumptions, no auth yet
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — how to contribute safely
- [CHANGELOG.md](CHANGELOG.md) — human-readable history of major changes

Deeper technical notes on the current rule set already exist in
[`docs/cashflow_rules.md`](docs/cashflow_rules.md) and
[`docs/monthly_cycle.md`](docs/monthly_cycle.md).

## Safety / privacy notes

- `data/*.json` is local runtime state and is ignored by git. Fake demo
  numbers are kept in `data.example/` and `tests/fixtures/demo_data/` (see
  [docs/PRIVACY.md](docs/PRIVACY.md)).
- Nothing in this project sends data anywhere. There is no analytics, no
  telemetry, no third-party API call.
- There is no login. Anyone who can reach the web UI's address (e.g. anyone
  on your LAN) can view and edit your data. Keep it off the public internet;
  use a VPN (WireGuard/Tailscale) for remote access instead.

## License

MIT — see [LICENSE](LICENSE).
