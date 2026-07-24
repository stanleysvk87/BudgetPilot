# Changelog

Human-readable summary of the project's major changes. All dates 2026-07-09
(the revival happened in a single day's work session, building on an older,
previously non-git-tracked local project) except where noted.

## Add desktop app mode (2026-07-24)

New `desktop_app.py`: runs the existing Flask app unchanged in a
background thread and opens it in a native OS window via pywebview
instead of a browser tab. Packaging only, no route/template/data changes.
Kept as an optional extra (`requirements-desktop.txt`) so the server/
Docker deployment doesn't need a GUI toolkit. See
[docs/DESKTOP_APP.md](docs/DESKTOP_APP.md).

## `v0.1.0` — Initial public MVP (2026-07-16)

First public release candidate for BudgetPilot as a local-first household
forward-cashflow app.

- Flask web dashboard and CLI forecast over local JSON files.
- First-run local administrator setup, login/logout, CSRF protection,
  security headers, and optional Basic Auth compatibility.
- Balance-first setup wizard, payday balance snapshots, recurring payments,
  one-time obligations, debts, manual expenses, envelopes, and local receipt
  OCR review flow.
- Slovak and English web UI with persisted language preference.
- Docker Compose deployment, native Linux systemd example, `.env.example`,
  backup/update instructions, and public release documentation.
- Worker-safe persisted session-secret creation so multi-worker Gunicorn
  starts on a fresh runtime keep CSRF/session cookies valid.
- Standard-library unit test suite plus Playwright Chromium E2E, visual
  review, and sanitized screenshot capture.
- Apache License 2.0, copyright 2026 Stanislav Hambalko.

## `a76f595` — Add debts and one-time obligations UI, wired into the forecast (2026-07-10)

Debts: `obligations.set_debt_state()` (new) validates state transitions per
direction (I_owe: pending/paid_me/deferred; owed_to_me: pending/received —
mixing them is rejected). Web dashboard gets a "Dlhy" section; pending
I_owe debts feed into `calc_month()`'s forecast via the existing
`debt_to_payment()`, reducing `safe_to_spend_now` exactly like any other
obligation. owed_to_me debts never enter the forecast, per that function's
existing rule. One-time obligations: `generate_onetime_for_month()`
(existing pure helper) now merges into `payment_items`, so a one-time item
gets the full 5-state `payment_events` lifecycle exactly like a recurring
payment. Web dashboard gets a "Jednorazové platby" section, scoped to the
current month. 135 tests total.

## `22de605` — Add spending envelopes (categories vs. monthly budget) (2026-07-10)

New `envelopes.py`: pure per-category monthly-limit tracking (spent,
remaining, over_budget) plus a 3-month historical average. Wired into the
web dashboard as an "Obálky" section. Categories reuse the existing
`EXPENSE_TYPES` list, so `expense.name` is the category with no new field
needed. 115 tests total.

## `44f96bd` — Fix safe-to-spend mixing future income into current cash position (2026-07-10)

The dashboard's "Bezpečne minúť" figure was computed from `real_available`,
which added future income (e.g. an upcoming payday) before subtracting
required payments and reserve — a real shortfall before payday could
render as a safe-looking positive number. Added
`forecast.current_cash_position()`: `safe_to_spend_now` from the current
balance only (never inflated by future income, floored at 0), separate
from `projected_after_payday` (may include future income, labeled as a
projection). 98 tests total.

## `6a90742` — Fix recurring payment state to be cycle-scoped, reorganize mobile dashboard

Added `payment_events.py`: state (`paid_me`/`paid_other`/`paid_reserve`/
`deferred`) is no longer baked onto recurring templates in
`data/payments.json` (which made a payment marked paid in July stay paid
forever) — instead it lives in `data/payment_events.json`, one event per
`(payment_id, cycle_key)`. No event for a cycle means pending, regardless
of what the template's legacy state field says. Reorganized the dashboard
so the cashflow summary renders above the income/settings tables, added a
sticky nav bar, and moved main content ahead of the sidebar on mobile.
87 tests total.

## Public-release cleanup (included in `v0.1.0`)

- Added README.md, docs/ (QUICKSTART, INSTALL, USAGE, DATA_MODEL,
  CASHFLOW_LOGIC, ARCHITECTURE, ROADMAP, PRIVACY, SECURITY, CONTRIBUTING),
  LICENSE, and this changelog.
- Expanded `.gitignore` for virtualenvs, local env files, and `backups/`.
- Added Docker/native deployment files and release-readiness documentation.

## Slovak/English localization and Chromium release review (included in `v0.1.0`)

- Added dependency-free Slovak/English localization with JSON catalogs,
  fallback behavior, visible language switcher, and persisted language cookie.
- Localized authentication/setup pages, navigation, statuses, validation
  messages, warnings, empty states, dashboard/payment/expense/manage labels,
  and browser-side confirmation copy.
- Added localization tests and Playwright Chromium end-to-end tests for
  first-run setup, login/logout, protected redirects, financial actions,
  language switching, mobile navigation, validation, and destructive-action
  confirmation.
- Added automated Chromium visual review across desktop, laptop, tablet,
  mobile portrait, mobile landscape, and narrow mobile widths.
- Added sanitized public screenshots generated from synthetic data under
  `docs/assets/screenshots/`.
- Fixed auth-page CSS injection, tablet `/manage` action overflow, small
  clickable targets, and English forecast status labels.

## `f71ee3e` — Expose payment states in web UI and reset to clean demo data

Added a state selector and a 7-day defer button to each payment row in the
web dashboard, wired to the same `obligations.set_payment_state()` /
`defer_payment()` helpers used by the tests. Reset `data/*.json` to a small,
clearly fake demo dataset that exercises all five payment states by hand
(the previous contents were backed up first, see
`backups/data-reset-20260709-225605/`).

## `5e0e0e6` — Add receipt-OCR extension points (no OCR implemented)

Added inert, placeholder-only extension points for a possible future
receipt-scanning feature: `receipts.py`
(`parse_receipt_placeholder()`, `create_expense_from_receipt_result()` —
no OCR engine, no image reading, no external calls), a `source` field on
expenses (`manual`/`ocr`/`import`, default `manual`), and non-destructive
`expense/update` (merges instead of overwriting, so metadata survives a
manual edit). Documented in `docs/receipt_ocr.md`.

## `1f966b2` — Stabilize settings/payment persistence and mobile rendering

Fixed `/settings` and `payment/update` to merge submitted fields into the
existing record instead of overwriting it wholesale — both were silently
dropping fields (`payday_day`, `real_balance`, `reserve_amount`, `id`,
`priority`, `flexibility`, `active`, `start_month`) that weren't present in
the submitted form. Added `ensure_recurring_compatible()` so payments added
from the main dashboard get the same default fields as ones added via
`/setup`. Added a viewport meta tag and horizontal table scroll for mobile.

## `c3b1e39` — Add recurring obligations, payday snapshot, and first-run setup page

Added `obligations.py`: pure helpers for recurring-obligation
active/cancelled resolution, one-time obligations, `I_owe`/`owed_to_me`
debts, account-balance/payday-snapshot resolution, and a `needs_setup()`
check. Added a non-blocking `/setup` page in the Flask app for entering the
real balance, payday day, and recurring obligations — written into the same
`data/payments.json` the CLI already reads, so nothing else needed to
change. Extended `budgetpilot.py`'s `occurs()` to respect the new
`active`/`cancelled_from_month` fields. Fixed the web server to bind
`0.0.0.0` instead of `127.0.0.1` so it's actually reachable from other
devices on the LAN.

## `1dc71bf` — Add pure forecast module with payment-state cashflow rules

Added `forecast.py`: a pure, fully-tested function implementing a 5-state
payment model (`pending`, `paid_me`, `paid_other`, `paid_reserve`,
`deferred`) and wired it into `budgetpilot.py`'s `calc_month()`. This fixed
the core bug motivating this revival — the pre-existing `paid` boolean on
payments was never actually read by the forecast calculation, so marking a
bill paid had zero effect on the numbers. Added the first 16 unit tests and
`docs/cashflow_rules.md`.

## `b0e7f38` — Initial local checkpoint before BudgetPilot revival

First git commit of the pre-existing local project: `budgetpilot.py` (CLI),
`budgetpilot_web.py` (Flask UI), three earlier Tkinter GUI prototypes
(`budgetpilot_gui.py`, `_v2`, `_v3`), one-off patch scripts (`fix_*.py`,
`add_gui_lists.py`, `rollback_latest.sh`), and the data files and backups
that existed at the time. No tests existed yet.
