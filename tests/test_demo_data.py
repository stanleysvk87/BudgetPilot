#!/usr/bin/env python3
"""Sanity checks for the clean demo/default dataset in data/*.json.

These pin the forecast to the fixed demo cycle the data was written for
(today = 2026-07-09, payday = 2026-07-15). If the demo data is ever
reset again, update these dates alongside it.

Run directly: python3 tests/test_demo_data.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forecast import forecast, payment_state, VALID_STATES
import obligations as ob
from payment_events import apply_payment_events

DATA = ROOT / "data"
TODAY = date(2026, 7, 9)
NEXT_INCOME = date(2026, 7, 15)
CYCLE_KEY = "2026-07"


def load(name):
    return json.loads((DATA / name).read_text())


class DemoDataLoadsTests(unittest.TestCase):
    def test_all_data_files_parse(self):
        for name in ("settings.json", "incomes.json", "payments.json", "expenses.json", "payment_events.json"):
            self.assertTrue((DATA / name).exists(), f"missing {name}")
            load(name)  # must not raise

    def test_settings_no_longer_need_first_run_setup(self):
        settings = load("settings.json")
        payments = load("payments.json")
        self.assertFalse(ob.needs_setup(settings, payments))

    def test_demo_payments_json_holds_templates_not_baked_in_state(self):
        # payments.json must represent recurring templates only — no
        # payment may carry a permanently-paid state on the template
        # itself, or it would incorrectly stay "paid" every future month.
        payments = load("payments.json")
        for p in payments:
            self.assertNotIn("state", p)
            self.assertFalse(p.get("paid", False))

    def test_demo_payment_events_cover_every_non_pending_state(self):
        payments = load("payments.json")
        events = load("payment_events.json")
        resolved = apply_payment_events(
            ob.generate_recurring_for_month(payments, 2026, 7), events, CYCLE_KEY
        )
        states_present = {payment_state(p) for p in resolved}
        self.assertEqual(states_present, VALID_STATES)

    def test_demo_payments_cover_mandatory_flexible_and_optional(self):
        payments = load("payments.json")
        priorities = {p.get("priority") for p in payments}
        flexibilities = {p.get("flexibility") for p in payments}
        self.assertIn("mandatory", priorities)
        self.assertIn("optional", priorities)
        self.assertIn("can_defer", flexibilities)


class DemoDashboardForecastTests(unittest.TestCase):
    def setUp(self):
        self.settings = load("settings.json")
        payments = load("payments.json")
        events = load("payment_events.json")
        templates_for_july = ob.generate_recurring_for_month(payments, 2026, 7)
        self.resolved = apply_payment_events(templates_for_july, events, CYCLE_KEY)

    def test_expected_recurring_payments_resolved_for_july(self):
        self.assertEqual(len(self.resolved), 7)

    def test_forecast_matches_hand_computed_demo_numbers(self):
        result = forecast(self.settings["account_balance"], self.resolved, TODAY, NEXT_INCOME)
        # pending: Hypotéka 750 + Predplatné 12 + Splátka pôžičky 150
        # + Škôlka 120 (deferred to 2026-07-14, still inside the window)
        self.assertEqual(result["required_main"], 750 + 12 + 150 + 120)
        self.assertEqual(result["paid_me_total"], 95)
        self.assertEqual(result["paid_other_total"], 25)
        self.assertEqual(result["reserve_out"], 28)
        self.assertEqual(
            result["after_required"],
            self.settings["account_balance"] - (750 + 12 + 150 + 120),
        )

    def test_account_balance_and_reserve_are_small_clean_numbers(self):
        # Easy to verify by hand, not huge/unrealistic.
        self.assertLess(self.settings["account_balance"], 5000)
        self.assertLess(self.settings["reserve_amount"], 5000)


class DemoDataNextCycleIsolationTests(unittest.TestCase):
    """The demo payment_events.json only has entries for 2026-07 — August
    must not inherit any of July's paid/deferred states."""

    def test_august_resolves_all_demo_payments_as_pending(self):
        payments = load("payments.json")
        events = load("payment_events.json")
        templates_for_august = ob.generate_recurring_for_month(payments, 2026, 8)
        resolved = apply_payment_events(templates_for_august, events, "2026-08")
        states_present = {payment_state(p) for p in resolved}
        self.assertEqual(states_present, {"pending"})


if __name__ == "__main__":
    unittest.main()
