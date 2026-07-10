#!/usr/bin/env python3
"""Tests for the app-views layout: dashboard is summary-only, full lists
live on their own routes/views (docs/navigation_layout.md).

Isolated via a temp data dir (same pattern as test_budgetpilot_web.py's
ThreeMonthForecastTests) and a stubbed run_core() so these don't shell
out to budgetpilot.py against the real data/ dir on a live deployment.

Run directly: python3 tests/test_app_views.py
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

import budgetpilot_web as web
import payment_events as pe
import balance_first_summary as bfs


class AppViewsTestCase(unittest.TestCase):
    """Base: isolated temp data dir wired into every module that reads
    data/*.json, plus a stubbed run_core() (avoids shelling out to
    budgetpilot.py against real data)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)

        (data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0, "use_reserve": False, "safe_min": 0,
            "payday_day": 15, "real_balance": 1000.0,
        }))
        (data / "incomes.json").write_text(json.dumps([]))
        (data / "payments.json").write_text(json.dumps([
            {"id": "p1", "name": "Elektrina", "amount": 80.0, "day": 5, "due_day": 5,
             "frequency": "monthly", "start_month": "2026-01", "active": True},
        ]))
        (data / "payment_events.json").write_text(json.dumps([]))
        (data / "expenses.json").write_text(json.dumps([]))
        (data / "debts.json").write_text(json.dumps([]))
        (data / "onetime.json").write_text(json.dumps([]))
        (data / "envelopes.json").write_text(json.dumps([
            {"id": "e1", "category": "Strava", "monthly_limit": 400.0},
        ]))
        (data / "audit_log.json").write_text(json.dumps([
            {"at": "2026-07-10T09:00:00", "action": "balance_updated", "detail": "1000.00 €"},
        ]))
        (data / "receipts").mkdir(exist_ok=True)

        patches = [
            mock.patch.object(web, "SETTINGS", data / "settings.json"),
            mock.patch.object(web, "INCOMES", data / "incomes.json"),
            mock.patch.object(web, "PAYMENTS", data / "payments.json"),
            mock.patch.object(web, "EXPENSES", data / "expenses.json"),
            mock.patch.object(web, "DEBTS", data / "debts.json"),
            mock.patch.object(web, "ONETIME", data / "onetime.json"),
            mock.patch.object(web, "ENVELOPES", data / "envelopes.json"),
            mock.patch.object(web, "AUDIT_LOG_PATH", data / "audit_log.json"),
            mock.patch.object(web, "RECEIPTS_DIR", data / "receipts"),
            mock.patch.object(pe, "PAYMENT_EVENTS", data / "payment_events.json"),
            mock.patch.object(web, "run_core", return_value=""),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        web.app.config["TESTING"] = True
        self.client = web.app.test_client()


class RouteStatusTests(AppViewsTestCase):
    def test_dashboard_and_all_view_routes_return_200(self):
        for path in ("/", "/payments", "/deferred", "/envelopes", "/expenses",
                     "/receipts", "/history", "/settings"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f"{path} did not return 200")


class DashboardIsSummaryOnlyTests(AppViewsTestCase):
    def test_dashboard_does_not_render_full_payment_sections(self):
        html = self.client.get("/").data.decode()
        self.assertNotIn("Po splatnosti (", html)
        self.assertNotIn("Čaká na potvrdenie (", html)

    def test_dashboard_shows_the_four_summary_cards(self):
        html = self.client.get("/").data.decode()
        self.assertIn("payments-summary", html)
        self.assertIn("deferred-summary", html)
        self.assertIn("envelopes-summary-dashboard", html)
        self.assertIn("activity-summary", html)

    def test_payments_view_has_the_full_sections(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn("Po splatnosti (", html)
        self.assertIn("Čaká na potvrdenie (", html)

    def test_deferred_view_has_its_own_dedicated_section(self):
        html = self.client.get("/deferred").data.decode()
        self.assertIn("Odložené platby (", html)


class DeferredDashboardCardTests(AppViewsTestCase):
    def test_deferred_card_shows_nearest_item_and_open_button(self):
        events = pe.load_payment_events()
        events = pe.defer_payment_to_date(events, "p1", "2026-07", date(2026, 9, 1))
        pe.save_payment_events(events)

        html = self.client.get("/").data.decode()
        self.assertIn("Otvoriť odložené", html)
        self.assertIn("Elektrina", html)
        self.assertIn("2026-09-01", html)

    def test_deferred_card_empty_state_when_nothing_deferred(self):
        html = self.client.get("/").data.decode()
        self.assertIn("Žiadne odložené platby", html)


class BalanceFirstSummaryDashboardFieldsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data = Path(self.tmpdir.name)
        self._orig_data = bfs.DATA
        bfs.DATA = self.data
        self.addCleanup(setattr, bfs, "DATA", self._orig_data)

        (self.data / "settings.json").write_text(json.dumps({"account_balance": 1000}))
        (self.data / "payments.json").write_text(json.dumps([
            {"id": "p1", "name": "Elektrina", "amount": 80.0, "due_day": 5, "active": True},
            {"id": "p2", "name": "Internet", "amount": 20.0, "due_day": 5, "active": True},
        ]))
        (self.data / "payment_events.json").write_text(json.dumps([]))
        (self.data / "envelopes.json").write_text(json.dumps([]))
        (self.data / "expenses.json").write_text(json.dumps([]))
        (self.data / "audit_log.json").write_text(json.dumps([
            {"at": "2026-07-10T09:00:00", "action": "payment_paid", "detail": "Internet"},
        ]))

    def _write_events(self, events):
        (self.data / "payment_events.json").write_text(json.dumps(events))

    def test_next_deferred_item_is_the_earliest_one(self):
        cycle = f"{date.today().year:04d}-{date.today().month:02d}"
        self._write_events([
            {"payment_id": "p1", "cycle_key": cycle, "state": "deferred", "deferred_to": "2026-12-15"},
            {"payment_id": "p2", "cycle_key": cycle, "state": "deferred", "deferred_to": "2026-09-01"},
        ])
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["next_deferred_item"]["id"], "p2")
        self.assertEqual(result["deferred_count"], 2)

    def test_top_deferred_items_capped_at_three(self):
        cycle = f"{date.today().year:04d}-{date.today().month:02d}"
        events = [
            {"payment_id": "p1", "cycle_key": cycle, "state": "deferred", "deferred_to": "2026-12-01"},
            {"payment_id": "p2", "cycle_key": cycle, "state": "deferred", "deferred_to": "2026-12-02"},
        ]
        self._write_events(events)
        result = bfs.build_balance_first_summary()
        self.assertLessEqual(len(result["top_deferred_items"]), 3)

    def test_recent_activity_reflects_audit_log(self):
        result = bfs.build_balance_first_summary()
        self.assertEqual(len(result["recent_activity"]), 1)
        self.assertEqual(result["recent_activity"][0]["action"], "payment_paid")

    def test_unpaid_and_deferred_counts_are_dashboard_aliases(self):
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["unpaid_count"], result["unpaid_payment_count"])
        self.assertEqual(result["deferred_count"], result["deferred_payment_count"])


if __name__ == "__main__":
    unittest.main()
