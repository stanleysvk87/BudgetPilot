# BudgetPilot cashflow rules

BudgetPilot forecasts forward, not backward: it answers what still has to
happen to your main account balance between **now** and the **next
income date**, not just what happened this month.

## Payment states

`data/payments.json` holds recurring payment **templates** — name,
amount, due day, priority, flexibility. A template does not carry a
permanent paid/deferred state: which state applies is resolved per
month/cycle from `data/payment_events.json` (see
`docs/monthly_cycle.md`). This matters because a recurring payment
appears every month — if "paid" were baked onto the template itself,
marking Electricity `paid_me` in July would incorrectly leave it
`paid_me` in August too.

`forecast.payment_state(payment)` still normalizes a `state` field
(falling back to the legacy boolean `paid`) on whatever dict it's given —
that's what `payment_events.apply_payment_events()` uses internally after
resolving the effective per-cycle state, and it's also what makes legacy
data without a `payment_events.json` entry (or without the new model at
all) still parse without crashing.

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
button (`POST /payment/defer/<i>`). Both write to
`data/payment_events.json` for the **current cycle only** — they never
touch the template in `data/payments.json`:

| button / select value          | maps to                          |
|---------------------------------|-----------------------------------|
| Nezaplatené                     | `pending`                         |
| Zaplatené z účtu                | `paid_me`                         |
| Zaplatil niekto iný              | `paid_other`                      |
| Zaplatené z rezervy              | `paid_reserve`                    |
| Odložiť o 7 dní                 | `deferred`, `payment_events.defer_payment_event()` |

`payment_events.set_payment_event()` creates or replaces the event for
that `(payment_id, cycle_key)` pair only — every other cycle's event, and
every field on the template itself (id, priority, flexibility, active,
start_month, ...) is untouched. `payment_events.defer_payment_event()`
does the same, adding 7 days to the current cycle's `deferred_to` (or to
today, the first time this cycle).

`obligations.set_payment_state()` / `obligations.defer_payment()` still
exist and are still tested — they mutate a payment dict's state directly
and remain useful for one-time template-level edits/migration, but the
web UI no longer calls them for state changes, since that would be the
permanent-template bug this model fixes.

**Known limitation:** there is no per-cycle due-date override yet, so
"Odložiť" always adds a flat 7 days rather than letting you pick an
arbitrary new date, and a deferral cannot yet be scheduled into a future
cycle — it is always scoped to the current cycle. If the new date lands
after the next payday, `forecast()` correctly drops it out of the
*current* forecast window (see
`test_deferred_past_horizon_excluded_from_current_window`) — it simply
becomes a concern for the next cycle instead.

## Demo/default data

`data/payments.json` ships with a small, fake, internally-consistent
household set of recurring templates (mortgage, electricity, internet,
car insurance, kindergarten, a subscription, a loan installment) sized so
the forecast numbers can be checked by hand. `data/payment_events.json`
holds the current demo cycle's (`2026-07`) state for those templates —
electricity paid from the account, internet paid by someone else, car
insurance paid from the reserve, kindergarten deferred a few days. None
of that is baked onto the templates themselves, so simulating a later
month (`python3 budgetpilot.py`'s 18-month simulation, or the CLI/web
dashboard once the system date moves past July 2026) correctly shows
every payment back to `pending` until a new event exists for that cycle.
This is **not** real financial data — replace it with your own
household's numbers whenever you're ready. Whatever was in `data/`
before this reset was backed up to `backups/data-reset-<timestamp>/`
first, and whatever was there before the payment-events migration was
backed up to `backups/data-payment-events-<timestamp>/`; neither backup
is required for anything to keep working.

No bank integration, OCR, AI, or cloud sync is included anywhere in this
project — payments and expenses are entered by hand, and `receipts.py`
remains an unused extension point (see `docs/receipt_ocr.md`).
