# BudgetPilot cashflow rules

BudgetPilot forecasts forward, not backward: it answers what still has to
happen to your main account balance between **now** and the **next
income date**, not just what happened this month.

## Payment states

Every entry in `data/payments.json` can carry a `state` field. If absent,
the legacy boolean `paid` is used instead (`paid: true` → `paid_me`,
otherwise `pending`).

| state          | meaning                                   | reduces main forecast? | reduces reserve? |
|----------------|--------------------------------------------|:-----------------------:|:-----------------:|
| `pending`      | not paid yet                               | yes                     | no                |
| `paid_me`      | paid from the main account already         | no (already reflected in the account balance) | no |
| `paid_other`   | paid by someone else                       | no                      | no                |
| `paid_reserve` | paid out of the reserve, not main cash     | no                      | yes               |
| `deferred`     | pushed to a later date (`deferred_to`)     | only if the new date still falls before the next income | no |

The rule in one line: **every pending payment reduces the forecast until
it is marked `paid_me`, `paid_other`, `paid_reserve`, or `deferred`.**

## Deferred payments

A `deferred` payment keeps its original `due_date` unless a
`deferred_to` date is set — that becomes its new effective due date. If
the new date still falls within the current forecast window (today →
next income), it still counts as required. If it moves past the next
income date, it drops out of the *current* window (it becomes a future
month's obligation instead).

## What this produces

`forecast()` in `forecast.py` returns:

- `required_main` — total still owed from the main account before the next income
- `reserve_out` — total drawn from the reserve (informational, doesn't touch main cash)
- `paid_other_total` / `paid_me_total` — informational totals, excluded from `required_main`
- `after_required` — account balance minus `required_main` (money left after mandatory payments)
- `safe_to_spend` — `after_required`, floored at 0
- `days_to_income` / `daily_safe_to_spend` — the safe daily allowance until the next income

This is a pure function: no file I/O, no globals, so it's fully covered
by `tests/test_forecast.py`.
