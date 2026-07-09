# Privacy

BudgetPilot is designed to be local-first:

- No bank login, no Open Banking connection, no bank scraping.
- No cloud account, no cloud sync, no telemetry, no analytics.
- No third-party API calls of any kind.
- All data lives in plain JSON files under `data/` on the machine you run
  it on.

## What is stored

- `data/settings.json` — account balance, reserve, payday day
- `data/payments.json` — your bills/obligations and their payment states
- `data/incomes.json` — your income sources
- `data/expenses.json` — manual expense log
- `data/snapshots.json` — history of payday balance snapshots

None of this is transmitted anywhere by BudgetPilot. It only ever reads and
writes these files on local disk.

## The data shipped in this repository

`data/*.json` in this repository ships with small, fake, internally
consistent demo numbers (a demo mortgage, electricity bill, internet,
insurance, a subscription, a loan installment) — not real financial data
from any household. It exists so the app has something to show immediately
after cloning. Replace it with your own numbers once you're ready to use
BudgetPilot for real, either by hand-editing the JSON or through the web
UI's forms.

## Your responsibility

Because everything is local, **you** are responsible for protecting these
files the same way you'd protect any other file containing financial
information:

- Don't commit your real `data/*.json` to a public git repository. If you
  fork or clone this project for your own use, keep your real data files
  out of version control (see `.gitignore`) or in a private repository.
- `backups/` (created by `rollback_latest.sh`) can contain older copies of
  your real data — it's gitignored by default for the same reason.
- If you back up your data elsewhere (external drive, personal cloud
  storage you control), treat it with the same care you'd give any backup
  of financial records.

BudgetPilot itself has no encryption at rest — the JSON files are plain
text. If your device's disk isn't already encrypted and that matters to
your threat model, consider full-disk encryption at the OS level.
