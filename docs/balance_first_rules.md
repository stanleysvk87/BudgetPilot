# Balance-first rules

BudgetPilot's dashboard answers one question first: **how much money do
I actually have right now, once what I still owe is set aside?** It is
not a payday/salary forecasting tool and not accounting software.

## The formula

```
current account balance
- unpaid active payments
- remaining monthly envelopes
= real estimated balance
```

Implemented in `balance_first_summary.py`'s `build_balance_first_summary()`,
exposed at `GET /api/balance-first-summary` and rendered by the
`BP_TOP_REAL_OVERVIEW_V5` script block in `budgetpilot_web.py`. Unlike
the rest of the codebase's pure helpers (`forecast.py`, `envelopes.py`),
this function reads its inputs directly from `data/*.json` rather than
taking them as arguments — tests isolate it by pointing the module-level
`DATA` constant at a temp directory (see `tests/test_balance_first_summary.py`).

## Current balance is the source of truth

The manually entered `settings.account_balance` is authoritative. It is
updated in exactly one place with a single, narrow effect —
`POST /api/balance/update` (`balance_first_summary.api_balance_update()`):

- sets `settings.account_balance`, `settings.real_balance`,
  `settings.last_manual_review`
- appends an entry to `data/snapshots.json`
- does **not** touch payments or envelopes

## Income is optional, never counted as available money

`build_balance_first_summary()` never reads `data/incomes.json` at all —
income has no path into the real estimate. `first_run_wizard.py`'s
`_needs_first_run()` only requires a balance and at least one payment to
be entered, not an income.

## Date due is never "paid"

A payment's due date only affects display (`overdue` flag, urgency
coloring). The only way a payment stops counting as unpaid is an
explicit user action — the "✓ Zaplatené" button
(`POST /payment/state/<i>` with `state=paid_me`, or the equivalent
`paid_other`/`paid_reserve` options). `build_balance_first_summary()`
never reads `due_date` to decide whether something counts as paid.

## Deferred payments are excluded from unpaid

A payment with a `payment_events.json` entry whose `state` is
`"deferred"` for the current cycle is skipped entirely out of the unpaid
loop and instead added to `deferred_total`/`deferred_payment_items` —
never both.

## Envelopes: only unspent money is held back

`envelopes_remaining_total` is `max(budget - spent, 0)` per envelope,
summed — an over-budget envelope (spent > budget) contributes `0` to
what's held back, not a negative number that would add money back to
the estimate. Money already spent from an envelope already left the
account and is already reflected in `current_balance`; subtracting the
full envelope budget again would double-count it.

## Envelope category matching

`_expense_matches_envelope()` matches an expense to an envelope by
normalized (accent/case-insensitive) text match on the expense's
category/name/merchant/description/note against the envelope name, plus
a small alias table:

- `strava`: potraviny, jedlo, food, lidl, kaufland, tesco, billa
- `nafta`: palivo, fuel, benzina, slovnaft, omv, shell

So an expense named "Potraviny" (the dropdown still offers this label)
or an OCR'd "Lidl" merchant both reduce the "Strava" envelope
automatically.

## Shortfall

When `estimated_after_payments_and_envelopes < 0`,
`missing_after_everything` carries the absolute gap, shown as a red
warning on the dashboard.
