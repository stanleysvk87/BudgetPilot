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


if __name__ == "__main__":
    unittest.main()
