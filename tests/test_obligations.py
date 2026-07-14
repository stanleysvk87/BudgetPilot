#!/usr/bin/env python3
"""Tests for the pure financial-calendar helpers in obligations.py.

Run directly: python3 tests/test_obligations.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forecast import forecast, PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED
import obligations as ob


TODAY = date(2026, 7, 9)
NEXT_INCOME = date(2026, 7, 15)


class RecurringObligationTests(unittest.TestCase):
    def test_recurring_monthly_obligation_appears_in_current_month(self):
        recurring = [{"name": "Internet", "amount": 55, "due_day": 24, "active": True}]
        result = ob.generate_recurring_for_month(recurring, 2026, 7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["due_date"], date(2026, 7, 24))

    def test_inactive_obligation_does_not_appear(self):
        recurring = [{"name": "Old subscription", "amount": 10, "due_day": 5, "active": False}]
        result = ob.generate_recurring_for_month(recurring, 2026, 7)
        self.assertEqual(result, [])

    def test_cancelled_from_month_does_not_appear(self):
        recurring = [{
            "name": "Kindergarten", "amount": 120, "due_day": 5,
            "active": True, "cancelled_from_month": "2026-07",
        }]
        self.assertTrue(ob.is_recurring_active(recurring[0], 2026, 6))
        self.assertFalse(ob.is_recurring_active(recurring[0], 2026, 7))

    def test_legacy_payment_without_active_field_defaults_active(self):
        legacy = {"name": "Hypotéka", "amount": 820, "day": 20, "frequency": "monthly", "start": "2026-01-20"}
        result = ob.generate_recurring_for_month([legacy], 2026, 7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["due_date"], date(2026, 7, 20))

    def test_start_month_before_start_does_not_appear(self):
        recurring = [{"name": "New loan", "amount": 200, "due_day": 1, "start_month": "2026-09"}]
        self.assertFalse(ob.is_recurring_active(recurring[0], 2026, 7))
        self.assertTrue(ob.is_recurring_active(recurring[0], 2026, 9))


class FrequencyOccurrenceTests(unittest.TestCase):
    """Regression tests for the canonical occurrence check
    (obligations.is_recurring_active / occurrence_matches_frequency).

    Before this fix, is_recurring_active() ignored `frequency` entirely
    and treated every active payment as monthly -- a yearly/quarterly
    bill showed up as due (and unpaid) in every single month on the web
    dashboard and in balance_first_summary.py, even though the older,
    separate budgetpilot.occurs() got this right. These tests cover each
    frequency this bug could affect, plus the interaction with
    cancellation and future start dates the review specifically asked
    for.
    """

    def test_monthly_occurs_every_month(self):
        payment = {"frequency": "monthly", "start": "2026-01-15", "start_month": "2026-01"}
        for month in range(1, 13):
            with self.subTest(month=month):
                self.assertTrue(ob.is_recurring_active(payment, 2026, month))

    def test_quarterly_occurs_every_third_month_from_start(self):
        payment = {"frequency": "quarterly", "start": "2026-01-15", "start_month": "2026-01"}
        expect_true = {1, 4, 7, 10}
        for month in range(1, 13):
            with self.subTest(month=month):
                self.assertEqual(
                    ob.is_recurring_active(payment, 2026, month),
                    month in expect_true,
                )

    def test_yearly_occurs_only_in_start_month_reproduces_original_bug_report(self):
        # This is the exact shape of the reported bug: a once-a-year bill
        # (car insurance) must be "due" only in its own month, in any
        # year on/after its start year -- not in all twelve.
        payment = {
            "id": "p1", "name": "Havarijná poistka", "amount": 400,
            "frequency": "yearly", "start": "2026-01-15", "start_month": "2026-01",
            "active": True,
        }
        for month in range(1, 13):
            with self.subTest(month=month):
                self.assertEqual(ob.is_recurring_active(payment, 2026, month), month == 1)
        # And it recurs the following year, still only in January.
        self.assertTrue(ob.is_recurring_active(payment, 2027, 1))
        self.assertFalse(ob.is_recurring_active(payment, 2027, 7))

    def test_custom_months_occurs_every_n_months_from_start(self):
        payment = {
            "frequency": "custom_months", "every_months": 6,
            "start": "2026-01-01", "start_month": "2026-01",
        }
        expect_true = {1, 7}
        for month in range(1, 13):
            with self.subTest(month=month):
                self.assertEqual(
                    ob.is_recurring_active(payment, 2026, month),
                    month in expect_true,
                )

    def test_custom_months_zero_every_months_does_not_crash_and_is_skipped(self):
        # Reproduces the second reported bug: a web form submission of
        # "0" for every_months used to raise ZeroDivisionError inside
        # this exact check, which render_page() calls for every payment
        # on every page load -- one bad value took the whole app down.
        # Also verifies the "hardening" requirement that a skipped,
        # malformed record is logged rather than silently discarded.
        payment = {
            "id": "p2", "name": "Custom", "frequency": "custom_months",
            "every_months": 0, "start": "2026-01-01", "start_month": "2026-01",
        }
        with self.assertLogs("obligations", level="WARNING") as logs:
            self.assertFalse(ob.is_recurring_active(payment, 2026, 7))
        self.assertIn("every_months=0", logs.output[0])
        self.assertIn("p2", logs.output[0])

    def test_custom_months_negative_every_months_does_not_crash_and_is_skipped(self):
        payment = {
            "frequency": "custom_months", "every_months": -3,
            "start": "2026-01-01", "start_month": "2026-01",
        }
        self.assertFalse(ob.is_recurring_active(payment, 2026, 7))

    def test_custom_months_non_numeric_every_months_does_not_crash_and_is_skipped(self):
        payment = {
            "frequency": "custom_months", "every_months": "many",
            "start": "2026-01-01", "start_month": "2026-01",
        }
        self.assertFalse(ob.is_recurring_active(payment, 2026, 7))

    def test_custom_months_missing_every_months_defaults_to_one_month(self):
        # No explicit every_months at all (old data saved before the
        # field existed) -- historical behavior was "every 1 month".
        payment = {"frequency": "custom_months", "start": "2026-01-01", "start_month": "2026-01"}
        for month in range(1, 13):
            with self.subTest(month=month):
                self.assertTrue(ob.is_recurring_active(payment, 2026, month))

    def test_once_occurs_only_in_the_exact_start_month(self):
        payment = {"frequency": "once", "start": "2026-03-10", "start_month": "2026-03"}
        self.assertTrue(ob.is_recurring_active(payment, 2026, 3))
        self.assertFalse(ob.is_recurring_active(payment, 2026, 2))
        self.assertFalse(ob.is_recurring_active(payment, 2026, 4))
        self.assertFalse(ob.is_recurring_active(payment, 2027, 3))

    def test_cancelled_yearly_payment_does_not_reappear_after_cancellation(self):
        payment = {
            "frequency": "yearly", "start": "2026-01-15", "start_month": "2026-01",
            "cancelled_from_month": "2027-01",
        }
        self.assertTrue(ob.is_recurring_active(payment, 2026, 1))
        self.assertFalse(ob.is_recurring_active(payment, 2027, 1))

    def test_future_start_date_quarterly_payment_does_not_appear_before_start(self):
        payment = {"frequency": "quarterly", "start": "2026-10-01", "start_month": "2026-10"}
        self.assertFalse(ob.is_recurring_active(payment, 2026, 7))
        self.assertFalse(ob.is_recurring_active(payment, 2026, 9))
        self.assertTrue(ob.is_recurring_active(payment, 2026, 10))

    def test_unrecognized_frequency_does_not_occur(self):
        # occurrence_matches_frequency() must fail closed (not occurring)
        # rather than silently defaulting to monthly for a garbled value.
        payment = {"frequency": "biannual-oops", "start": "2026-01-01", "start_month": "2026-01"}
        self.assertFalse(ob.is_recurring_active(payment, 2026, 7))


class NormalizeEveryMonthsTests(unittest.TestCase):
    def test_missing_key_returns_default(self):
        self.assertEqual(ob.normalize_every_months({}), 1)
        self.assertEqual(ob.normalize_every_months({}, default=3), 3)

    def test_valid_positive_value_is_returned_as_int(self):
        self.assertEqual(ob.normalize_every_months({"every_months": "6"}), 6)
        self.assertEqual(ob.normalize_every_months({"every_months": 6.0}), 6)

    def test_zero_or_negative_or_non_numeric_returns_none(self):
        with self.assertLogs("obligations", level="WARNING"):
            self.assertIsNone(ob.normalize_every_months({"every_months": 0}))
        with self.assertLogs("obligations", level="WARNING"):
            self.assertIsNone(ob.normalize_every_months({"every_months": -1}))
        with self.assertLogs("obligations", level="WARNING"):
            self.assertIsNone(ob.normalize_every_months({"every_months": "many"}))
        with self.assertLogs("obligations", level="WARNING"):
            self.assertIsNone(ob.normalize_every_months({"every_months": None}))


class OnetimeObligationTests(unittest.TestCase):
    def test_onetime_obligation_appears_only_when_due(self):
        item = {"name": "Car repair", "amount": 300, "due_date": "2026-07-18"}
        self.assertTrue(ob.onetime_due_in_month(item, 2026, 7))
        self.assertFalse(ob.onetime_due_in_month(item, 2026, 8))

    def test_generate_onetime_for_month_resolves_due_date(self):
        items = [
            {"name": "Car repair", "amount": 300, "due_date": "2026-07-18"},
            {"name": "Vacation deposit", "amount": 150, "due_date": "2026-08-01"},
        ]
        result = ob.generate_onetime_for_month(items, 2026, 7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Car repair")
        self.assertEqual(result[0]["due_date"], date(2026, 7, 18))


class DebtTests(unittest.TestCase):
    def test_i_owe_debt_reduces_forecast(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "due_date": "2026-07-20", "person": "Peter"}
        payment = ob.debt_to_payment(debt)
        result = forecast(1000, [payment], TODAY, NEXT_INCOME)
        self.assertEqual(result["required_main"], 100)
        self.assertEqual(result["after_required"], 900)

    def test_i_owe_debt_already_paid_does_not_reduce_forecast(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "due_date": "2026-07-20", "state": PAID_ME}
        self.assertIsNone(ob.debt_to_payment(debt))

    def test_owed_to_me_does_not_count_as_safe_money_before_received(self):
        debt = {"direction": ob.OWED_TO_ME, "amount": 500, "due_date": "2026-07-20", "person": "Jana"}
        self.assertIsNone(ob.debt_to_payment(debt))
        # Even if someone tried to forecast with it, there is nothing to feed in.
        result = forecast(1000, [], TODAY, NEXT_INCOME)
        self.assertEqual(result["safe_to_spend"], 1000)

    def test_owed_to_me_marked_received_is_still_not_converted_to_a_payment(self):
        debt = {"direction": ob.OWED_TO_ME, "amount": 500, "due_date": "2026-07-20", "state": ob.RECEIVED}
        self.assertIsNone(ob.debt_to_payment(debt))


class SetDebtStateTests(unittest.TestCase):
    def test_i_owe_can_be_marked_paid_me(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "state": PENDING}
        result = ob.set_debt_state(debt, PAID_ME)
        self.assertEqual(result["state"], PAID_ME)

    def test_i_owe_can_be_deferred(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "state": PENDING}
        result = ob.set_debt_state(debt, DEFERRED)
        self.assertEqual(result["state"], DEFERRED)

    def test_i_owe_cannot_be_marked_received(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "state": PENDING}
        with self.assertRaises(ValueError):
            ob.set_debt_state(debt, ob.RECEIVED)

    def test_owed_to_me_can_be_marked_received(self):
        debt = {"direction": ob.OWED_TO_ME, "amount": 500, "state": PENDING}
        result = ob.set_debt_state(debt, ob.RECEIVED)
        self.assertEqual(result["state"], ob.RECEIVED)

    def test_owed_to_me_cannot_be_marked_paid_me(self):
        debt = {"direction": ob.OWED_TO_ME, "amount": 500, "state": PENDING}
        with self.assertRaises(ValueError):
            ob.set_debt_state(debt, PAID_ME)

    def test_unknown_direction_is_rejected(self):
        debt = {"direction": "sideways", "amount": 10, "state": PENDING}
        with self.assertRaises(ValueError):
            ob.set_debt_state(debt, PENDING)

    def test_other_metadata_preserved(self):
        debt = {"direction": ob.I_OWE, "amount": 100, "state": PENDING, "name": "Peter", "note": "pôžička na auto"}
        result = ob.set_debt_state(debt, PAID_ME)
        self.assertEqual(result["name"], "Peter")
        self.assertEqual(result["note"], "pôžička na auto")


class SnapshotTests(unittest.TestCase):
    def test_payday_real_balance_snapshot_is_source_of_truth(self):
        settings = {"account_balance": 150.0, "real_balance": 150.0}
        snapshots = [
            ob.new_cycle_snapshot(150.0, today=date(2026, 6, 15)),
            ob.new_cycle_snapshot(2100.0, today=date(2026, 7, 15)),
        ]
        self.assertEqual(ob.resolve_account_balance(settings, snapshots), 2100.0)

    def test_no_snapshot_falls_back_to_settings_balance(self):
        settings = {"account_balance": 150.0}
        self.assertEqual(ob.resolve_account_balance(settings, []), 150.0)


class SetupNeededTests(unittest.TestCase):
    def test_missing_payday_needs_setup(self):
        self.assertTrue(ob.needs_setup({"real_balance": 100}, []))

    def test_missing_real_balance_needs_setup(self):
        self.assertTrue(ob.needs_setup({"payday_day": 15}, []))

    def test_complete_settings_do_not_need_setup(self):
        self.assertFalse(ob.needs_setup({"payday_day": 15, "real_balance": 100}, []))


class SettingsMergeTests(unittest.TestCase):
    def test_settings_update_preserves_existing_payday_and_real_balance(self):
        existing = {"payday_day": 15, "real_balance": 850.0, "reserve_amount": 100.0, "account_balance": 850.0, "use_reserve": True, "safe_min": 100.0}
        updates = {"account_balance": 900.0, "use_reserve": False, "safe_min": 0.0}
        merged = ob.merge_settings(existing, updates)
        self.assertEqual(merged["payday_day"], 15)
        self.assertEqual(merged["real_balance"], 850.0)
        self.assertEqual(merged["reserve_amount"], 100.0)
        self.assertEqual(merged["account_balance"], 900.0)
        self.assertFalse(merged["use_reserve"])


class PaymentMergeTests(unittest.TestCase):
    def test_payment_update_preserves_metadata_not_touched_by_form(self):
        existing = {
            "id": "abc123", "name": "Internet", "amount": 40, "day": 24, "due_day": 24,
            "frequency": "monthly", "start": "2026-01-24", "start_month": "2026-01",
            "priority": "important", "flexibility": "can_defer", "active": True,
            "paid": True,
        }
        form_updates = {
            "name": "Internet", "amount": 55.0, "day": 24, "due_day": 24,
            "frequency": "monthly", "start": "2026-01-24", "start_month": "2026-01",
        }
        merged = ob.merge_payment_fields(existing, form_updates)
        self.assertEqual(merged["id"], "abc123")
        self.assertTrue(merged["active"])
        self.assertEqual(merged["priority"], "important")
        self.assertEqual(merged["flexibility"], "can_defer")
        self.assertEqual(merged["start_month"], "2026-01")
        self.assertEqual(merged["amount"], 55.0)
        self.assertTrue(merged["paid"])


class EnsureRecurringCompatibleTests(unittest.TestCase):
    def test_new_payment_contains_due_day_and_active_true(self):
        item = ob.ensure_recurring_compatible({"name": "Nájom", "amount": 500, "day": 1, "due_day": 1, "frequency": "monthly", "start": "2026-07-01", "start_month": "2026-07"}, new_id="xyz789")
        self.assertEqual(item["id"], "xyz789")
        self.assertEqual(item["due_day"], 1)
        self.assertTrue(item["active"])
        self.assertEqual(item["priority"], "mandatory")
        self.assertEqual(item["flexibility"], "hard_due")
        self.assertFalse(item["paid"])

    def test_existing_id_and_active_are_not_overwritten(self):
        item = ob.ensure_recurring_compatible({"id": "keepme", "name": "Nájom", "amount": 500, "day": 1, "active": False, "priority": "flexible"}, new_id="ignored")
        self.assertEqual(item["id"], "keepme")
        self.assertFalse(item["active"])
        self.assertEqual(item["priority"], "flexible")


class SetPaymentStateTests(unittest.TestCase):
    def test_set_paid_me_marks_legacy_paid_true(self):
        payment = {"id": "p1", "name": "Internet", "amount": 25, "priority": "mandatory"}
        updated = ob.set_payment_state(payment, PAID_ME)
        self.assertEqual(updated["state"], PAID_ME)
        self.assertTrue(updated["paid"])
        self.assertEqual(updated["priority"], "mandatory")

    def test_set_paid_other_clears_legacy_paid_flag(self):
        payment = {"id": "p1", "amount": 25, "paid": True}
        updated = ob.set_payment_state(payment, PAID_OTHER)
        self.assertEqual(updated["state"], PAID_OTHER)
        self.assertFalse(updated["paid"])

    def test_set_paid_reserve(self):
        payment = {"id": "p1", "amount": 25}
        updated = ob.set_payment_state(payment, PAID_RESERVE)
        self.assertEqual(updated["state"], PAID_RESERVE)
        self.assertFalse(updated["paid"])

    def test_reset_to_pending_from_paid(self):
        payment = {"id": "p1", "amount": 25, "state": PAID_ME, "paid": True}
        updated = ob.set_payment_state(payment, PENDING)
        self.assertEqual(updated["state"], PENDING)
        self.assertFalse(updated["paid"])

    def test_unknown_state_is_rejected(self):
        with self.assertRaises(ValueError):
            ob.set_payment_state({"amount": 25}, "bogus")

    def test_legacy_paid_true_without_state_field_behaves_as_paid_me(self):
        legacy = {"amount": 25, "paid": True}
        from forecast import payment_state
        self.assertEqual(payment_state(legacy), PAID_ME)


class DeferPaymentTests(unittest.TestCase):
    def test_defer_sets_state_and_pushes_seven_days_from_today(self):
        payment = {"id": "p1", "name": "Škôlka", "amount": 120, "priority": "important"}
        updated = ob.defer_payment(payment, date(2026, 7, 9))
        self.assertEqual(updated["state"], DEFERRED)
        self.assertEqual(updated["deferred_to"], "2026-07-16")
        self.assertEqual(updated["priority"], "important")
        self.assertEqual(updated["name"], "Škôlka")

    def test_defer_again_stacks_on_previous_deferred_to(self):
        payment = {"id": "p1", "amount": 120, "state": DEFERRED, "deferred_to": "2026-07-16"}
        updated = ob.defer_payment(payment, date(2026, 7, 20))
        self.assertEqual(updated["deferred_to"], "2026-07-23")

    def test_defer_preserves_metadata_not_related_to_state(self):
        payment = {"id": "p1", "amount": 120, "due_day": 10, "start_month": "2026-01", "active": True}
        updated = ob.defer_payment(payment, date(2026, 7, 9))
        self.assertEqual(updated["due_day"], 10)
        self.assertEqual(updated["start_month"], "2026-01")
        self.assertTrue(updated["active"])


if __name__ == "__main__":
    unittest.main()
