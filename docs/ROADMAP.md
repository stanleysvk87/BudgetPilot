# Roadmap

## Current MVP (done)

- Pure forecast engine with a 5-state payment model
  (`pending`/`paid_me`/`paid_other`/`paid_reserve`/`deferred`)
- Current-vs-projected cashflow split: `safe_to_spend_now` never includes
  future income, `projected_after_payday` is the separate, clearly labeled
  figure that does
- Categories / envelopes — monthly budget per category vs. actual spend vs.
  remaining, plus a 3-month historical average per category
  (`envelopes.py`)
- Recurring obligations, one-time obligations, and debts (`I_owe`/
  `owed_to_me`) — full dashboard UI (add/state/defer/delete), both wired
  into the current-cashflow forecast (`unpaid_required_before_payday`)
- First-run setup flow (`/auth/setup` then `/setup/full`): local
  administrator account, starting balance, reserve, and recurring
  obligations. Ongoing balance/payday maintenance remains available at
  `/setup`.
- Payday balance snapshot as source of truth for a new cycle
- Payment-state UI: state selector + defer button per payment, reachable
  from the main dashboard
- Receipt OCR — photo upload, local/offline Tesseract extraction (amount/
  date/merchant guess), mandatory user review/confirm before saving as a
  normal expense. See [receipt_ocr.md](receipt_ocr.md)
- 350 unit tests (stdlib `unittest`), covering forecast, obligations,
  receipt OCR/review boundaries, reset/wizard behavior, app views, and
  data fixtures
- Mobile-friendly dashboard (viewport meta tag, horizontal table scroll),
  reachable over LAN
- Linux deployment — Docker Compose is the preferred public path; a native
  systemd service example is documented in [../deploy/README.md](../deploy/README.md).
- 3-month forecast — rolling per-month income/payments/planned-balance
  table on the dashboard, reusing `budgetpilot.calc_month()` (same
  computation the CLI's `simulate()` already did, now also on the web).
  Note: like `simulate()`, this does not include debts for future months —
  only the current month's cashflow figures do.

## Next up

Nothing currently queued — the roadmap items tracked here are all done.
See "Later / exploratory" below for bigger, more open-ended ideas.

## Later / exploratory

- **Docker packaging hardening** — expand smoke tests and publish a tagged
  multi-architecture image only after CI covers that path.
- **Cross-process JSON locking** — add `flock`-based locking around the
  read-modify-write cycle in `json_store.py` so `BUDGETPILOT_WORKERS` can
  safely be raised above 1. See
  [ARCHITECTURE.md](ARCHITECTURE.md#concurrency-single-gunicorn-worker-by-design).
- **Possible public release** — this documentation pass is preparation for
  that, not the release itself. No bank integration, AI, public accounts, or
  cloud sync is planned before or after a public release.

## Explicitly out of scope

No bank integration, no AI, no cloud sync, and no public account system are
planned as part of the near-term roadmap. The web UI has a single local
administrator account; multi-user households, OAuth, invitations, and public
identity flows would be deliberate, separately-discussed features.
