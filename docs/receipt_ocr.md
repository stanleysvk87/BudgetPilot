# Receipt OCR (future, optional)

This documents an extension point that exists in the code but is **not
implemented**. No OCR engine is installed, called, or planned to run in
this slice.

## Status

- `receipts.py` contains only placeholder functions
  (`parse_receipt_placeholder()`, `create_expense_from_receipt_result()`).
  Neither reads an image file nor calls any OCR library or external
  service.
- Expenses in `data/expenses.json` may carry a `source` field
  (`"manual"` / `"ocr"` / `"import"`), defaulting to `"manual"`. Optional
  receipt metadata (`receipt_id`, `merchant`, `original_image_path`,
  `ocr_confidence`, `ocr_raw_text`, `needs_review`) is supported by the
  data model but not required and not currently written by anything.
- There is no OCR UI. Photo upload is not implemented.

## Intended future direction

Manual entry is, and will remain, the primary and fastest way to log an
expense. OCR is meant to be an **optional input source for manual
expenses**, not a separate accounting system:

1. User uploads or photographs a receipt.
2. OCR (not yet implemented) attempts to extract total amount, date, and
   possibly the merchant, via `parse_receipt_placeholder()` or its real
   successor.
3. The user must review and confirm or correct the amount, date, and
   category, and may edit the note/merchant, before anything is saved —
   see `create_expense_from_receipt_result()`, which only ever writes the
   user-confirmed values, never the raw OCR guess.
4. Once confirmed, the result is saved as a normal expense
   (`source: "ocr"`) — same shape, same forecast rules, same dashboard as
   a manually typed expense.

OCR must never save an expense automatically. Confirmation is mandatory,
every time.

When BudgetPilot is deployed on the Orange Pi server, local/NPU-accelerated
OCR processing may be considered — this is out of scope for now and has
no code or dependencies in this repo yet.
