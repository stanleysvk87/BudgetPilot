# OCR receipt rules

**OCR never auto-saves an expense. It only ever produces a starting
guess that the user must review and confirm.** This is the one hard
rule everything else here supports.

## Candidate extraction

A receipt's raw OCR text almost always contains more than one
money-shaped number — the payable total, sometimes a card-payment line,
and near-universally on Slovak/Czech receipts, VAT (`DPH`) and a tax
base (`základ dane`). Picking the "biggest number" or "last number"
blindly frequently grabs the VAT or base instead of what was actually
paid.

`receipts.extract_amount_candidates(raw_text)` returns **every**
amount-shaped number found, each tagged with a `kind`:

| kind    | matched on (case-insensitive)                          | shown to user as        |
|---------|----------------------------------------------------------|--------------------------|
| `total` | spolu, celkom, total, suma, k úhrade                      | "Celkom / spolu"        |
| `card`  | kartou, card, platbou kartou, uhradené kartou              | "Platba kartou"          |
| `vat`   | dph, vat                                                   | "DPH" — **not recommended** |
| `base`  | základ, základ dane, tax base                              | "Základ dane" — **not recommended** |
| `other` | no keyword matched                                         | "Iná suma na účtenke"    |

`not_recommended` is `True` for `vat`/`base` — the review card renders
those with a dashed border and "(neodporúčané)" instead of hiding them,
so the user can still pick one if the real total genuinely wasn't OCR'd,
but is never nudged toward it.

## Default guess

`receipts._pick_default_amount(candidates)` prefers, in order: a
`total` candidate, then `card`, then the largest remaining non-vat/base
candidate. It never defaults to a `vat`/`base` amount even if that's the
only thing OCR found — the amount field starts empty in that case and
the user must type it in.

## Review flow

1. `POST /receipt/upload` saves the image, runs `receipts.parse_receipt()`,
   and stashes the result (amount/date/merchant/candidates) as
   `data/receipts/<id>.review.json`. Redirects to `/` — nothing is
   written to `data/expenses.json` yet.
2. `render_page()` loads that file via `?review_receipt=<id>` and
   renders the `#receipt-review` card: the candidate list (radio-select
   fills the amount field), a category dropdown, editable
   amount/date/merchant.
3. `POST /receipt/confirm` is the only route that writes to
   `data/expenses.json`, using only the submitted values via
   `receipts.create_expense_from_receipt_result()`. Deletes the stashed
   `.review.json` afterward and logs `ocr_expense_saved` to the audit
   log (`audit_log.py`).

Saved OCR expenses get `source: "ocr"`, `needs_review: False`, and —
via `balance_first_summary._expense_matches_envelope()` — reduce
whichever envelope their confirmed category or recognized merchant
resolves to.

## Testing

`tests/test_receipts.py::ExtractAmountCandidatesTests` covers: total +
DPH + base together, multiple plain amounts, comma vs. dot decimal
format, ambiguous text with no amounts, and that the default guess never
picks a vat/base candidate even when it's the only one present.
