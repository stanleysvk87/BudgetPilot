#!/usr/bin/env python3
"""Tests for the pure envelope/category-budget calculations in envelopes.py.

Run directly: python3 tests/test_envelopes.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from envelopes import (
    expenses_in_month, spent_by_category, envelope_status,
    envelopes_summary, average_monthly_spend,
)


def expense(name, amount, d):
    return {"name": name, "amount": amount, "date": d}


class ExpensesInMonthTests(unittest.TestCase):
    def test_filters_to_given_year_month(self):
        expenses = [
            expense("Potraviny", 30, "2026-07-05"),
            expense("Potraviny", 20, "2026-06-30"),
            expense("Nafta", 40, "2026-07-20"),
        ]
        result = expenses_in_month(expenses, 2026, 7)
        self.assertEqual(len(result), 2)

    def test_empty_when_nothing_matches(self):
        expenses = [expense("Potraviny", 30, "2026-06-05")]
        self.assertEqual(expenses_in_month(expenses, 2026, 7), [])


class SpentByCategoryTests(unittest.TestCase):
    def test_sums_per_category(self):
        expenses = [
            expense("Potraviny", 30, "2026-07-05"),
            expense("Potraviny", 20, "2026-07-06"),
            expense("Nafta", 40, "2026-07-07"),
        ]
        totals = spent_by_category(expenses)
        self.assertEqual(totals, {"Potraviny": 50, "Nafta": 40})

    def test_missing_name_falls_back_to_ine(self):
        totals = spent_by_category([{"amount": 15, "date": "2026-07-01"}])
        self.assertEqual(totals, {"Iné": 15})


class EnvelopeStatusTests(unittest.TestCase):
    def test_under_budget(self):
        result = envelope_status("Potraviny", 200, 120)
        self.assertEqual(result["remaining"], 80)
        self.assertFalse(result["over_budget"])

    def test_over_budget(self):
        result = envelope_status("Potraviny", 200, 250)
        self.assertEqual(result["remaining"], -50)
        self.assertTrue(result["over_budget"])

    def test_exactly_at_limit_is_not_over_budget(self):
        result = envelope_status("Potraviny", 200, 200)
        self.assertEqual(result["remaining"], 0)
        self.assertFalse(result["over_budget"])


class EnvelopesSummaryTests(unittest.TestCase):
    def test_summary_matches_defined_envelopes_only(self):
        envelope_defs = [
            {"category": "Potraviny", "monthly_limit": 200},
            {"category": "Nafta", "monthly_limit": 100},
        ]
        expenses = [
            expense("Potraviny", 120, "2026-07-05"),
            expense("Nafta", 150, "2026-07-06"),
            expense("Deti", 999, "2026-07-07"),  # no envelope defined — excluded
        ]
        summary = envelopes_summary(envelope_defs, expenses)
        self.assertEqual(len(summary["rows"]), 2)
        self.assertEqual(summary["rows"][0]["remaining"], 80)
        self.assertEqual(summary["rows"][1]["remaining"], -50)
        self.assertTrue(summary["rows"][1]["over_budget"])
        self.assertEqual(summary["total_limit"], 300)
        self.assertEqual(summary["total_spent"], 270)
        self.assertEqual(summary["total_remaining"], 30)

    def test_category_with_no_spend_yet_shows_full_limit_remaining(self):
        envelope_defs = [{"category": "Oblečenie", "monthly_limit": 50}]
        summary = envelopes_summary(envelope_defs, [])
        self.assertEqual(summary["rows"][0]["spent"], 0)
        self.assertEqual(summary["rows"][0]["remaining"], 50)

    def test_empty_envelope_defs_gives_zero_totals(self):
        summary = envelopes_summary([], [expense("Potraviny", 50, "2026-07-01")])
        self.assertEqual(summary["rows"], [])
        self.assertEqual(summary["total_limit"], 0)
        self.assertEqual(summary["total_remaining"], 0)


class AverageMonthlySpendTests(unittest.TestCase):
    TODAY = date(2026, 7, 9)

    def test_averages_across_the_requested_months(self):
        expenses = [
            expense("Potraviny", 100, "2026-06-10"),
            expense("Potraviny", 200, "2026-05-10"),
            expense("Potraviny", 999, "2026-07-01"),  # current month excluded
        ]
        avg = average_monthly_spend(expenses, "Potraviny", months=2, today=self.TODAY)
        self.assertEqual(avg, 150)

    def test_month_with_no_expenses_counts_as_zero(self):
        expenses = [expense("Potraviny", 300, "2026-06-10")]
        avg = average_monthly_spend(expenses, "Potraviny", months=3, today=self.TODAY)
        # June=300, May=0, April=0 -> 300/3
        self.assertEqual(avg, 100)

    def test_zero_months_requested_returns_zero(self):
        self.assertEqual(average_monthly_spend([], "Potraviny", months=0, today=self.TODAY), 0.0)

    def test_year_boundary_is_handled(self):
        today = date(2026, 1, 15)
        expenses = [expense("Potraviny", 90, "2025-12-01")]
        avg = average_monthly_spend(expenses, "Potraviny", months=1, today=today)
        self.assertEqual(avg, 90)

    def test_only_matching_category_counts(self):
        expenses = [
            expense("Potraviny", 100, "2026-06-10"),
            expense("Nafta", 500, "2026-06-11"),
        ]
        avg = average_monthly_spend(expenses, "Potraviny", months=1, today=self.TODAY)
        self.assertEqual(avg, 100)


if __name__ == "__main__":
    unittest.main()
