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
- **BP_TOP_REVIEW_DEFER_V1**: replaces the dropdown-only payment state
  workflow with tap-friendly "Z účtu / Iný / Rezerva / Nezaplatené" +
  "Odložiť" buttons — these clone/reuse the *same* underlying
  `<form action="/payment/state/<i>">` / `<form action="/payment/defer/<i>">`
  elements the server renders, so every code path (old dropdown or new
  buttons) posts to the same two backend routes.
- **BP_TOP_REAL_OVERVIEW_V5**: the top "real balance" panel, fetching
  `GET /api/balance-first-summary` and rendering it client-side; hides
  the old `.topgrid`/`.summarygrid`/`.envelope-summary`/`.fin-overview`
  cards (`hideOldMetricCards()`) rather than deleting their markup —
  they still render server-side, just get a `bp-hide-old-metrics` class.
- **BP_OCR_CANDIDATES_V1**: `.candidate-list`/`.candidate` styling for
  the OCR amount-candidate picker in the receipt review card.

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
