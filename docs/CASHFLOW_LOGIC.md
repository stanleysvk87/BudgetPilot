# Cashflow logic, in plain language

BudgetPilot's core question: *how much of my current balance is actually
free to spend, once I account for everything still owed before my next
payday?*

This document is a plain-language summary. The precise rules, edge cases,
and the web UI's mapping of buttons to states live in
[cashflow_rules.md](cashflow_rules.md); the monthly cycle (setup, recurring
obligations, payday snapshot) lives in [monthly_cycle.md](monthly_cycle.md).

## The one-line rule

**Every pending payment reduces the forecast until it is marked `paid_me`,
`paid_other`, `paid_reserve`, or `deferred`.**

## What each state means for your forecast

- **`pending`** — not paid yet. Counted against your available balance.
- **`paid_me`** — you already paid it from your main account. Not
  subtracted again — your account balance already reflects it.
- **`paid_other`** — someone else paid it (e.g. a partner from their own
  account). Doesn't reduce your main balance, because it was never your
  money that moved.
- **`paid_reserve`** — paid out of a separate reserve, not your main cash.
  Reduces the reserve figure, not the main forecast.
- **`deferred`** — pushed to a later date. Still counts if that later date
  is still before your next payday; drops out of the current forecast
  window if it lands after payday (it becomes next cycle's concern).

## Avoiding double-counting

The payday balance snapshot is the reset point: whatever real balance you
enter on payday becomes the new source of truth, overriding any running
total from the previous cycle. This is deliberate — it means a manual
expense you logged mid-month, or a payment you marked paid, never gets
counted twice once a new snapshot is taken. See "Payday balance snapshot"
in [monthly_cycle.md](monthly_cycle.md) for the exact resolution order.

## What comes out of the forecast

- `required_main` — still owed from the main account before payday
- `reserve_out` — drawn from reserve (informational; doesn't touch main
  cash)
- `after_required` — balance minus what's still required
- `safe_to_spend` — `after_required`, floored at 0
- `daily_safe_to_spend` — that amount divided across the days left until
  payday

This calculation (`forecast()` in `forecast.py`) is a pure function with no
file I/O — it's fully exercised by `tests/test_forecast.py`.
