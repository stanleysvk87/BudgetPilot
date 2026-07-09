# BudgetPilot monthly cycle

BudgetPilot is a household forward-cashflow calendar, not an expense
tracker. This document explains the parts of the model that keep it
correct from one month to the next: first-run setup, recurring
obligations, and the payday balance snapshot.

## First-run setup

BudgetPilot needs two things before it can forecast reliably: a **payday
day of month** and a **real account balance**. Until both are set,
`needs_setup()` (in `obligations.py`) returns `True` and the dashboard
shows a banner linking to `/setup`.

This is intentionally *not* a blocking wizard — the existing dashboard
(`/`) keeps working even while setup is incomplete, so a household with
data already entered isn't locked out. `/setup` lets you:

- enter the real current balance and an optional reserve amount
- set the payday day of month
- add recurring monthly obligations (name, amount, due day, priority,
  flexibility)
- cancel/reactivate a recurring obligation

## Recurring obligations

Recurring obligations added through `/setup` are stored in the same
`data/payments.json` used by the original CLI and dashboard — there is
no separate file to keep in sync. Each one carries a superset of fields
so both engines understand it:

- `day` / `due_day` — day of month it's due (kept in sync)
- `frequency` — defaults to `"monthly"`
- `start` / `start_month` — when it starts applying
- `priority` — `mandatory` / `important` / `flexible` / `optional`
- `flexibility` — `hard_due` / `can_defer` / `optional`
- `active` — `true` until cancelled
- `cancelled_from_month` (optional) — a `"YYYY-MM"` from which it stops
  applying, without deleting its history

A recurring obligation appears **every month** until you cancel it from
`/setup` — you never have to re-enter rent, a loan, or a subscription.
Cancelling flips `active` to `false` (or sets `cancelled_from_month`);
it stops appearing in that month's forecast but the entry itself isn't
deleted.

Legacy entries in `data/payments.json` (rent, utilities, insurance —
anything added before this slice) have no `active` field. They default
to active, so nothing already configured changes behavior.

The pure logic lives in `obligations.py`:
- `is_recurring_active(item, year, month)` — active/cancelled/start-date checks
- `recurring_due_date(item, year, month)` — resolves the due date for a given month
- `generate_recurring_for_month(recurring, year, month)` — both combined

`budgetpilot.py`'s `occurs()` (used by the CLI and the real forecast
numbers) was extended with the same `active` / `cancelled_from_month`
checks, so cancelling an obligation in `/setup` actually removes it from
the forecast, not just from the new pure-function layer.

## Recurring payment template vs. monthly/cycle payment event

A recurring payment in `data/payments.json` is a **template**: it
describes the obligation (name, amount, due day, priority, flexibility),
not whether this month's occurrence has been paid. Marking Electricity
paid in July must not make it appear paid in August — the template is
the same row every month, so baking a permanent `paid`/`state` field onto
it would leak that state forward into every future cycle. That was the
bug this slice fixes.

Instead, state changes live in `data/payment_events.json`, one event per
`(payment_id, cycle_key)`:

```json
{
  "payment_id": "demo-elektrina",
  "cycle_key": "2026-07",
  "state": "paid_me",
  "deferred_to": "2026-07-14",
  "note": "optional",
  "updated_at": "2026-07-09T09:00:00"
}
```

Rules (`payment_events.py`):

- If no event exists for a `(payment_id, cycle_key)` pair, the effective
  state is `pending` — always, even if the template has a leftover
  legacy `state`/`paid` field from before this model existed.
- An event for one cycle never affects another cycle.
  `apply_payment_events(payments, events, cycle_key)` resolves the
  effective state for exactly one cycle at a time and is what both
  `budgetpilot.py`'s `calc_month()` and `budgetpilot_web.py`'s dashboard
  call before forecasting or rendering.
- Web state actions (`POST /payment/state/<i>`, `POST /payment/defer/<i>`)
  write only to `payment_events.json` for the current cycle
  (`payment_events.get_current_cycle_key()`), never to the template.
- Editing a recurring payment (`POST /payment/update/<i>`) only ever
  touches the template fields the edit form exposes — it cannot change
  any cycle's event.

`cycle_key` currently uses `"YYYY-MM"` (calendar month), but the
functions are named around "cycle" rather than "month"
(`cycle_key_for_date`, `get_current_cycle_key`, "payment event" /
"payment occurrence") on purpose: a future slice may switch to
payday-to-payday cycles instead of calendar months without reshaping
this module, only changing how `get_current_cycle_key()` computes the
key.

## One-time obligations and debts

Two more concepts exist as pure helpers (`obligations.py`) but don't yet
have a dedicated UI in this slice:

- **One-time obligations** — `generate_onetime_for_month()` includes an
  item only in the month its `due_date` falls in.
- **Debts** — `debt_to_payment()` converts an `I_owe` debt into a normal
  pending obligation that reduces the forecast when due. Money marked
  `owed_to_me` is **never** converted — it is not safe/spendable money
  until it's explicitly marked `received` (BudgetPilot must never show a
  misleading safe-to-spend amount by counting money that hasn't arrived).

## Payday balance snapshot

On payday, enter the real current balance in `/setup`. This:

1. Overwrites `account_balance` / `real_balance` in `data/settings.json`
   — the number the whole dashboard and CLI already use.
2. Appends an entry to `data/snapshots.json` (date, real balance, reserve,
   optional note) — a history of what the account actually held on each
   payday.

`obligations.resolve_account_balance(settings, snapshots)` always
prefers the most recent snapshot over whatever is sitting in `settings`,
so a fresh payday balance overrides any assumptions carried over from
the previous month. This is the "source of truth" rule: the real balance
you type in on payday wins, always.

## What is intentionally not included yet

- No bank integration — balances are entered by hand.
- No AI.
- No OCR (receipt/bill scanning may be considered later, not now).
- No cloud sync — everything lives in local JSON files.
- No authentication — this app is for LAN use on a trusted home network.
- No database — the data model stays small, backwards-compatible JSON
  until the current approach actually can't keep up.
