#!/usr/bin/env python3
"""Receipt-OCR boundary: an optional, local/offline extraction pass over
a receipt photo, with a hard rule that its guess is never trusted
directly. See docs/receipt_ocr.md for the full picture.

OCR runs entirely on-device via Tesseract (through pytesseract) — no
cloud call, no external service, consistent with this project's "no
bank integration, no AI, no cloud sync" stance. If pytesseract or the
tesseract binary isn't installed, parse_receipt() falls back to the
inert placeholder rather than crashing, so a server without the system
package still works for manual expense entry.
"""
import re
from datetime import date

SOURCE_MANUAL = "manual"
SOURCE_OCR = "ocr"
SOURCE_IMPORT = "import"

VALID_SOURCES = {SOURCE_MANUAL, SOURCE_OCR, SOURCE_IMPORT}

_AMOUNT_RE = re.compile(r"(\d{1,4}[.,]\d{2})\b")
_TOTAL_KEYWORDS = ("spolu", "celkom", "total", "suma", "k úhrade", "k uhrade")
_CARD_KEYWORDS = ("kartou", "card", "platbou kartou", "uhradené kartou", "uhradene kartou")
_VAT_KEYWORDS = ("dph", "vat")
_BASE_KEYWORDS = ("základ", "zaklad dane", "zaklad", "tax base")
_DATE_DMY4_RE = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{4})\b")
_DATE_DMY2_RE = re.compile(r"\b(\d{2})[.\-/](\d{2})[.\-/](\d{2})\b")
_DATE_YMD_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Candidate kinds that a review UI should mark as "not recommended" — a
# receipt's VAT amount or tax base is almost never what the user actually
# paid, but OCR can't tell them apart from the real total by shape alone.
NOT_RECOMMENDED_KINDS = {"vat", "base"}
KIND_LABEL = {
    "total": "Celkom / spolu",
    "card": "Platba kartou",
    "vat": "DPH",
    "base": "Základ dane",
    "other": "Iná suma na účtenke",
}


def parse_receipt_placeholder(image_path):
    """Stand-in for an OCR call — always returns an empty, needs_review
    result. Used directly when OCR is unavailable, and by parse_receipt()
    itself as its fallback on any failure (missing dependency, unreadable
    image, tesseract error).
    """
    return {
        "amount": None,
        "date": None,
        "merchant": None,
        "raw_text": None,
        "confidence": 0.0,
        "image_path": image_path,
        "needs_review": True,
    }


def _classify_line(line_lower):
    """Which kind of money value a receipt line most likely holds. Checked
    in this order because a VAT/base line often also contains the word
    "spolu" (e.g. "DPH spolu") — the more specific label must win."""
    if any(k in line_lower for k in _VAT_KEYWORDS):
        return "vat"
    if any(k in line_lower for k in _BASE_KEYWORDS):
        return "base"
    if any(k in line_lower for k in _CARD_KEYWORDS):
        return "card"
    if any(k in line_lower for k in _TOTAL_KEYWORDS):
        return "total"
    return "other"


def extract_amount_candidates(raw_text):
    """Every amount-shaped number found in `raw_text`, tagged with the kind
    of line it appeared on (total/card/vat/base/other), so a review UI can
    show all of them and flag vat/base as not recommended instead of
    silently picking one. Order of first appearance, duplicates (same
    kind+amount) collapsed.
    """
    if not raw_text:
        return []
    seen = set()
    candidates = []
    for line in raw_text.splitlines():
        kind = _classify_line(line.lower())
        for m in _AMOUNT_RE.finditer(line):
            amount = float(m.group(1).replace(",", "."))
            key = (kind, amount)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "kind": kind,
                "label": KIND_LABEL[kind],
                "amount": amount,
                "not_recommended": kind in NOT_RECOMMENDED_KINDS,
            })
    return candidates


def _pick_default_amount(candidates):
    """Best starting guess for the review form: prefer the payable total
    (a 'total' or 'card' line), never a VAT/tax-base line even if it's the
    only one found, otherwise fall back to the largest amount seen. This
    is only ever a pre-filled suggestion — create_expense_from_receipt_result()
    still requires the user's confirmed value, never this guess directly.
    """
    for kind in ("total", "card"):
        matches = [c["amount"] for c in candidates if c["kind"] == kind]
        if matches:
            return max(matches)
    other = [c["amount"] for c in candidates if kind_allowed(c)]
    if other:
        return max(other)
    return None


def kind_allowed(candidate):
    return candidate["kind"] not in NOT_RECOMMENDED_KINDS


def _extract_amount(raw_text):
    """Best-guess total from OCR'd receipt text. Purely heuristic —
    receipts.py's caller must always treat this as a starting guess for
    the user to correct, never as a fact. Kept as a thin wrapper around
    extract_amount_candidates()/_pick_default_amount() for callers that
    only want the single best guess.
    """
    return _pick_default_amount(extract_amount_candidates(raw_text))


def _extract_date(raw_text):
    """Best-guess date from OCR'd receipt text: the first DD.MM.YYYY,
    DD.MM.YY (most Slovak/Austrian receipts print a 2-digit year), or
    YYYY-MM-DD pattern found (each also accepting '-'/'/' as separator).
    Same heuristic caveat as _extract_amount."""
    if not raw_text:
        return None
    m = _DATE_DMY4_RE.search(raw_text)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    m = _DATE_YMD_RE.search(raw_text)
    if m:
        y, mo, d = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    m = _DATE_DMY2_RE.search(raw_text)
    if m:
        d, mo, y = m.groups()
        try:
            return date(2000 + int(y), int(mo), int(d)).isoformat()
        except ValueError:
            pass
    return None


def _extract_merchant(raw_text):
    """First non-blank OCR line, on the (weak but usually true) assumption
    that a receipt's header/logo line is its merchant name."""
    if not raw_text:
        return None
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def parse_receipt(image_path):
    """Run local Tesseract OCR over a receipt image and extract a rough
    amount/date/merchant guess from the raw text.

    Falls back to parse_receipt_placeholder() — never raises — if
    pytesseract/Pillow aren't installed, the image can't be opened, or
    tesseract itself fails (including a missing Slovak language pack;
    retries with English-only before giving up). needs_review is always
    True: this function only ever produces a starting guess, matching the
    hard rule in create_expense_from_receipt_result() that the saved
    values always come from the user's confirmation, never straight from
    here.
    """
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        return parse_receipt_placeholder(image_path)

    try:
        image = Image.open(image_path)
        # Phone photos carry an EXIF orientation tag rather than physically
        # rotated pixels — most viewers auto-rotate for display, but PIL's
        # raw pixel data (and therefore Tesseract's OCR) does not unless
        # this is applied. Without it, a portrait photo OCRs as garbage.
        image = ImageOps.exif_transpose(image)
    except Exception:
        return parse_receipt_placeholder(image_path)

    raw_text = None
    for lang in ("slk+eng", "eng"):
        try:
            raw_text = pytesseract.image_to_string(image, lang=lang)
            break
        except Exception:
            continue
    if raw_text is None:
        return parse_receipt_placeholder(image_path)

    candidates = extract_amount_candidates(raw_text)
    return {
        "amount": _pick_default_amount(candidates),
        "amount_candidates": candidates,
        "date": _extract_date(raw_text),
        "merchant": _extract_merchant(raw_text),
        "raw_text": raw_text,
        "confidence": 0.0,
        "image_path": str(image_path),
        "needs_review": True,
    }


def create_expense_from_receipt_result(receipt_result, confirmed, receipt_id=None):
    """Turn a (future) OCR result into a normal expense dict.

    The saved amount/date/category/note always come from `confirmed` —
    the user-reviewed values — never straight from `receipt_result`. This
    is the only path an OCR result may take into data/expenses.json, and
    it always requires that confirmation step to have already happened.

    confirmed: {"name": str, "amount": float, "date": "YYYY-MM-DD"}
    """
    expense = {
        "name": confirmed["name"],
        "amount": float(confirmed["amount"]),
        "date": confirmed["date"],
        "source": SOURCE_OCR,
        "needs_review": False,
    }
    if receipt_id:
        expense["receipt_id"] = receipt_id
    if receipt_result.get("merchant"):
        expense["merchant"] = receipt_result["merchant"]
    if receipt_result.get("image_path"):
        expense["original_image_path"] = receipt_result["image_path"]
    if receipt_result.get("confidence") is not None:
        expense["ocr_confidence"] = receipt_result["confidence"]
    if receipt_result.get("raw_text"):
        expense["ocr_raw_text"] = receipt_result["raw_text"]
    return expense
