# BudgetPilot

BudgetPilot is a privacy-focused, self-hosted household **forward-cashflow** app. It
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
- **Local administrator login.** On first launch, create the local admin
  account. Optional Basic Auth remains for existing deployments. See
  [`docs/SECURITY.md`](docs/SECURITY.md).

## Main features

- Forward cashflow forecast: safe-to-spend today and per day until payday
- Payment states per bill: `pending`, `paid_me`, `paid_other`, `paid_reserve`,
  `deferred` — see [`docs/cashflow_rules.md`](docs/cashflow_rules.md)
- Recurring obligations (rent, loan, insurance, subscriptions) that persist
  month to month until cancelled
- Payday balance snapshot as the source of truth for each new cycle
- Manual expense log
- Monthly envelopes for planned flexible spending
- Local/offline receipt OCR review flow when optional OCR dependencies are
  installed
- Local administrator login, with optional Basic Auth compatibility for
  existing trusted LAN deployments
- Slovak and English web UI with a visible language switcher and persisted
  browser preference
- Both a CLI (`budgetpilot.py`) and a Flask web dashboard
  (`budgetpilot_web.py`) reachable from other devices on your LAN (e.g. a
  phone)

## Current project status

Active MVP under development. The forecast engine, payment-state model,
envelopes, debts, receipt review flow, first-run setup, CSRF protection, and
multi-month forecast are implemented and unit-tested. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) for what's next.

## Deployment safety

Publishing the source code on GitHub is different from safely exposing a
running BudgetPilot instance. A live instance contains personal financial
data and write actions.

BudgetPilot now requires a local administrator account on first launch and
protects financial pages by default, but the supported deployment model for
the first public release is still **localhost, trusted LAN, or private VPN
/ Tailscale access**. Do not expose it directly to the public internet.
HTTPS, Docker, or a reverse proxy are useful transport/deployment tools, but
they are not a substitute for authentication and network access control.

Older Tkinter GUI prototypes and one-off patch scripts live in `legacy/`
for history; the supported way to use BudgetPilot today is the CLI and the
Flask web UI.

## Local-first philosophy

Your financial data stays in plain JSON files on your own disk
(`data/*.json`). Runtime data is ignored by git; demo/example data lives in
`data.example/` and test fixtures live in `tests/fixtures/`. There is no
network call anywhere in this codebase except serving the local web UI. You
can inspect, back up, or edit the data files directly with a text editor.

## Screenshots

Screenshots must be captured from sanitized demo data only. The public
documentation set is generated from an isolated synthetic runtime:

```bash
npm install
npx playwright install chromium
npm run screenshots:public
```

Generated screenshots live in `docs/assets/screenshots/`.

## Quick start

Requires Python 3.10+. Flask is needed for the web UI; `pytesseract` and
Pillow are optional for receipt OCR.

```bash
git clone https://github.com/stanleysvk87/BudgetPilot.git
cd BudgetPilot
pip install -r requirements.txt
```

On a fresh install, BudgetPilot will start with local administrator creation,
then financial setup. To try the fake demo numbers instead, run
`python3 scripts/load_demo_data.py` before starting the app.

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

### Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8765`. The provided Compose file stores the
container's persistent runtime home in a named Docker volume and binds the port to `127.0.0.1` by
default. On first launch, create the local administrator account in the
browser. See [docs/DOCKER.md](docs/DOCKER.md) before enabling LAN access.

### Configuration

BudgetPilot works without environment variables. Optional settings:

- `BUDGETPILOT_HOME` — runtime home; data is stored in
  `$BUDGETPILOT_HOME/data`. If unset, the historical default is
  `~/BudgetPilot/data`.
- `BUDGETPILOT_PASSWORD` — enables HTTP Basic Auth for the web UI.
- `BUDGETPILOT_USER` — Basic Auth username. The default remains `saldo` for
  compatibility. New installations should use the first-run local
  administrator account instead of relying on Basic Auth alone.

Copy `.env.example` only as a starting point for private local configuration.
Do not commit real credentials.

### Open it from another device on your LAN (e.g. your phone)

Native runs default to `0.0.0.0:8765` for historical compatibility, while
Docker Compose binds to `127.0.0.1` on the host by default. Find your
computer's LAN IP
(`ip addr` / `hostname -I` on Linux) and open
`http://<your-lan-ip>:8765` from your phone or another computer on the same
Wi-Fi only after creating the local administrator account and confirming the
network is trusted. Do not port-forward this to the public internet — see
[`docs/SECURITY.md`](docs/SECURITY.md).

### Run the tests

```bash
python3 -m unittest discover -s tests
```

Browser tests and visual review require Node and Playwright:

```bash
npm install
npx playwright install chromium
npm run test:e2e
npm run review:chromium
```

See [docs/BROWSER_TESTING.md](docs/BROWSER_TESTING.md) for headed mode,
environment variables, screenshot capture, and cleanup.

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
backups/                 Local data backups (gitignored)
docs/                    Documentation (see below)
tests/                   Unit tests (stdlib unittest, no extra dependency)
legacy/                  Older Tkinter prototypes and one-off patch scripts
```

## Documentation

- [docs/QUICKSTART.md](docs/QUICKSTART.md) — fastest path to running it
- [docs/INSTALL.md](docs/INSTALL.md) — Python/Flask setup, troubleshooting
- [docs/DOCKER.md](docs/DOCKER.md) — Docker Compose setup and backup notes
- [docs/USAGE.md](docs/USAGE.md) — first-run setup, payday snapshots, states
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — the JSON files explained
- [docs/CASHFLOW_LOGIC.md](docs/CASHFLOW_LOGIC.md) — the forecast rules in
  plain language
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the pieces fit together
- [docs/LOCALIZATION.md](docs/LOCALIZATION.md) — Slovak/English localization and adding languages
- [docs/BROWSER_TESTING.md](docs/BROWSER_TESTING.md) — Playwright/Chromium tests and screenshots
- [docs/ROADMAP.md](docs/ROADMAP.md) — what's built, what's next
- [docs/PRIVACY.md](docs/PRIVACY.md) — what data BudgetPilot keeps and where
- [docs/SECURITY.md](docs/SECURITY.md) — LAN-only assumptions and optional password protection
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — how to contribute safely
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — checks before
  pushing/publishing
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
- Create the first-run administrator account before entering financial data.
  Keep the application off the public internet; use a VPN (WireGuard or
  Tailscale) for remote access instead.

## Language support

The web UI supports Slovak and English. Slovak is the source/fallback
language; English is provided through `translations/en.json`. The selected
language is persisted in the browser. See
[docs/LOCALIZATION.md](docs/LOCALIZATION.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
