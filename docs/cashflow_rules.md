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

## Web UI actions → payment states

The payments table in `budgetpilot_web.py` exposes a state selector per
payment (`POST /payment/state/<i>`) plus a dedicated "Odložiť o 7 dní"
button (`POST /payment/defer/<i>`). Both call the same helpers used by
the tests, so there is no calculation logic duplicated in the web route:

| button / select value          | maps to                          |
|---------------------------------|-----------------------------------|
| Nezaplatené                     | `pending`                         |
| Zaplatené z účtu                | `paid_me`                         |
| Zaplatil niekto iný              | `paid_other`                      |
| Zaplatené z rezervy              | `paid_reserve`                    |
| Odložiť o 7 dní                 | `deferred`, `obligations.defer_payment()` |

`obligations.set_payment_state()` changes only the `state` (and syncs the
legacy `paid` boolean for anything still reading it) — every other field
on the payment (id, priority, flexibility, active, start_month, ...) is
preserved untouched. `obligations.defer_payment()` does the same, adding
7 days to the current `deferred_to` (or to today, the first time).

**Known limitation:** the current data model has no per-cycle due-date
override, so "Odložiť" always adds a flat 7 days rather than letting you
pick an arbitrary new date. If the new date lands after the next payday,
`forecast()` correctly drops it out of the *current* forecast window
(see `test_deferred_past_horizon_excluded_from_current_window`) — it
simply becomes a concern for the next cycle instead.

## Demo/default data

`data/*.json` ships with a small, fake, internally-consistent household
dataset (mortgage, electricity, internet, car insurance, kindergarten,
a subscription, a loan installment, plus a couple of manual expenses)
sized so the forecast numbers can be checked by hand. It is **not**
real financial data — replace it with your own household's numbers
whenever you're ready. Whatever was in `data/` before this reset was
backed up to `backups/data-reset-<timestamp>/` first, and is not
required for anything to keep working.

No bank integration, OCR, AI, or cloud sync is included anywhere in this
project — payments and expenses are entered by hand, and `receipts.py`
remains an unused extension point (see `docs/receipt_ocr.md`).
