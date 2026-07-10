# Visual design: mockup-driven redesign

This slice restyled the existing views to match a supplied dark-mode
mobile banking-app mockup (8 screens: Prehľad/Platby/Odložené
platby/Obálky/OCR bloček/História). No routes, business logic, or data
model changed — this is CSS/markup plus two small additive backend
pieces (a receipt-image route and a couple of display-only groupings).
See `docs/navigation_layout.md` for the route table and
`docs/balance_first_rules.md` for the underlying rules that were
deliberately left untouched.

## Color coding

Reused consistently across dashboard cards, view tabs, task-card accent
borders, and the bottom nav's active state:

- **blue** — primary/neutral (dashboard hero, Platby, Čaká)
- **purple** (`#7c3aed`) — OCR/receipts (candidate tags, receipt
  thumbnail border, bottom-nav OCR active state)
- **teal** (`#0d9488`/`#2dd4bf`) — envelopes (progress bars, remaining
  amounts, icon-circle background, bottom-nav Obálky active state)
- **orange/brown** (`#b45309`) — deferred (task-card left border,
  defer-toggle outline, bottom-nav Odložené active state)
- **red** — overdue/risk (`.badge.bad`, `.tab-red`, overdue task-cards)
- **green** — confirmed-paid only, never used for "due" or "deferred"
  (paid task-cards, `.paid-quick-form button`)

## Payments/Deferred views: tab pills + task-cards

Both `/payments` and `/deferred` replaced their `<table>` rows with a
`.view-tabs` row of filter pills (each with a `.tab-badge` count) linking
to `id`-anchored sections below, and each section renders a
`.task-card-list` of `.task-card` divs (Jinja macros `unpaid_rows()` /
`deferred_rows()` in the template) instead of table rows. This is a
pure display change — the underlying `unpaid_overdue`/`unpaid_soon`/
`unpaid_pending` split already existed; `/deferred` got the equivalent
`deferred_overdue`/`deferred_soon`/`deferred_later` split (by
`days_left`, computed the same way as before) purely for the new tabs.
In practice `deferred_overdue` is rarely non-empty: once a `deferred_to`
date's month reaches the current cycle, `resolve_deferred_carryovers()`
already promotes that item out of "deferred" and into `/payments`'s
unpaid list (see `docs/balance_first_rules.md`) — the tab still exists
for the edge case, and `tests/test_app_views.py::DeferredViewTabSplitTests`
pins down that a passed `deferred_to` shows up on `/payments`, not stuck
on `/deferred`.

## Envelope cards: icon circles

`BP_EDITABLE_ENVELOPES_V1`'s JS card builder (`/envelopes` only) now
prefixes each card's name with a small emoji in a circular badge
(`.envelope-card-icon`), picked by a keyword match on the envelope name
(`envelopeIcon()` — strava/nafta/bývanie/zábava/oblečenie/zdravie, falling
back to a generic 💶). Purely cosmetic; the underlying envelope data and
alias-matching in `envelopes.py` is unrelated and untouched.

## OCR review: receipt thumbnail

The receipt review card (`/receipts`) previously had no way to show the
uploaded photo — there was no route serving it. Added
`GET /receipt/image/<receipt_id>` (`budgetpilot_web.py`), which validates
`receipt_id` against the exact `uuid4().hex[:12]` shape the upload route
generates before touching disk (rejects anything else with a 404 — no
path ever reaches the filesystem unsanitized) and serves whichever
known image extension exists via `send_file`. The review form's fields
were relabeled to match the mockup: Nájdené sumy (candidates, unchanged)
→ **Vybraná suma** (was "Suma") → **Obálka** (was "Kategória") →
**Poznámka**. The confirm flow, candidate list, and "not recommended"
VAT/base flags are all unchanged.

## History: date-grouped timeline

`/history`'s audit table became a `.timeline` of day-grouped entries.
Since Jinja's `groupby` filter can't group on a slice expression, the
day (and a `HH:MM` time) are now split off `entry["at"]` once in Python
(`_with_day_and_time()`) before the entries reach the template, then
grouped with `{% for day, day_entries in audit_entries|groupby('day')|reverse %}`
(`groupby` sorts ascending and is stable, so `|reverse` puts the newest
day first while preserving each day's own newest-first order).

## Bottom nav active-state colors

`.bottomnav a.active` now picks up the same per-section accent as the
tabs above, via `href`-attribute selectors (`a[href="/deferred"].active`
etc.) rather than always using the default blue — no markup change
needed since the `href`s already existed.
