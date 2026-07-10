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

## Deferred payments: "Odložiť" means postpone to a concrete date

"↷ Odložiť" always requires a target date — there is no one-click
"push it 7 days and forget" action anymore (the old auto-+7-days
`payment_events.defer_payment_event()` still exists as a pure building
block/tested, but nothing in the web UI calls it). Deferring writes an
event to `data/payment_events.json` shaped as:

```json
{
  "payment_id": "...", "cycle_key": "2026-07", "state": "deferred",
  "deferred_to": "2026-08-15", "created_at": "...", "updated_at": "...",
  "note": "optional"
}
```

`cycle_key` is the cycle the event slot lives under — the current cycle
for a fresh defer, or the item's own `origin_cycle_key` when
re-deferring/changing the date of an already-deferred item (re-defer
updates that same slot in place rather than creating a second, orphaned
event for the same payment — see `payment_events.defer_payment_to_date()`).

**A deferred payment is never deleted and never marked paid by
deferring it.** The only way it stops being deferred is an explicit
"✓ Zaplatené" action (still requires manual confirmation — date never
means paid, including `deferred_to`) or a later re-defer.

**A deferred payment becomes active again automatically once its
target date arrives** — `payment_events.resolve_deferred_carryovers()`
(and its balance_first_summary equivalent, `_deferred_carryovers()`)
scans deferred-state events from *any* cycle, not just the one being
viewed, and promotes any whose `deferred_to` month is the current
cycle's month or earlier into that cycle's unpaid list — labeled
"Odložené z minulého obdobia" (deferred within the same cycle) or
"Odložené z {origin cycle}" (carried over from an earlier one) — instead
of leaving it parked under "deferred" forever. A `deferred_to` date in
the past is accepted, not rejected — it just means the item shows up
immediately as overdue-unpaid rather than staying hidden.

**A carryover never merges with or replaces the target month's own
natural occurrence of the same recurring payment.** If a monthly
payment is deferred from July into August, and that same payment also
recurs naturally in August (its own fresh pending obligation, due
August's own due day), both appear as separate unpaid items once August
arrives — the carryover is always in *addition to*, never instead of,
that month's own obligation. This is why carryover resolution is kept
completely separate from the normal per-cycle event lookup: the two
are independent by construction, not merged and then deduplicated.

See `tests/test_payment_events.py::ResolveDeferredCarryoversTests` and
`tests/test_balance_first_summary.py` (the `test_deferred_*`/
`test_paid_deferred_*`/`test_overdue_deferred_*` cases) for the exact
promoted-vs-still-deferred boundary cases this implements.
