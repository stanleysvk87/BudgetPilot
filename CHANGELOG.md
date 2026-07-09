# Changelog

Human-readable summary of the project's major changes. All dates 2026-07-09
(the revival happened in a single day's work session, building on an older,
previously non-git-tracked local project).

## Unreleased — documentation and public-release cleanup

- Added README.md, docs/ (QUICKSTART, INSTALL, USAGE, DATA_MODEL,
  CASHFLOW_LOGIC, ARCHITECTURE, ROADMAP, PRIVACY, SECURITY, CONTRIBUTING),
  LICENSE, and this changelog.
- Expanded `.gitignore` for virtualenvs, local env files, and `backups/`.
- No application logic, data model, or feature changes in this pass.

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
