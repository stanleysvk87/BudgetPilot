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

from forecast import forecast, payment_state, current_cash_position, VALID_STATES
import obligations as ob
import envelopes as env
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


class DemoDashboardCurrentPositionTests(unittest.TestCase):
    """Regression test for the safe-to-spend labeling bug, pinned to the
    exact numbers from the bug report: balance 400, reserve 300, unpaid
    required before payday 1032 (see DemoDashboardForecastTests above for
    where 1032 comes from) — safe_to_spend_now must be 0, not 963."""

    def setUp(self):
        self.settings = load("settings.json")
        payments = load("payments.json")
        events = load("payment_events.json")
        templates_for_july = ob.generate_recurring_for_month(payments, 2026, 7)
        self.resolved = apply_payment_events(templates_for_july, events, CYCLE_KEY)
        self.account_balance = self.settings["account_balance"]
        self.protected_reserve = self.settings["safe_min"]
        upcoming = [p for p in self.resolved if p.get("due_date", TODAY) >= TODAY]
        self.fc = forecast(self.account_balance, upcoming, TODAY, NEXT_INCOME)

    def test_unpaid_required_before_payday_matches_bug_report(self):
        self.assertEqual(self.fc["required_main"], 1032)

    def test_safe_to_spend_now_is_zero_not_inflated_by_future_income(self):
        position = current_cash_position(
            self.account_balance, self.fc["required_main"], self.protected_reserve
        )
        self.assertEqual(position["safe_to_spend_now"], 0)
        self.assertNotEqual(position["safe_to_spend_now"], 963)

    def test_shortfall_before_payday_matches_bug_report(self):
        position = current_cash_position(
            self.account_balance, self.fc["required_main"], self.protected_reserve
        )
        self.assertEqual(position["shortfall_before_payday"], -932)

    def test_safe_to_spend_now_never_exceeds_current_balance(self):
        position = current_cash_position(
            self.account_balance, self.fc["required_main"], self.protected_reserve
        )
        self.assertLessEqual(position["safe_to_spend_now"], self.account_balance)

    def test_future_income_only_affects_a_separately_labeled_projection(self):
        future_income = 2000.0  # the demo's July payday, arrives after TODAY
        expense_total = 45.0 + 60.0  # demo expenses.json

        position = current_cash_position(
            self.account_balance, self.fc["required_main"], self.protected_reserve
        )
        projected_after_payday = (
            self.account_balance + future_income
            - self.fc["required_main"] - expense_total - self.protected_reserve
        )

        # future_income must not appear anywhere in the current-position figures.
        self.assertEqual(position["safe_to_spend_now"], 0)
        self.assertEqual(position["shortfall_before_payday"], -932)
        # It only shows up in the separately labeled projection.
        self.assertEqual(projected_after_payday, 963)


class DemoEnvelopesTests(unittest.TestCase):
    """data/envelopes.json + data/expenses.json (demo: Nafta 45, Potraviny
    60, both in July) — pins the numbers so a future data reset notices if
    the categories drift out of sync with the demo expenses."""

    def setUp(self):
        self.envelope_defs = load("envelopes.json")
        self.expenses = load("expenses.json")
        self.this_month = env.expenses_in_month(self.expenses, TODAY.year, TODAY.month)

    def test_demo_envelope_categories(self):
        categories = {e["category"] for e in self.envelope_defs}
        self.assertEqual(categories, {"Potraviny", "Nafta", "Deti"})

    def test_summary_matches_demo_expenses(self):
        summary = env.envelopes_summary(self.envelope_defs, self.this_month)
        by_category = {r["category"]: r for r in summary["rows"]}
        self.assertEqual(by_category["Potraviny"]["spent"], 60)
        self.assertEqual(by_category["Nafta"]["spent"], 45)
        self.assertEqual(by_category["Deti"]["spent"], 0)
        self.assertFalse(any(r["over_budget"] for r in summary["rows"]))


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
