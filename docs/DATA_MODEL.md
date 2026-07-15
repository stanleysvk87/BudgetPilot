# Data model

Runtime data lives in plain JSON files under `data/`. There is no database.
Nothing here is a bank format — every file is written and read only by
this codebase, in whatever shape it already understands. `data/*.json` is
ignored by git; fake demo data lives in `data.example/` and test fixtures
live in `tests/fixtures/demo_data/`.

Backups created by the web UI live under `backups/` in the same
`BUDGETPILOT_HOME`. Docker stores both `data/` and `backups/` inside the
named `/var/lib/budgetpilot` volume.

## `data/settings.json`

Household-level settings:

```json
{
  "account_balance": 400.0,
  "use_reserve": true,
  "safe_min": 300.0,
  "payday_day": 15,
  "real_balance": 400.0,
  "reserve_amount": 300.0
}
```

- `account_balance` / `real_balance` — current main-account balance (kept in
  sync; `real_balance` is the newer field written by `/setup`).
- `use_reserve` / `safe_min` — whether a minimum reserve buffer applies and
  its amount.
- `payday_day` — day of month income arrives; used with `next_income_date`.
- `reserve_amount` — the separate reserve balance, distinct from the main
  account.

## `data/payments.json`

A list of bills/obligations. Fields accumulated over several slices, all
backward compatible:

```json
{
  "id": "demo-hypoteka",
  "name": "Hypotéka",
  "amount": 750.0,
  "day": 20,
  "due_day": 20,
  "frequency": "monthly",
  "start": "2026-01-20",
  "start_month": "2026-01",
  "priority": "mandatory",
  "flexibility": "hard_due",
  "active": true
}
```

- `frequency` — `monthly` / `quarterly` / `yearly` / `custom_months`
  (with `every_months`).
- `priority` — `mandatory` / `important` / `optional`.
- `flexibility` — `hard_due` / `can_defer` / `optional`.
- `active` / `cancelled_from_month` — whether a recurring obligation still
  applies; cancelling sets one of these instead of deleting the entry.
- Payment state is cycle-scoped in `data/payment_events.json`; recurring
  templates should not carry permanent `state`/`paid` values. Legacy entries
  with those fields still parse for compatibility.

Recurring obligations added via `/setup` are written into this same file
(not a separate one) with the full field set above, so the original
CLI/dashboard code paths keep working unchanged.

## `data/payment_events.json`

Cycle-scoped payment state. Recurring templates in `payments.json` describe
what exists; this file records whether a specific cycle's occurrence is
`pending`, `paid_me`, `paid_other`, `paid_reserve`, or `deferred`.

## `data/users.json`

Created when the first local administrator account is submitted at
`/auth/setup`. It stores the username and Werkzeug password hash. It does
not store the plaintext password.

## `data/incomes.json`

A list of income sources: `name`, `amount`, `day`, `frequency`, `start`.

## `data/expenses.json`

Manual one-off spending log:

```json
{
  "name": "Nafta",
  "amount": 45.0,
  "date": "2026-07-08",
  "source": "manual"
}
```

- `source` — `manual` / `ocr` / `import`, defaults to `manual`. OCR entries
  are created only after user review — see [receipt_ocr.md](receipt_ocr.md).
- Optional receipt metadata fields (`receipt_id`, `merchant`,
  `original_image_path`, `ocr_confidence`, `ocr_raw_text`, `needs_review`)
  are supported by the data model but unused until OCR exists.

## `data/snapshots.json`

Created the first time you submit a balance via `/setup`. A history of
payday balance snapshots: date, real balance, reserve, optional note. The
most recent snapshot is always preferred over `settings.json` when
resolving the current balance — see `obligations.resolve_account_balance()`.

## `data/envelopes.json`

Monthly category limits. Each envelope has a category/name and a monthly
limit; current spending is calculated from `data/expenses.json` for the
open month.

## `data/debts.json`

`obligations.py` has a `debt_to_payment()` helper that converts an `I_owe`
debt into a normal pending payment. Money marked `owed_to_me` is never
converted into spendable forecast — it only counts once it's confirmed
`received`, so BudgetPilot never shows a misleading safe-to-spend number.

## Other runtime files

- `data/onetime.json` — one-time obligations entered through the web UI.
- `data/audit_log.json` — recent local audit entries for important actions.
- `data/.session_secret_key` — generated Flask session signing secret; back
  it up with `data/` so browser sessions and CSRF tokens survive restarts.
- `data/receipts/` — uploaded receipt images and review JSON when the
  optional receipt OCR flow is used.
