# Roadmap

## Current MVP (done)

- Pure forecast engine with a 5-state payment model
  (`pending`/`paid_me`/`paid_other`/`paid_reserve`/`deferred`)
- Recurring obligations, one-time obligations (pure helpers), and debts
  (pure helpers)
- First-run setup flow (`/setup`): real balance, payday day, add/cancel
  recurring obligations
- Payday balance snapshot as source of truth for a new cycle
- Payment-state UI: state selector + defer button per payment, reachable
  from the main dashboard
- Manual expense log with a `source` field ready for a future OCR input
  path
- 58 unit tests (stdlib `unittest`), covering forecast, obligations, and
  the receipts placeholder
- Mobile-friendly dashboard (viewport meta tag, horizontal table scroll),
  reachable over LAN

## Next up

- **Manual expenses UI polish** — categories/envelopes (see below) are the
  main gap; expense CRUD itself already works.
- **Categories / envelopes** — planned monthly budget per category (food,
  fuel, children, pharmacy, household, car, school, subscriptions,
  restaurant, other) vs. actual spend vs. remaining, plus historical
  monthly averages. Data model and UI both still to be designed.
- **Debts / borrowed money UI** — `obligations.py` already has the pure
  logic (`debt_to_payment()`, `I_owe` / `owed_to_me`); no dashboard surface
  yet.
- **One-time obligations UI** — pure helper (`generate_onetime_for_month()`)
  exists; no add/edit UI yet.
- **3-month forecast** — extending `forecast()` beyond the current
  now-to-next-payday window.

## Later / exploratory

- **Orange Pi / systemd deployment** — running `budgetpilot_web.py` as a
  persistent home-server service instead of a manually started process.
- **Optional Docker packaging** — for easier install on other machines;
  not needed for the current single-Python-file deployment model.
- **Optional OCR** — receipt photo → extracted amount/date/merchant → user
  confirms before saving as a normal manual expense. Manual entry stays the
  primary path always. See [receipt_ocr.md](receipt_ocr.md) — currently
  zero implementation, placeholder extension points only.
- **Possible public release** — this documentation pass is preparation for
  that, not the release itself. No bank integration, AI, authentication, or
  cloud sync is planned before or after a public release.

## Explicitly out of scope

No bank integration, no AI, no cloud sync, no authentication are planned as
part of the near-term roadmap. If any of these are ever considered, they'd
be a deliberate, separately-discussed decision — not a casual addition.
