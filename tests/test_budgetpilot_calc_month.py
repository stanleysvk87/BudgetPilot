#!/usr/bin/env python3
"""Integration tests for budgetpilot.calc_month()'s wiring of debts and
one-time obligations into the forecast.

Debts: an I_owe debt must reduce unpaid_required_before_payday exactly
like a pending payment; an owed_to_me debt must never enter it (see
obligations.debt_to_payment for why).

One-time obligations: due in the current month, they must flow into the
forecast and the cycle-scoped payment_events state model exactly like a
recurring payment; due in a different month, they must not appear at all.

Uses temp data files and patches budgetpilot's module-level TODAY/paths so
it's independent of the real data/ directory and the wall-clock date.

Run directly: python3 tests/test_budgetpilot_calc_month.py
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


class CalcMonthIsolatedTestCase(unittest.TestCase):
    """Base setup shared by the debt- and onetime-wiring tests: temp data
    files and patched module-level TODAY/paths so calc_month() is fully
    independent of the real data/ directory and the wall-clock date."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)
        (data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0, "use_reserve": False, "safe_min": 0,
        }))
        (data / "incomes.json").write_text(json.dumps([]))
        (data / "payments.json").write_text(json.dumps([]))
        (data / "expenses.json").write_text(json.dumps([]))
        self.data = data

        patches = [
            mock.patch.object(bp, "TODAY", date(2026, 7, 9)),
            mock.patch.object(bp, "SETTINGS", data / "settings.json"),
            mock.patch.object(bp, "INCOMES", data / "incomes.json"),
            mock.patch.object(bp, "PAYMENTS", data / "payments.json"),
            mock.patch.object(bp, "EXPENSES", data / "expenses.json"),
            mock.patch.object(bp, "DEBTS", data / "debts.json"),
            mock.patch.object(bp, "ONETIME", data / "onetime.json"),
            # calc_month() calls load_payment_events() with no path, which
            # defaults to payment_events.PAYMENT_EVENTS — patch that too, or
            # this test would read/depend on the real demo data file.
            mock.patch.object(pe, "PAYMENT_EVENTS", data / "payment_events.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def write_debts(self, debts):
        (self.data / "debts.json").write_text(json.dumps(debts))

    def write_onetime(self, onetime):
        (self.data / "onetime.json").write_text(json.dumps(onetime))


class CalcMonthDebtWiringTests(CalcMonthIsolatedTestCase):

    def test_i_owe_pending_debt_reduces_forecast(self):
        self.write_debts([
            {"name": "Peter", "amount": 150, "direction": "I_owe", "due_date": "2026-07-12", "state": "pending"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 150)
        self.assertEqual(r["safe_to_spend_now"], 850)

    def test_i_owe_paid_debt_does_not_reduce_forecast(self):
        self.write_debts([
            {"name": "Peter", "amount": 150, "direction": "I_owe", "due_date": "2026-07-12", "state": "paid_me"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)

    def test_owed_to_me_debt_never_enters_forecast(self):
        self.write_debts([
            {"name": "Jana", "amount": 500, "direction": "owed_to_me", "due_date": "2026-07-12", "state": "pending"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)
        self.assertEqual(r["safe_to_spend_now"], 1000)

    def test_debt_due_after_payday_still_counts_like_a_normal_payment(self):
        # Matches existing behavior for recurring payments due after payday:
        # unpaid_required_before_payday isn't restricted to the payday
        # window, only to due_date >= TODAY (see test_demo_data.py).
        self.write_debts([
            {"name": "Peter", "amount": 150, "direction": "I_owe", "due_date": "2026-07-30", "state": "pending"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 150)

    def test_debt_due_before_today_is_excluded(self):
        self.write_debts([
            {"name": "Peter", "amount": 150, "direction": "I_owe", "due_date": "2026-07-01", "state": "pending"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)


class CalcMonthOnetimeWiringTests(CalcMonthIsolatedTestCase):
    def test_onetime_due_this_month_reduces_forecast(self):
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-07-20"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 180)
        self.assertEqual(r["safe_to_spend_now"], 820)
        names = [p["name"] for p in r["payments"]]
        self.assertIn("Servis auta", names)

    def test_onetime_due_a_different_month_is_excluded(self):
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-08-05"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)
        self.assertEqual(r["payments"], [])

    def test_onetime_due_before_today_in_the_same_month_is_excluded_from_forecast(self):
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-07-01"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)
        # Still shows up in the payments list for the month (e.g. as
        # overdue-but-unpaid), just doesn't count toward the future forecast.
        names = [p["name"] for p in r["payments"]]
        self.assertIn("Servis auta", names)

    def test_onetime_state_baked_on_the_template_is_ignored_without_an_event(self):
        # Same hard rule as recurring payments (see payment_events.
        # effective_payment_state): a template's own baked-in state is
        # never a fallback — only an explicit event for this cycle counts.
        # Otherwise this state would incorrectly leak into every future
        # month the same way the original pre-payment_events bug did.
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-07-20", "state": "paid_me"},
        ])
        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 180)

    def test_onetime_marked_paid_me_via_event_does_not_reduce_forecast(self):
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-07-20"},
        ])
        events = pe.set_payment_event(pe.load_payment_events(), "ot-1", "2026-07", "paid_me")
        pe.save_payment_events(events)

        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)

    def test_onetime_state_is_cycle_scoped_via_payment_events(self):
        # Same guarantee recurring payments already have: a payment_event
        # for this cycle overrides whatever the template's own state is.
        self.write_onetime([
            {"id": "ot-1", "name": "Servis auta", "amount": 180, "due_date": "2026-07-20"},
        ])
        events = pe.load_payment_events()
        events = pe.set_payment_event(events, "ot-1", "2026-07", "paid_other")
        pe.save_payment_events(events)

        r = bp.calc_month(2026, 7)
        self.assertEqual(r["unpaid_required_before_payday"], 0)
        onetime_payment = next(p for p in r["payments"] if p["name"] == "Servis auta")
        self.assertEqual(onetime_payment["state"], "paid_other")


if __name__ == "__main__":
    unittest.main()
