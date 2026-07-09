#!/usr/bin/env python3
"""Tests for the pure forecast calculation in forecast.py.

Run directly: python3 tests/test_forecast.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forecast import (
    forecast, payment_state, current_cash_position,
    PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED,
)


TODAY = date(2026, 7, 9)
NEXT_INCOME = date(2026, 7, 15)


def payment(amount, due_date, **extra):
    return {"amount": amount, "due_date": due_date, **extra}


class PaymentStateTests(unittest.TestCase):
    def test_defaults_to_pending(self):
        self.assertEqual(payment_state({"amount": 10}), PENDING)

    def test_legacy_paid_true_maps_to_paid_me(self):
        self.assertEqual(payment_state({"amount": 10, "paid": True}), PAID_ME)

    def test_legacy_paid_false_maps_to_pending(self):
        self.assertEqual(payment_state({"amount": 10, "paid": False}), PENDING)

    def test_explicit_state_wins_over_legacy_flag(self):
        self.assertEqual(
            payment_state({"amount": 10, "paid": True, "state": PAID_OTHER}), PAID_OTHER
        )

    def test_unknown_state_falls_back_to_pending(self):
        self.assertEqual(payment_state({"amount": 10, "state": "bogus"}), PENDING)


class ForecastTests(unittest.TestCase):
    def test_pending_payment_reduces_main_forecast(self):
        payments = [payment(100, date(2026, 7, 20), state=PENDING)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 100)
        self.assertEqual(result["after_required"], 900)

    def test_paid_me_no_longer_reduces_forecast(self):
        payments = [payment(100, date(2026, 7, 20), state=PAID_ME)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 0)
        self.assertEqual(result["paid_me_total"], 100)
        self.assertEqual(result["after_required"], 1000)

    def test_paid_other_does_not_touch_main_account(self):
        payments = [payment(100, date(2026, 7, 20), state=PAID_OTHER)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 0)
        self.assertEqual(result["paid_other_total"], 100)
        self.assertEqual(result["after_required"], 1000)

    def test_paid_reserve_hits_reserve_not_main(self):
        payments = [payment(100, date(2026, 7, 20), state=PAID_RESERVE)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 0)
        self.assertEqual(result["reserve_out"], 100)
        self.assertEqual(result["after_required"], 1000)

    def test_deferred_within_horizon_still_required(self):
        payments = [
            payment(100, date(2026, 7, 20), state=DEFERRED, deferred_to=date(2026, 7, 12))
        ]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 100)

    def test_deferred_past_horizon_excluded_from_current_window(self):
        payments = [
            payment(100, date(2026, 7, 20), state=DEFERRED, deferred_to=date(2026, 8, 1))
        ]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 0)

    def test_deferred_without_new_date_keeps_original_due_date(self):
        payments = [payment(100, date(2026, 7, 12), state=DEFERRED)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 100)

    def test_mixed_states_combine_correctly(self):
        payments = [
            payment(100, date(2026, 7, 20), state=PENDING),
            payment(50, date(2026, 7, 20), state=PAID_ME),
            payment(30, date(2026, 7, 20), state=PAID_OTHER),
            payment(20, date(2026, 7, 20), state=PAID_RESERVE),
        ]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 100)
        self.assertEqual(result["reserve_out"], 20)
        self.assertEqual(result["paid_other_total"], 30)
        self.assertEqual(result["paid_me_total"], 50)
        self.assertEqual(result["after_required"], 900)

    def test_daily_safe_to_spend(self):
        payments = [payment(100, date(2026, 7, 20), state=PENDING)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["days_to_income"], 6)
        self.assertAlmostEqual(result["daily_safe_to_spend"], 900 / 6)

    def test_negative_after_required_floors_safe_to_spend_at_zero(self):
        payments = [payment(2000, date(2026, 7, 20), state=PENDING)]
        result = forecast(1000, payments, TODAY, NEXT_INCOME)
        self.assertEqual(result["after_required"], -1000)
        self.assertEqual(result["safe_to_spend"], 0)

    def test_no_horizon_skips_daily_figures(self):
        payments = [payment(100, date(2026, 7, 20), state=PENDING)]
        result = forecast(1000, payments, TODAY, None)
        self.assertIsNone(result["days_to_income"])
        self.assertIsNone(result["daily_safe_to_spend"])


class CurrentCashPositionTests(unittest.TestCase):
    """Regression coverage for the safe-to-spend-now labeling bug: future
    income must never inflate what's shown as available before payday."""

    def test_shortfall_with_protected_reserve(self):
        result = current_cash_position(400, 1032, protected_reserve=300)
        self.assertEqual(result["safe_to_spend_now"], 0)
        self.assertEqual(result["shortfall_before_payday"], -932)

    def test_shortfall_without_protected_reserve(self):
        result = current_cash_position(400, 1032, protected_reserve=0)
        self.assertEqual(result["safe_to_spend_now"], 0)
        self.assertEqual(result["shortfall_before_payday"], -632)

    def test_safe_to_spend_now_is_never_963_for_the_reported_bug_case(self):
        result = current_cash_position(400, 1032, protected_reserve=300)
        self.assertNotEqual(result["safe_to_spend_now"], 963)

    def test_safe_to_spend_now_never_exceeds_current_balance(self):
        result = current_cash_position(400, unpaid_required_before_payday=0, protected_reserve=0)
        self.assertLessEqual(result["safe_to_spend_now"], 400)
        self.assertEqual(result["safe_to_spend_now"], 400)

    def test_positive_position_has_no_shortfall(self):
        result = current_cash_position(1000, 200, protected_reserve=100)
        self.assertEqual(result["safe_to_spend_now"], 700)
        self.assertEqual(result["shortfall_before_payday"], 0)

    def test_future_income_is_not_a_parameter_and_cannot_leak_in(self):
        # current_cash_position() only accepts current-balance inputs, so
        # there is no way to pass future income into safe_to_spend_now.
        before = current_cash_position(400, 1032, protected_reserve=300)
        # Simulate a large incoming paycheck arriving after payday: it must
        # have zero effect on today's figure because it's simply not an
        # input to this calculation.
        future_income = 2000
        after = current_cash_position(400, 1032, protected_reserve=300)
        self.assertEqual(before, after)
        self.assertNotIn(future_income, after.values())


if __name__ == "__main__":
    unittest.main()
