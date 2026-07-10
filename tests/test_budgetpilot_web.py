#!/usr/bin/env python3
"""Tests for budgetpilot_web.three_month_forecast() — the small wrapper
that reuses budgetpilot.calc_month() (already covered in
test_budgetpilot_calc_month.py) across a rolling window of months.

Uses temp data files and patches budgetpilot's module-level paths, the
same isolation pattern as test_budgetpilot_calc_month.py — safe here too
since budgetpilot_web imports the same `budgetpilot` module object
(`import budgetpilot as bp`), so patching its attributes affects calls
made through either name.

Run directly: python3 tests/test_budgetpilot_web.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budgetpilot as bp
import payment_events as pe
import budgetpilot_web as web


class ThreeMonthForecastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)
        (data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0, "use_reserve": False, "safe_min": 0,
        }))
        (data / "incomes.json").write_text(json.dumps([
            {"name": "Výplata", "amount": 2000.0, "day": 15, "frequency": "monthly", "start": "2026-01-01"},
        ]))
        (data / "payments.json").write_text(json.dumps([
            {"name": "Nájom", "amount": 600.0, "day": 5, "frequency": "monthly", "start": "2026-01-01"},
        ]))
        (data / "expenses.json").write_text(json.dumps([]))
        (data / "debts.json").write_text(json.dumps([]))
        (data / "onetime.json").write_text(json.dumps([]))

        patches = [
            mock.patch.object(bp, "TODAY", date(2026, 7, 9)),
            mock.patch.object(bp, "SETTINGS", data / "settings.json"),
            mock.patch.object(bp, "INCOMES", data / "incomes.json"),
            mock.patch.object(bp, "PAYMENTS", data / "payments.json"),
            mock.patch.object(bp, "EXPENSES", data / "expenses.json"),
            mock.patch.object(bp, "DEBTS", data / "debts.json"),
            mock.patch.object(bp, "ONETIME", data / "onetime.json"),
            mock.patch.object(pe, "PAYMENT_EVENTS", data / "payment_events.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_returns_one_row_per_month_requested(self):
        months = web.three_month_forecast(date(2026, 7, 9), months=3)
        self.assertEqual(len(months), 3)

    def test_labels_are_in_calendar_order(self):
        months = web.three_month_forecast(date(2026, 7, 9), months=3)
        self.assertEqual([m["label"] for m in months], ["júl 2026", "august 2026", "september 2026"])

    def test_year_boundary_rolls_over(self):
        months = web.three_month_forecast(date(2026, 11, 9), months=3)
        self.assertEqual([m["label"] for m in months], ["november 2026", "december 2026", "január 2027"])

    def test_recurring_income_and_payment_repeat_every_month(self):
        months = web.three_month_forecast(date(2026, 7, 9), months=3)
        for m in months:
            self.assertEqual(m["income_total"], 2000.0)
            self.assertEqual(m["payment_total"], 600.0)
            self.assertEqual(m["planned_month_balance"], 1400.0)

    def test_month_count_is_configurable(self):
        months = web.three_month_forecast(date(2026, 7, 9), months=1)
        self.assertEqual(len(months), 1)


if __name__ == "__main__":
    unittest.main()
