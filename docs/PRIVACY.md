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

## Demo data in this repository

Live `data/*.json` files are runtime state and are ignored by git because
they may contain real household finances. Fake, internally consistent demo
numbers live in `data.example/` and in `tests/fixtures/demo_data/` for the
test suite. Copy `data.example/*.json` into `data/` only when you want a
throwaway demo state.

## Your responsibility

Because everything is local, **you** are responsible for protecting these
files the same way you'd protect any other file containing financial
information:

- Don't commit your real `data/*.json` to a public git repository. They are
  ignored by default, but check `git status` before publishing changes.
- `backups/` can contain older copies of your real data — it's gitignored by
  default for the same reason.
- If you back up your data elsewhere (external drive, personal cloud
  storage you control), treat it with the same care you'd give any backup
  of financial records.

BudgetPilot itself has no encryption at rest — the JSON files are plain
text. If your device's disk isn't already encrypted and that matters to
your threat model, consider full-disk encryption at the OS level.
