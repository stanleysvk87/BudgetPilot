#!/usr/bin/env python3
"""Tests for the cycle-scoped payment-state model in payment_events.py.

Run directly: python3 tests/test_payment_events.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forecast import payment_state, PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED
import payment_events as pe


TEMPLATE = {
    "id": "p1", "name": "Elektrina", "amount": 95.0, "due_day": 18,
    "frequency": "monthly", "start_month": "2026-01",
    "priority": "mandatory", "flexibility": "hard_due", "active": True,
}


class CycleKeyTests(unittest.TestCase):
    def test_cycle_key_for_date_is_year_month(self):
        self.assertEqual(pe.cycle_key_for_date(date(2026, 7, 9)), "2026-07")

    def test_get_current_cycle_key_defaults_to_today(self):
        self.assertEqual(pe.get_current_cycle_key(date(2026, 8, 1)), "2026-08")

    def test_get_current_cycle_key_accepts_unused_settings_arg(self):
        # Forward-compatible signature for a future payday-cycle slice.
        self.assertEqual(pe.get_current_cycle_key(date(2026, 8, 1), settings={"payday_day": 15}), "2026-08")


class NoEventDefaultsToPendingTests(unittest.TestCase):
    def test_no_event_is_pending(self):
        self.assertEqual(pe.effective_payment_state(TEMPLATE, event=None), PENDING)

    def test_no_event_ignores_legacy_paid_true_on_template(self):
        # The core bug this module fixes: a template's own baked-in state
        # must never leak through as an ongoing fallback.
        legacy = {**TEMPLATE, "paid": True, "state": PAID_ME}
        self.assertEqual(pe.effective_payment_state(legacy, event=None), PENDING)

    def test_apply_payment_events_defaults_every_payment_to_pending_with_no_events(self):
        resolved = pe.apply_payment_events([TEMPLATE], [], "2026-07")
        self.assertEqual(payment_state(resolved[0]), PENDING)
        self.assertFalse(resolved[0]["paid"])


class CycleIsolationTests(unittest.TestCase):
    """A recurring payment appears every month; marking it paid in one
    cycle must never affect another cycle."""

    def test_paid_in_july_does_not_carry_into_august(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_ME)
        july = pe.apply_payment_events([TEMPLATE], events, "2026-07")
        august = pe.apply_payment_events([TEMPLATE], events, "2026-08")
        self.assertEqual(payment_state(july[0]), PAID_ME)
        self.assertEqual(payment_state(august[0]), PENDING)

    def test_deferred_in_july_does_not_change_august_default(self):
        events = pe.defer_payment_event([], "p1", "2026-07", date(2026, 7, 9))
        july = pe.apply_payment_events([TEMPLATE], events, "2026-07")
        august = pe.apply_payment_events([TEMPLATE], events, "2026-08")
        self.assertEqual(payment_state(july[0]), DEFERRED)
        self.assertEqual(july[0]["deferred_to"], "2026-07-16")
        self.assertEqual(payment_state(august[0]), PENDING)
        self.assertNotIn("deferred_to", august[0])

    def test_event_only_overrides_its_own_cycle(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_OTHER)
        events = pe.set_payment_event(events, "p1", "2026-09", PAID_RESERVE)
        aug = pe.apply_payment_events([TEMPLATE], events, "2026-08")
        self.assertEqual(payment_state(aug[0]), PENDING)


class SetPaymentEventTests(unittest.TestCase):
    def test_set_creates_new_event(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_ME)
        event = pe.get_payment_event(events, "p1", "2026-07")
        self.assertIsNotNone(event)
        self.assertEqual(event["state"], PAID_ME)

    def test_set_updates_existing_event_for_same_cycle_in_place(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_ME)
        events = pe.set_payment_event(events, "p1", "2026-07", PAID_OTHER)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["state"], PAID_OTHER)

    def test_reset_to_pending_works(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_ME)
        events = pe.set_payment_event(events, "p1", "2026-07", PENDING)
        resolved = pe.apply_payment_events([TEMPLATE], events, "2026-07")
        self.assertEqual(payment_state(resolved[0]), PENDING)
        self.assertFalse(resolved[0]["paid"])

    def test_unknown_state_is_rejected(self):
        with self.assertRaises(ValueError):
            pe.set_payment_event([], "p1", "2026-07", "bogus")

    def test_other_payments_events_in_same_cycle_are_untouched(self):
        events = pe.set_payment_event([], "p1", "2026-07", PAID_ME)
        events = pe.set_payment_event(events, "p2", "2026-07", PAID_OTHER)
        events = pe.set_payment_event(events, "p1", "2026-07", PENDING)
        self.assertEqual(pe.get_payment_event(events, "p2", "2026-07")["state"], PAID_OTHER)


class TemplateMetadataPreservedTests(unittest.TestCase):
    def test_apply_payment_events_preserves_template_metadata(self):
        template = {
            **TEMPLATE,
            "start_month": "2026-01", "cancelled_from_month": "2027-01",
        }
        events = pe.set_payment_event([], "p1", "2026-07", PAID_RESERVE)
        resolved = pe.apply_payment_events([template], events, "2026-07")[0]
        for key in ("id", "name", "amount", "due_day", "priority", "flexibility", "active", "start_month", "cancelled_from_month"):
            self.assertEqual(resolved[key], template[key])

    def test_defer_payment_event_does_not_mutate_template(self):
        template = dict(TEMPLATE)
        pe.defer_payment_event([], "p1", "2026-07", date(2026, 7, 9))
        self.assertEqual(template, TEMPLATE)
        self.assertNotIn("state", template)
        self.assertNotIn("deferred_to", template)


class DeferPaymentEventTests(unittest.TestCase):
    def test_defer_sets_deferred_state_and_pushes_seven_days(self):
        events = pe.defer_payment_event([], "p1", "2026-07", date(2026, 7, 9))
        event = pe.get_payment_event(events, "p1", "2026-07")
        self.assertEqual(event["state"], DEFERRED)
        self.assertEqual(event["deferred_to"], "2026-07-16")

    def test_defer_again_stacks_within_the_same_cycle(self):
        events = pe.defer_payment_event([], "p1", "2026-07", date(2026, 7, 9))
        events = pe.defer_payment_event(events, "p1", "2026-07", date(2026, 7, 20))
        event = pe.get_payment_event(events, "p1", "2026-07")
        self.assertEqual(event["deferred_to"], "2026-07-23")

    def test_defer_scoped_to_current_cycle_only(self):
        events = pe.defer_payment_event([], "p1", "2026-07", date(2026, 7, 9))
        self.assertIsNone(pe.get_payment_event(events, "p1", "2026-08"))


class UrgencyLabelTests(unittest.TestCase):
    TODAY = date(2026, 7, 9)

    def test_overdue(self):
        self.assertEqual(pe.urgency_label(date(2026, 7, 8), self.TODAY), pe.OVERDUE)

    def test_due_today(self):
        self.assertEqual(pe.urgency_label(date(2026, 7, 9), self.TODAY), pe.DUE_TODAY)

    def test_soon_within_seven_days(self):
        self.assertEqual(pe.urgency_label(date(2026, 7, 16), self.TODAY), pe.SOON)

    def test_later_beyond_seven_days(self):
        self.assertEqual(pe.urgency_label(date(2026, 7, 20), self.TODAY), pe.LATER)

    def test_missing_due_date_is_later(self):
        self.assertEqual(pe.urgency_label(None, self.TODAY), pe.LATER)


class GroupPaymentsByStatusTests(unittest.TestCase):
    TODAY = date(2026, 7, 9)

    def test_groups_by_effective_state(self):
        payments = [
            {"id": "a", "name": "A", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 20)},
            {"id": "b", "name": "B", "amount": 20, "state": DEFERRED, "due_date": date(2026, 7, 5), "deferred_to": "2026-07-20"},
            {"id": "c", "name": "C", "amount": 30, "state": PAID_ME, "due_date": date(2026, 7, 1)},
        ]
        groups = pe.group_payments_by_status(payments, self.TODAY)
        self.assertEqual([p["id"] for p in groups["unpaid"]], ["a"])
        self.assertEqual([p["id"] for p in groups["deferred"]], ["b"])
        self.assertEqual([p["id"] for p in groups["paid"]], ["c"])

    def test_unpaid_sorted_most_urgent_first(self):
        payments = [
            {"id": "later", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 25)},
            {"id": "overdue", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 1)},
            {"id": "soon", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 12)},
            {"id": "due_today", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 9)},
        ]
        groups = pe.group_payments_by_status(payments, self.TODAY)
        self.assertEqual([p["id"] for p in groups["unpaid"]], ["overdue", "due_today", "soon", "later"])

    def test_unpaid_items_carry_urgency_label(self):
        payments = [{"id": "a", "amount": 10, "state": PENDING, "due_date": date(2026, 7, 1)}]
        groups = pe.group_payments_by_status(payments, self.TODAY)
        self.assertEqual(groups["unpaid"][0]["urgency"], pe.OVERDUE)


if __name__ == "__main__":
    unittest.main()
