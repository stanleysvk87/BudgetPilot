# Data model

All data lives in plain JSON files under `data/`. There is no database.
Nothing here is a bank format — every file is written and read only by
this codebase, in whatever shape it already understands.

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
  "active": true,
  "state": "pending",
  "paid": false
}
```

- `frequency` — `monthly` / `quarterly` / `yearly` / `custom_months`
  (with `every_months`).
- `priority` — `mandatory` / `important` / `optional`.
- `flexibility` — `hard_due` / `can_defer` / `optional`.
- `active` / `cancelled_from_month` — whether a recurring obligation still
  applies; cancelling sets one of these instead of deleting the entry.
- `state` — one of the five payment states (see
  [CASHFLOW_LOGIC.md](CASHFLOW_LOGIC.md)). Legacy entries have no `state`
  and fall back to the `paid` boolean (`true` → `paid_me`, else `pending`).
- `deferred_to` — present only when `state` is `deferred`.

Recurring obligations added via `/setup` are written into this same file
(not a separate one) with the full field set above, so the original
CLI/dashboard code paths keep working unchanged.

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

- `source` — `manual` / `ocr` / `import`, defaults to `manual`. `ocr` is
  reserved for a future feature and never set by anything today — see
  [receipt_ocr.md](receipt_ocr.md).
- Optional receipt metadata fields (`receipt_id`, `merchant`,
  `original_image_path`, `ocr_confidence`, `ocr_raw_text`, `needs_review`)
  are supported by the data model but unused until OCR exists.

## `data/snapshots.json`

Created the first time you submit a balance via `/setup`. A history of
payday balance snapshots: date, real balance, reserve, optional note. The
most recent snapshot is always preferred over `settings.json` when
resolving the current balance — see `obligations.resolve_account_balance()`.

## Categories / envelopes (not yet implemented)

Planned monthly spending categories (food, fuel, children, pharmacy,
household, car, school, subscriptions, restaurant, other) with a budget
envelope per category are designed but not built — see
[ROADMAP.md](ROADMAP.md). No fields for this exist in `data/expenses.json`
yet.

## Debts (pure helpers only, no UI yet)

`obligations.py` has a `debt_to_payment()` helper that converts an `I_owe`
debt into a normal pending payment. Money marked `owed_to_me` is never
converted into spendable forecast — it only counts once it's confirmed
`received`, so BudgetPilot never shows a misleading safe-to-spend number.
