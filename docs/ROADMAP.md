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
- First-run setup flow (`/setup`): real balance, payday day, add/cancel
  recurring obligations
- Payday balance snapshot as source of truth for a new cycle
- Payment-state UI: state selector + defer button per payment, reachable
  from the main dashboard
- Receipt OCR — photo upload, local/offline Tesseract extraction (amount/
  date/merchant guess), mandatory user review/confirm before saving as a
  normal expense. See [receipt_ocr.md](receipt_ocr.md)
- 58 unit tests (stdlib `unittest`), covering forecast, obligations, and
  the receipts placeholder
- Mobile-friendly dashboard (viewport meta tag, horizontal table scroll),
  reachable over LAN
- Orange Pi / systemd deployment — user-level service (no root needed),
  see [../deploy/README.md](../deploy/README.md)

## Next up

- **3-month forecast** — extending `forecast()` beyond the current
  now-to-next-payday window.

## Later / exploratory

- **Optional Docker packaging** — for easier install on other machines;
  not needed for the current single-Python-file deployment model.
- **Possible public release** — this documentation pass is preparation for
  that, not the release itself. No bank integration, AI, authentication, or
  cloud sync is planned before or after a public release.

## Explicitly out of scope

No bank integration, no AI, no cloud sync, no authentication are planned as
part of the near-term roadmap. If any of these are ever considered, they'd
be a deliberate, separately-discussed decision — not a casual addition.
