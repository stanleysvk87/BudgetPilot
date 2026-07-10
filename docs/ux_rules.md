# UX rules

Design direction for the web dashboard — a calm, mobile-first finance
app. This codebase evolved as a series of live-applied patches directly
on this device (`BP_APP_SHELL_PATCH_V1`, `BP_UX_SAFETY_V2`,
`BP_BALANCE_FIRST_V1`, `BP_EDITABLE_ENVELOPES_V1`,
`BP_TOP_REVIEW_DEFER_V1`, `BP_TOP_REAL_OVERVIEW_V5`,
`BP_OCR_CANDIDATES_V1`) rather than one clean rewrite — search
`budgetpilot_web.py` for those markers to find each patch's boundaries.

## What each patch does

- **BP_APP_SHELL_PATCH_V1**: base layout/shell adjustments.
- **BP_UX_SAFETY_V2**: general UI safety/consistency patches.
- **BP_BALANCE_FIRST_V1**: wires the balance-first summary into the page.
- **BP_EDITABLE_ENVELOPES_V1**: inline envelope amount editing via
  `envelope_editor.py`'s `/api/envelopes/update`.
- **BP_TOP_REVIEW_DEFER_V1**: its row-patching (`patchTopRows()`) is now
  a no-op — `BP_UX_SAFETY_V2`'s `addUnpaidReview()` builds the
  `.safety-review-row` paid/defer actions directly and correctly
  (including for carried-over deferred items, which don't have a
  meaningful array index for `patchTopRows()`'s original clone-from-table
  approach to target), so leaving the old patcher active would have
  appended a second, stale defer action onto rows it no longer owns.
- **BP_TOP_REAL_OVERVIEW_V5**: the top "real balance" panel, fetching
  `GET /api/balance-first-summary` and rendering it client-side; hides
  the old `.topgrid`/`.summarygrid`/`.envelope-summary`/`.fin-overview`
  cards (`hideOldMetricCards()`) rather than deleting their markup —
  they still render server-side, just get a `bp-hide-old-metrics` class.
- **BP_OCR_CANDIDATES_V1**: `.candidate-list`/`.candidate` styling for
  the OCR amount-candidate picker in the receipt review card.
- **BP_DEFER_DATE_REQUIRED_V1**: the `.defer-widget` toggle/quick-date/
  cancel/required-date-on-submit behavior, event-delegated on
  `document` (not queried at page-load) specifically so cloned copies
  of the widget — `BP_UX_SAFETY_V2` clones the whole `.defer-widget`
  div into each `.safety-review-row` — work without any per-clone
  rewiring. See docs/balance_first_rules.md's "Deferred payments"
  section for the data-model side of this.

## Color rules

| color   | meaning                                                    |
|---------|--------------------------------------------------------------|
| green   | manually confirmed paid ("Z účtu"), or a clearly positive final state |
| red     | overdue, negative real estimate, over-budget envelope       |
| orange  | deferred, soon due                                           |
| blue    | neutral information                                          |

`cls(v)` in the `BP_TOP_REAL_OVERVIEW_V5` script: `< 0` → `bad` (red),
`< 100` → `warn`, else `good`.

## Removed/de-emphasized, not deleted

The old `.topgrid`/`.summarygrid` metric cards (safe-to-spend, payday
projection) are hidden via CSS class (`bp-hide-old-metrics`) by
`BP_TOP_REAL_OVERVIEW_V5`, not removed from the template — the
underlying Jinja/Python computation they were built from still runs.
Future income is never folded into the balance-first estimate (see
`docs/balance_first_rules.md`).

## Audit/history

New `#audit` section (details/summary "História zmien (N)") lists the
last 30 entries from `audit_log.py`, most-recent-first: balance updated,
payment paid/deferred, envelope amount changed, OCR expense saved,
manual expense added.

## Mobile

- Large tap targets (`.quick-actions button`, `.real-top-btn`).
- Sticky/responsive tables and a `real-update` grid that collapses to
  one column below 650px.
- OCR ("📷 OCR bloček") linked near the top of the real-overview panel,
  not buried in the sidebar.

## Payment review coloring (final polish pass)

`.safety-review-row` gets a class computed client-side from each item's
due date vs. today: `overdue` (red border) when `due < today`,
`due-soon` (orange border) when `0 <= days_until <= 3`, otherwise
unstyled. This is purely a CSS class on the row — it never changes
which payments count as unpaid in `build_balance_first_summary()`.

## Quick actions (final polish pass)

The real-overview panel's action row now links to four anchors:
`#expense-quick` (+ Výdavok), `/receipts` (📷 OCR bloček, purple),
`#payment-review` (✓ Skontrolovať platby — the id set on the
dynamically-created `.safety-review` section), `#envelopes` (✉ Upraviť
obálky, teal). The inline balance-update form inside the same panel
doubles as the "✎ Stav účtu" action, so no separate button is needed
for it.

## Manual expense entry

The "Detailný výdavok" sidebar form is the full manual-entry flow:
category (envelope) dropdown, amount, an optional "Poznámka / obchod"
free-text field (stored as `expense.merchant` when present — feeds the
same envelope alias matching OCR expenses use), and date defaulting to
today. The plain "Rýchly výdavok" form stays a single-amount shortcut
for the common case and does not expose category/merchant.

## Deferring a payment ("Odložiť")

No more one-click auto-+7-days. Clicking "↷ Odložiť" (or "Zmeniť dátum"
on an already-deferred item) expands an inline `.defer-form` in place —
never a page navigation or a separate modal — with a required
`type="date"` input, three quick-fill buttons (+7 dní / ďalší mesiac /
koniec mesiaca, computed client-side and just fill the date field, still
requiring the explicit "Potvrdiť odklad" submit), and a "Zrušiť" button
that collapses the form again without submitting. Submitting with an
empty date is blocked client-side (`reportValidity()`) as a first line
of defense; the server route (`/payment/defer/by-id`) independently
rejects a missing or unparseable date too, so this holds even with
JavaScript disabled or a hand-crafted request. See
docs/balance_first_rules.md for what happens to the event once
submitted.
