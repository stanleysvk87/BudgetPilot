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

from forecast import forecast, PENDING, PAID_ME
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


if __name__ == "__main__":
    unittest.main()
