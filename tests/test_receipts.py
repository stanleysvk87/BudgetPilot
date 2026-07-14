#!/usr/bin/env python3
"""Tests for the receipt-OCR placeholder boundary in receipts.py.

Run directly: python3 tests/test_receipts.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import receipts as rc


class ParseReceiptPlaceholderTests(unittest.TestCase):
    def test_placeholder_does_not_extract_anything(self):
        result = rc.parse_receipt_placeholder("/tmp/does-not-exist.jpg")
        self.assertIsNone(result["amount"])
        self.assertIsNone(result["date"])
        self.assertEqual(result["confidence"], 0.0)

    def test_placeholder_always_flags_needs_review(self):
        result = rc.parse_receipt_placeholder("/tmp/whatever.jpg")
        self.assertTrue(result["needs_review"])


class ExtractAmountTests(unittest.TestCase):
    def test_prefers_a_total_labeled_line(self):
        raw_text = "Chlieb 1,20\nMlieko 0,95\nSPOLU 42,50"
        self.assertEqual(rc._extract_amount(raw_text), 42.50)

    def test_falls_back_to_largest_amount_when_no_total_line(self):
        raw_text = "Chlieb 1,20\nMlieko 0,95"
        self.assertEqual(rc._extract_amount(raw_text), 1.20)

    def test_dot_decimal_also_matches(self):
        raw_text = "TOTAL 12.34"
        self.assertEqual(rc._extract_amount(raw_text), 12.34)

    def test_no_amount_shaped_number_returns_none(self):
        self.assertIsNone(rc._extract_amount("ďakujeme za nákup"))

    def test_empty_text_returns_none(self):
        self.assertIsNone(rc._extract_amount(""))
        self.assertIsNone(rc._extract_amount(None))


class ExtractAmountCandidatesTests(unittest.TestCase):
    def test_total_plus_dph_plus_base(self):
        raw_text = "Základ dane 21%: 35,12\nDPH 21%: 7,38\nSPOLU: 42,50"
        candidates = rc.extract_amount_candidates(raw_text)
        kinds = {c["kind"]: c["amount"] for c in candidates}
        self.assertEqual(kinds["base"], 35.12)
        self.assertEqual(kinds["vat"], 7.38)
        self.assertEqual(kinds["total"], 42.50)

    def test_vat_and_base_are_marked_not_recommended(self):
        raw_text = "Základ dane: 35,12\nDPH: 7,38"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertTrue(all(c["not_recommended"] for c in candidates))

    def test_total_and_card_are_not_marked_not_recommended(self):
        raw_text = "SPOLU: 42,50\nPlatba kartou: 42,50"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertFalse(any(c["not_recommended"] for c in candidates))

    def test_multiple_plain_amounts_all_captured(self):
        raw_text = "Chlieb 1,20\nMlieko 0,95\nVajcia 2,10"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(c["kind"] == "other" for c in candidates))

    def test_comma_decimal_format_parsed(self):
        candidates = rc.extract_amount_candidates("SPOLU 12,34")
        self.assertEqual(candidates[0]["amount"], 12.34)

    def test_dot_decimal_format_parsed(self):
        candidates = rc.extract_amount_candidates("TOTAL 12.34")
        self.assertEqual(candidates[0]["amount"], 12.34)

    def test_ambiguous_text_with_no_amounts_returns_empty_list(self):
        self.assertEqual(rc.extract_amount_candidates("ďakujeme za nákup"), [])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(rc.extract_amount_candidates(""), [])
        self.assertEqual(rc.extract_amount_candidates(None), [])

    def test_default_guess_prefers_total_over_vat_and_base(self):
        raw_text = "Základ dane: 35,12\nDPH: 7,38\nSPOLU: 42,50"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertEqual(rc._pick_default_amount(candidates), 42.50)

    def test_default_guess_never_picks_vat_or_base_even_if_only_candidates(self):
        raw_text = "Základ dane: 35,12\nDPH: 7,38"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertIsNone(rc._pick_default_amount(candidates))

    def test_default_guess_falls_back_to_card_when_no_total_line(self):
        raw_text = "Platba kartou: 18,00\nChlieb 1,20"
        candidates = rc.extract_amount_candidates(raw_text)
        self.assertEqual(rc._pick_default_amount(candidates), 18.00)


class ExtractDateTests(unittest.TestCase):
    def test_dmy_dotted_format(self):
        self.assertEqual(rc._extract_date("Dátum: 09.07.2026"), "2026-07-09")

    def test_ymd_dashed_format(self):
        self.assertEqual(rc._extract_date("2026-07-09 12:30"), "2026-07-09")

    def test_dmy_dotted_two_digit_year(self):
        # Most real Slovak/Austrian receipts print a 2-digit year.
        self.assertEqual(rc._extract_date("02.04.26 13:26"), "2026-04-02")

    def test_four_digit_year_preferred_over_two_digit_when_both_present(self):
        self.assertEqual(rc._extract_date("09.07.2026 skladom 01.01.26"), "2026-07-09")

    def test_no_date_returns_none(self):
        self.assertIsNone(rc._extract_date("ďakujeme za nákup"))

    def test_invalid_calendar_date_is_rejected_not_crashed(self):
        self.assertIsNone(rc._extract_date("99.99.9999"))
        self.assertIsNone(rc._extract_date("99.99.99"))

    def test_empty_text_returns_none(self):
        self.assertIsNone(rc._extract_date(""))
        self.assertIsNone(rc._extract_date(None))


class ExtractMerchantTests(unittest.TestCase):
    def test_first_nonblank_line(self):
        self.assertEqual(rc._extract_merchant("\n\nTESCO STORES\nHlavná 1"), "TESCO STORES")

    def test_empty_text_returns_none(self):
        self.assertIsNone(rc._extract_merchant(""))
        self.assertIsNone(rc._extract_merchant(None))


class ParseReceiptFallbackTests(unittest.TestCase):
    """parse_receipt() must degrade to the inert placeholder — never raise
    — whenever OCR isn't actually usable (missing dependency, unreadable
    image, tesseract failure), so a server without tesseract installed
    doesn't break manual expense entry. A nonexistent image path exercises
    this regardless of whether pytesseract itself is installed, since
    Image.open() fails first either way — this environment currently has
    no pytesseract installed at all, which the next test pins."""

    def test_nonexistent_image_falls_back_to_placeholder(self):
        result = rc.parse_receipt("/tmp/does-not-exist.jpg")
        self.assertIsNone(result["amount"])
        self.assertTrue(result["needs_review"])

    def test_missing_pytesseract_dependency_falls_back_to_placeholder(self):
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("pytesseract is installed in this environment")
        result = rc.parse_receipt(__file__)  # a real, readable file
        self.assertIsNone(result["amount"])
        self.assertTrue(result["needs_review"])


class CreateExpenseFromReceiptResultTests(unittest.TestCase):
    def test_saved_expense_uses_confirmed_values_not_raw_ocr_guess(self):
        receipt_result = {"amount": 999.99, "merchant": "Ignored Store", "confidence": 0.1}
        confirmed = {"name": "Potraviny", "amount": 42.50, "date": "2026-07-09"}
        expense = rc.create_expense_from_receipt_result(receipt_result, confirmed)
        self.assertEqual(expense["amount"], 42.50)
        self.assertEqual(expense["name"], "Potraviny")
        self.assertEqual(expense["date"], "2026-07-09")

    def test_saved_expense_is_marked_ocr_source_and_reviewed(self):
        confirmed = {"name": "Nafta", "amount": 60, "date": "2026-07-09"}
        expense = rc.create_expense_from_receipt_result({}, confirmed)
        self.assertEqual(expense["source"], rc.SOURCE_OCR)
        self.assertFalse(expense["needs_review"])

    def test_optional_receipt_metadata_is_carried_when_present(self):
        receipt_result = {
            "merchant": "Tesco", "image_path": "/data/receipts/1.jpg",
            "confidence": 0.87, "raw_text": "TESCO 42.50 EUR",
        }
        confirmed = {"name": "Potraviny", "amount": 42.50, "date": "2026-07-09"}
        expense = rc.create_expense_from_receipt_result(receipt_result, confirmed, receipt_id="r1")
        self.assertEqual(expense["receipt_id"], "r1")
        self.assertEqual(expense["merchant"], "Tesco")
        self.assertEqual(expense["original_image_path"], "/data/receipts/1.jpg")
        self.assertEqual(expense["ocr_confidence"], 0.87)
        self.assertEqual(expense["ocr_raw_text"], "TESCO 42.50 EUR")

    def test_missing_optional_metadata_is_simply_omitted(self):
        confirmed = {"name": "Nafta", "amount": 60, "date": "2026-07-09"}
        expense = rc.create_expense_from_receipt_result({}, confirmed)
        self.assertNotIn("merchant", expense)
        self.assertNotIn("receipt_id", expense)
        self.assertNotIn("original_image_path", expense)


class IsValidReceiptIdTests(unittest.TestCase):
    """The one shared id-shape check every route that turns a receipt id
    into a filesystem path must use (see receipts.is_valid_receipt_id's
    docstring) -- previously /receipt/image/<id> validated this inline
    while two other call sites (the review_receipt query param and
    receipt_confirm()'s receipt_id form field) didn't validate at all."""

    def test_well_formed_id_is_valid(self):
        self.assertTrue(rc.is_valid_receipt_id("abc123abc123"))

    def test_wrong_length_is_rejected(self):
        self.assertFalse(rc.is_valid_receipt_id("abc123"))
        self.assertFalse(rc.is_valid_receipt_id("abc123abc123ff"))

    def test_uppercase_hex_is_rejected(self):
        self.assertFalse(rc.is_valid_receipt_id("ABC123ABC123"))

    def test_path_traversal_shaped_input_is_rejected(self):
        self.assertFalse(rc.is_valid_receipt_id("../../etc/passwd"))
        self.assertFalse(rc.is_valid_receipt_id("../sibling"))
        self.assertFalse(rc.is_valid_receipt_id("/etc/passwd"))

    def test_empty_or_none_is_rejected(self):
        self.assertFalse(rc.is_valid_receipt_id(""))
        self.assertFalse(rc.is_valid_receipt_id(None))


if __name__ == "__main__":
    unittest.main()
