#!/usr/bin/env python3
"""Tests for balance_first_summary.py — the "current balance - unpaid -
remaining envelopes = real estimate" formula.

build_balance_first_summary() reads its input files from the module-level
DATA constant rather than taking them as arguments, so these tests point
DATA at an isolated temp directory per test instead of touching the real
data/ dir (which holds real household data on a live deployment).

Run directly: python3 tests/test_balance_first_summary.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import balance_first_summary as bfs

TODAY = date.today()


def _write(path, name, value):
    (path / name).write_text(json.dumps(value), encoding="utf-8")


class BalanceFirstSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data = Path(self.tmpdir.name)
        self._orig_data = bfs.DATA
        bfs.DATA = self.data
        _write(self.data, "settings.json", {"account_balance": 1000})
        _write(self.data, "payments.json", [])
        _write(self.data, "payment_events.json", [])
        _write(self.data, "envelopes.json", [])
        _write(self.data, "expenses.json", [])

    def tearDown(self):
        bfs.DATA = self._orig_data
        self.tmpdir.cleanup()

    def _payment(self, pid, amount, due_day):
        return {"id": pid, "name": "Test", "amount": amount, "due_day": due_day, "active": True}

    def test_pending_payment_reduces_estimate(self):
        _write(self.data, "payments.json", [self._payment("p1", 200, TODAY.day)])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["unpaid_payments_total"], 200)
        self.assertEqual(result["estimated_after_payments"], 800)

    def test_deferred_payment_excluded_from_unpaid_total(self):
        _write(self.data, "payments.json", [self._payment("p1", 200, TODAY.day)])
        _write(self.data, "payment_events.json", [
            {"payment_id": "p1", "cycle_key": f"{TODAY.year:04d}-{TODAY.month:02d}", "state": "deferred"}
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["unpaid_payments_total"], 0)
        self.assertEqual(result["deferred_payments_total"], 200)
        self.assertEqual(result["estimated_after_payments"], 1000)

    def test_paid_payment_excluded_from_unpaid_total(self):
        _write(self.data, "payments.json", [self._payment("p1", 200, TODAY.day)])
        _write(self.data, "payment_events.json", [
            {"payment_id": "p1", "cycle_key": f"{TODAY.year:04d}-{TODAY.month:02d}", "state": "paid_me"}
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["unpaid_payments_total"], 0)

    def test_overdue_count(self):
        past_day = max((TODAY - timedelta(days=2)).day, 1) if TODAY.day > 2 else 1
        future_day = min(TODAY.day + 5, 28)
        payments = [self._payment("p1", 50, past_day)]
        if future_day != past_day:
            payments.append(self._payment("p2", 50, future_day))
        _write(self.data, "payments.json", payments)
        result = bfs.build_balance_first_summary()
        self.assertGreaterEqual(result["overdue_count"], 1)

    def test_envelope_remaining_reduces_estimate_not_full_budget(self):
        _write(self.data, "envelopes.json", [
            {"id": "e1", "name": "Strava", "monthly_budget": 600, "active": True}
        ])
        _write(self.data, "expenses.json", [
            {"name": "Potraviny", "amount": 120, "date": TODAY.isoformat()}
        ])
        result = bfs.build_balance_first_summary()
        # 600 budget - 120 already spent = 480 still reserved, not the full 600
        self.assertEqual(result["envelopes_remaining_total"], 480)
        self.assertEqual(result["estimated_after_payments_and_envelopes"], 1000 - 480)

    def test_over_budget_envelope_does_not_add_money_back(self):
        _write(self.data, "envelopes.json", [
            {"id": "e1", "name": "Strava", "monthly_budget": 100, "active": True}
        ])
        _write(self.data, "expenses.json", [
            {"name": "Potraviny", "amount": 250, "date": TODAY.isoformat()}
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["envelopes_remaining_total"], 0)
        self.assertEqual(result["estimated_after_payments_and_envelopes"], 1000)

    def test_expense_alias_potraviny_reduces_strava_envelope(self):
        _write(self.data, "envelopes.json", [
            {"id": "e1", "name": "Strava", "monthly_budget": 600, "active": True}
        ])
        _write(self.data, "expenses.json", [
            {"name": "Potraviny", "amount": 60, "date": TODAY.isoformat()},
            {"merchant": "Lidl", "amount": 30, "date": TODAY.isoformat()},
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["envelopes_spent_total"], 90)

    def test_expense_alias_nafta_reduces_nafta_envelope(self):
        _write(self.data, "envelopes.json", [
            {"id": "e1", "name": "Nafta", "monthly_budget": 400, "active": True}
        ])
        _write(self.data, "expenses.json", [
            {"merchant": "Slovnaft", "amount": 40, "date": TODAY.isoformat()},
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["envelopes_spent_total"], 40)

    def test_negative_estimate_reports_missing_amount(self):
        _write(self.data, "payments.json", [self._payment("p1", 1500, TODAY.day)])
        result = bfs.build_balance_first_summary()
        self.assertLess(result["estimated_after_payments_and_envelopes"], 0)
        self.assertEqual(result["missing_after_everything"], 500)

    def test_no_income_required_current_balance_is_source_of_truth(self):
        # No incomes.json is read anywhere in this function at all —
        # income is optional and never part of the estimate.
        _write(self.data, "payments.json", [self._payment("p1", 100, TODAY.day)])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["current_balance"], 1000)
        self.assertEqual(result["estimated_after_payments"], 900)


if __name__ == "__main__":
    unittest.main()
