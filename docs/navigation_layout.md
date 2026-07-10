# Navigation & layout: dashboard vs. detail views

BudgetPilot is a single Flask app (one Jinja template string in
`budgetpilot_web.py`) rendered by **real routes**, one per app section,
all going through the same `render_page(active_view=...)` function.
Content that belongs to a specific view is wrapped in
`{% if active_view == '...' %}` blocks — nothing is duplicated per
route, and nothing is hidden purely with client-side JS (a route that
returns 200 genuinely renders only that view's content server-side, so
it also works with JavaScript disabled or via curl).

## Routes

| route         | active_view  | shows |
|----------------|--------------|-------|
| `/`            | `dashboard`  | Hero overview + 4 summary cards only |
| `/payments`    | `payments`   | Po splatnosti / Splatné čoskoro / Čaká na potvrdenie / Zaplatené, full payment management table, jednorazové platby, dlhy |
| `/deferred`    | `deferred`   | Full deferred list with origin cycle, days remaining, zmeniť dátum |
| `/envelopes`   | `envelopes`  | Full envelope-grid progress cards + collapsed management table |
| `/expenses`    | `expenses`   | Expense entry forms + expenses table |
| `/receipts`    | `receipts`   | OCR upload + review flow (this route didn't exist before this slice — the quick-action link was 404ing) |
| `/history`     | `history`    | Full audit log + technical output |
| `/settings`    | `settings`   | Account/reserve, income form + table |

## Dashboard is summary-only

**Rule: dashboard = short overview, detail views = full lists and
management.** The dashboard never renders a full unpaid/deferred/
envelope table — only counts, totals, and up to 3 nearest/top items per
card, each with a button to the real detail route:

- **Platby** card: unpaid count, overdue count, due-soon count, total →
  "Otvoriť platby" (`/payments`).
- **Odložené platby** card (its own card — this was explicitly required,
  not folded into the payments card): total deferred, count, nearest
  due date, up to 3 nearest items → "Otvoriť odložené" (`/deferred`).
  Orange/brown accent (`.deferred-summary`), matching the deferred color
  used elsewhere.
- **Obálky** card: planned/spent/remaining totals, top 3 envelopes →
  "Spravovať obálky" (`/envelopes`). Teal accent.
- **Nedávna aktivita** card: last 5 audit entries → "Celá história"
  (`/history`).

These 4 cards are server-rendered directly from the same context
`render_page()` already builds (`unpaid`/`deferred`/`envelope_rows`/
`audit_entries`) — no extra fetch needed for them specifically. The
hero card and the full envelope-grid/payment-review builders that
already existed as client-side JS (fetching `/api/balance-first-summary`)
are now gated to their own view via `window.BP_ACTIVE_VIEW` (set once
per page load from `active_view`) so they don't render on pages that
don't want them — see the "JS gating" section below.

## Deferred payments must never disappear

This was true before this slice (see `docs/balance_first_rules.md`) and
stays true here — `/deferred` is purely a dedicated place to *see* the
full list with more detail (origin cycle/month, days remaining or
"Po termíne" for overdue, a "Vrátiť medzi aktuálne" quick-defer-to-today
button alongside "Zmeniť dátum"), not a change to when something counts
as unpaid vs. deferred. That logic is unchanged, in
`payment_events.resolve_deferred_carryovers()` /
`balance_first_summary._deferred_carryovers()`.

## `/api/balance-first-summary` additions

Purely additive — existing fields are untouched, so nothing that reads
this endpoint today breaks:

- `unpaid_count` / `deferred_count` (aliases of the existing
  `unpaid_payment_count` / `deferred_payment_count`)
- `due_soon_count` (unpaid, not overdue, due within 3 days)
- `next_deferred_item` (earliest `deferred_to`, or `null`)
- `top_deferred_items` (up to 3, nearest first)
- `recent_activity` (last 5 audit log entries, most recent first)

## JS gating (`window.BP_ACTIVE_VIEW`)

Set once near the top of `<body>`:
`window.BP_ACTIVE_VIEW = "{{active_view}}";`. Three existing client-side
builders check it and no-op on the wrong page:

- `BP_TOP_REAL_OVERVIEW_V5` (hero): dashboard only.
- `BP_EDITABLE_ENVELOPES_V1` (envelope-grid cards): `/envelopes` only.
- `BP_UX_SAFETY_V2`'s `addUnpaidReview()` (the old grouped
  "Kontrola nezaplatených platieb" card) is now naturally dormant: it
  looks for a heading text ("Nezaplatené / treba zaplatiť") that no
  longer exists anywhere in the template (the /payments view uses three
  separate headings instead), so its own `if(!unpaidSection) return;`
  guard already no-ops it everywhere — left in place rather than
  removed, since deleting a few-hundred-line function from a large
  string template is a needless risk when "already inert" achieves the
  same result.

## `go_home()` returns to the current view, not always the dashboard

Every POST action route (mark paid, defer, delete, add envelope, ...)
used to `redirect("/")` unconditionally — fine when there was only one
page, wrong now (deleting an envelope from `/envelopes` should not dump
you back on the dashboard). `go_home()` now redirects to
`request.referrer`'s path when it's a same-app local path, falling back
to `/` only when there's no usable referrer.

## Mobile

A `.bottomnav` fixed bar (5 primary destinations: Prehľad / Platby /
Odložené / Obálky / OCR) appears below 760px, alongside the existing
slide-out drawer (`BP_APP_SHELL_PATCH_V1`) for the full nav list
(History/Settings included). Both point at the same real routes, so
either one works identically; the bottom bar just puts the 5 most-used
destinations one tap away without opening the drawer first.
