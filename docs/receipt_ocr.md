# Receipt OCR

Optional, local/offline receipt scanning: photograph a receipt, get a
rough amount/date/merchant guess, review and correct it, then it's saved
as a normal expense. Manual entry remains the primary and fastest way to
log an expense — OCR is just an alternate input source for the same
`data/expenses.json` shape.

## How it works

1. Upload a photo via the "Účtenka (foto)" form in the web dashboard
   (`POST /receipt/upload`). On a phone, `capture="environment"` opens the
   camera directly. The image is saved to `data/receipts/<id>.<ext>`.
2. `receipts.parse_receipt()` runs local Tesseract OCR (via `pytesseract`)
   over the image and extracts a best-guess amount (the largest
   amount-shaped number, preferring a line with "spolu"/"celkom"/"total"),
   date (`DD.MM.YYYY` or `YYYY-MM-DD` pattern), and merchant (first
   non-blank OCR line). This is a rough heuristic, not a real model — it
   is never trusted directly.
3. The dashboard shows a "Potvrdiť účtenku" review form pre-filled with
   the guess. The user must review and correct the amount/date/category
   before saving — see `create_expense_from_receipt_result()`, which only
   ever writes the user-confirmed values (`confirmed`), never the raw OCR
   guess (`receipt_result`) straight through.
4. On confirm (`POST /receipt/confirm`), the result is saved as a normal
   expense with `source: "ocr"` — same shape, same forecast rules, same
   dashboard as a manually typed expense. OCR never saves anything
   automatically; confirmation is mandatory every time.

## Local, offline only

OCR runs entirely on-device via the system `tesseract` binary — no cloud
call, no external API, consistent with this project's "no bank
integration, no AI, no cloud sync" stance. If `pytesseract`/`Pillow`
aren't installed, or the `tesseract` binary is missing, `parse_receipt()`
falls back to `parse_receipt_placeholder()` (empty guess, still
`needs_review: True`) instead of crashing — manual expense entry keeps
working either way.

## Installing the OCR dependencies

```bash
sudo apt install tesseract-ocr tesseract-ocr-slk   # system binary + Slovak language pack
pip install -r requirements.txt                     # pytesseract, Pillow
```

Without this, the web UI's upload form still works, it just won't extract
anything — the review form opens with empty amount/date fields for you to
fill in by hand.

## Data model

Expenses may carry: `source` (`"manual"` / `"ocr"` / `"import"`,
default `"manual"`), `receipt_id`, `merchant`, `original_image_path`,
`ocr_confidence`, `ocr_raw_text`, `needs_review`. All optional — only
`source`/`receipt_id`/`merchant`/`original_image_path` are actually
written by the current upload flow (confidence/raw_text are supported by
`create_expense_from_receipt_result()` but not currently passed through
from the web form, to keep the review form and redirect URL short).
