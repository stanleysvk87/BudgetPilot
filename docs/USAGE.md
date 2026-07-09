# Usage

## First-run setup

BudgetPilot needs a **payday day of month** and a **real account balance**
before it can forecast reliably. Until both are set, the dashboard (`/`)
shows a banner linking to `/setup`. The dashboard itself still works while
setup is incomplete — it's not a blocking wizard.

At `/setup` you can:

- enter your real current balance and an optional reserve amount
- set the payday day of month
- add recurring monthly obligations (name, amount, due day, priority,
  flexibility)
- cancel or reactivate a recurring obligation

## Payday balance snapshot

On payday, go back to `/setup` and enter the real current balance. This
overwrites the balance BudgetPilot forecasts from, and records a snapshot
(date, balance, reserve) in `data/snapshots.json` — a history of what the
account actually held on each payday. The most recent snapshot always wins
over whatever was assumed before: your real balance on payday is the
source of truth for the new cycle, so nothing from the previous month gets
double-counted.

## Recurring obligations

Rent, a mortgage, a loan installment, insurance, subscriptions — anything
that repeats monthly — only needs to be entered once via `/setup` (or the
main dashboard's add-payment form). It then appears automatically every
month until you cancel it. Cancelling doesn't delete its history, it just
stops it from applying to future months.

## Payment states

Every payment on the dashboard can be marked with one of five states, via
its dropdown or the "Odložiť o 7 dní" (defer) button:

| state          | meaning                                |
|----------------|-----------------------------------------|
| `pending`      | not paid yet — reduces your forecast    |
| `paid_me`      | you already paid it from the main account |
| `paid_other`   | someone else paid it (e.g. a partner)   |
| `paid_reserve` | paid out of your reserve, not main cash |
| `deferred`     | pushed later by 7 days at a time        |

Full rule table and rationale: [cashflow_rules.md](cashflow_rules.md).

## Deferred payments

Marking a payment `deferred` pushes its effective due date 7 days forward
each time you click it. If the new date still falls before your next
payday, it still counts against your forecast; if it moves past payday, it
naturally becomes next cycle's concern instead of this one's.

## Dashboard meaning

The dashboard shows, for the current month: total income, total payments
due, total manual expenses, and — for the current month specifically — a
forward-looking `real_available` figure that accounts for what's still to
come before payday, not just what's already happened this month. From that
it derives a safe-to-spend amount and a per-day allowance until payday, plus
a plain-language verdict (OK / caution / problem).

## Manual data entry

Incomes, payments, and expenses can all be added, edited, or deleted
directly from the web dashboard forms — no need to hand-edit the JSON
files, though you can (see [DATA_MODEL.md](DATA_MODEL.md)) if you prefer.
