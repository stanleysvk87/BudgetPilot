#!/usr/bin/env python3
"""Placeholder boundary for a future, optional receipt-OCR feature.

No OCR engine is implemented or called anywhere in this module — it only
defines the shape a future OCR pass would produce, and the one path by
which that result is allowed to become a real expense: through explicit
user confirmation. See docs/receipt_ocr.md for the full picture.
"""

SOURCE_MANUAL = "manual"
SOURCE_OCR = "ocr"
SOURCE_IMPORT = "import"

VALID_SOURCES = {SOURCE_MANUAL, SOURCE_OCR, SOURCE_IMPORT}


def parse_receipt_placeholder(image_path):
    """Stand-in for a future OCR call.

    Does not open image_path or run any OCR engine. Always returns a
    result flagged needs_review=True, since nothing has actually been
    extracted or verified yet.
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
