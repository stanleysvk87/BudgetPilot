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
import base64
import os
import sys
import tempfile
import unittest
from io import BytesIO
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
            mock.patch.object(web, "BASE", data),
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
            mock.patch.object(bfs, "DATA", data),
            mock.patch.object(web, "run_core", return_value=""),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        web.app.config["TESTING"] = True
        self.client = web.app.test_client()

    def _cycle(self):
        return f"{date.today().year:04d}-{date.today().month:02d}"


class RouteStatusTests(AppViewsTestCase):
    def test_dashboard_and_all_view_routes_return_200(self):
        for path in ("/", "/payments", "/deferred", "/envelopes", "/expenses",
                     "/receipts", "/history", "/settings", "/manage", "/problems"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f"{path} did not return 200")

    def test_security_headers_are_set(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_basic_auth_is_required_when_password_env_is_set(self):
        with mock.patch.dict(os.environ, {"BUDGETPILOT_PASSWORD": "tajne", "BUDGETPILOT_USER": "saldo"}):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 401)
            self.assertIn("Basic", response.headers["WWW-Authenticate"])

            token = base64.b64encode(b"saldo:tajne").decode()
            response = self.client.get("/", headers={"Authorization": f"Basic {token}"})
            self.assertEqual(response.status_code, 200)


class DashboardIsSummaryOnlyTests(AppViewsTestCase):
    def test_dashboard_does_not_render_full_payment_sections(self):
        html = self.client.get("/").data.decode()
        self.assertNotIn("Po splatnosti (", html)
        self.assertNotIn("Čaká na potvrdenie (", html)
        self.assertNotIn('id="payment-inbox"', html)

    def test_dashboard_shows_the_four_summary_cards(self):
        html = self.client.get("/").data.decode()
        self.assertIn("payments-summary", html)
        self.assertIn("deferred-summary", html)
        self.assertIn("envelopes-summary-dashboard", html)
        self.assertIn("activity-summary", html)

    def test_views_render_app_shell_header_and_layout_class(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn('class="app app-payments"', html)
        self.assertIn("Saldo · cyklus", html)
        self.assertIn("Pracovný zoznam povinností", html)
        self.assertNotIn("Akcie a formuláre", html)

        manage_html = self.client.get("/manage").data.decode()
        self.assertIn('class="app app-manage"', manage_html)
        self.assertIn("Akcie a formuláre", manage_html)

    def test_dashboard_uses_full_width_app_layout(self):
        html = self.client.get("/").data.decode()
        self.assertIn('class="app app-dashboard"', html)
        self.assertNotIn("Akcie a formuláre", html)

    def test_dashboard_labels_available_money_as_real_available(self):
        html = self.client.get("/").data.decode()
        self.assertIn("Reálne k dispozícii", html)
        self.assertIn("Ešte treba zaplatiť", html)
        self.assertNotIn("<div class=\"label\">Bezpečne minúť teraz", html)

    def test_dashboard_contains_visible_calculation_breakdown(self):
        html = self.client.get("/").data.decode()
        self.assertIn("dashboard-hero", html)
        self.assertIn("Rozpad výpočtu", html)
        self.assertIn("Zaplatené mimo zostatku", html)

    def test_payment_impact_uses_custom_modal(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn("impact-modal-overlay", html)
        self.assertIn("BP_PAYMENT_IMPACT_CONFIRM_V1", html)
        payment_script = html.split("BP_PAYMENT_IMPACT_CONFIRM_V1", 1)[1].split("BP_DEFER_DATE_REQUIRED_V1", 1)[0]
        self.assertNotIn("window.confirm", payment_script)

    def test_mobile_bottom_bar_prioritizes_workflow_actions(self):
        html = self.client.get("/").data.decode()
        bottomnav = html.split('<nav class="bottomnav">', 1)[1].split("</nav>", 1)[0]
        self.assertIn('href="/expenses#expense-quick"', bottomnav)
        self.assertIn('href="/payments"', bottomnav)
        self.assertIn('href="/#balance-update-field"', bottomnav)
        self.assertIn("Stav účtu", bottomnav)
        self.assertNotIn('href="/deferred"', bottomnav)
        self.assertNotIn('href="/envelopes"', bottomnav)
        self.assertNotIn('href="/receipts"', bottomnav)

    def test_payments_view_has_the_payment_inbox(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn('id="payment-inbox"', html)
        self.assertIn("Na zaplatenie", html)
        self.assertIn("work-tab", html)

    def test_payments_view_keeps_management_out_of_the_daily_workflow(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn("/manage#edit-form-payment", html)
        self.assertNotIn("Správa pravidelných platieb", html)
        self.assertNotIn('id="payment-templates"', html)
        self.assertNotIn('<div class="manager-grid">', html)

    def test_manage_view_contains_payment_management(self):
        html = self.client.get("/manage").data.decode()
        self.assertIn("Správa pravidelných platieb", html)
        self.assertIn("manager-section", html)
        self.assertIn("manager-grid", html)
        self.assertIn("✓ Zaplatené z účtu", html)
        self.assertIn("Nastaviť stav", html)
        self.assertIn("Ešte znižuje dostupnú sumu", html)
        self.assertNotIn("<h2>Pravidelné platby</h2>", html)

    def test_deferred_view_has_its_own_dedicated_section(self):
        html = self.client.get("/deferred").data.decode()
        self.assertIn("Odložené platby (", html)

    def test_settings_links_to_balance_debug(self):
        html = self.client.get("/settings").data.decode()
        self.assertIn("Diagnostika výpočtu", html)
        self.assertIn("/debug/balance", html)
        self.assertIn("/problems", html)

    def test_manage_view_shows_stability_and_backup_panel(self):
        html = self.client.get("/manage").data.decode()
        self.assertIn("Stabilita systému", html)
        self.assertIn("Diagnostika dát", html)
        self.assertIn("Zálohy a obnova", html)
        self.assertIn("Zatiaľ nie je dostupná žiadna záloha", html)


class BalanceDebugViewTests(AppViewsTestCase):
    def test_balance_debug_view_shows_formula_and_items(self):
        html = self.client.get("/debug/balance").data.decode()
        self.assertIn("Debug výpočtu zostatku", html)
        self.assertIn("Vzorec", html)
        self.assertIn("Nezaplatené platby", html)
        self.assertIn("Elektrina", html)
        self.assertIn("Reálne k dispozícii", html)

    def test_balance_debug_view_reports_orphan_events(self):
        pe.save_payment_events([
            {"payment_id": "missing", "cycle_key": self._cycle(), "state": "paid_me"}
        ])

        html = self.client.get("/debug/balance").data.decode()
        self.assertIn("Payment events bez existujúcej platby", html)
        self.assertIn("missing", html)


class ProblemsViewTests(AppViewsTestCase):
    def test_problems_view_shows_concrete_problem_and_solution(self):
        (web.SETTINGS).write_text(json.dumps({
            "account_balance": 100.0, "use_reserve": False, "safe_min": 0,
            "payday_day": 15, "real_balance": 100.0,
        }))

        html = self.client.get("/problems").data.decode()

        self.assertIn("Problémy a návrhy riešení", html)
        self.assertIn("Reálny odhad je v mínuse", html)
        self.assertIn("Návrh riešenia", html)
        self.assertIn("Otvoriť platby", html)

    def test_problems_view_reports_orphan_events_with_specific_id(self):
        pe.save_payment_events([
            {"payment_id": "missing", "cycle_key": self._cycle(), "state": "paid_me"}
        ])

        html = self.client.get("/problems").data.decode()

        self.assertIn("Stavy bez existujúcej platby", html)
        self.assertIn("missing", html)
        self.assertIn("payment_events.json", html)

    def test_problem_report_helper_returns_ok_when_clean(self):
        (web.SETTINGS).write_text(json.dumps({
            "account_balance": 1000.0,
            "real_balance": 1000.0,
            "last_manual_review": "2026-07-11T12:00:00",
        }))
        (web.PAYMENTS).write_text(json.dumps([]))
        (web.ENVELOPES).write_text(json.dumps([]))
        (web.ONETIME).write_text(json.dumps([]))
        pe.save_payment_events([])

        problems = web._build_problem_reports(web._debug_balance_context())

        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["severity"], "ok")


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


class PaymentPaidBalanceAdjustmentTests(AppViewsTestCase):
    def _settings(self):
        return json.loads(web.SETTINGS.read_text())

    def test_mark_paid_from_account_subtracts_payment_from_balance_once(self):
        payload = {"payment_id": "p1", "cycle_key": self._cycle(), "state": "paid_me"}

        self.client.post("/payment/state/by-id", data=payload)
        self.assertEqual(self._settings()["account_balance"], 920.0)
        self.assertEqual(self._settings()["real_balance"], 920.0)

        self.client.post("/payment/state/by-id", data=payload)
        self.assertEqual(self._settings()["account_balance"], 920.0)

    def test_payment_impact_preview_for_mark_paid(self):
        response = self.client.post("/api/payment-action-impact", data={
            "action_path": "/payment/state/0",
            "state": "paid_me",
        })
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        impact = payload["impact"]
        self.assertEqual(impact["before"]["current_balance"], 1000.0)
        self.assertEqual(impact["before"]["unpaid_payments_total"], 80.0)
        self.assertEqual(impact["after"]["current_balance"], 920.0)
        self.assertEqual(impact["after"]["unpaid_payments_total"], 0.0)
        self.assertEqual(impact["after"]["estimated_after_payments_and_envelopes"], 520.0)
        self.assertIn("Reálne k dispozícii: 520.00 € -> 520.00 €", payload["message"])

    def test_payment_impact_preview_for_paid_back_to_pending(self):
        cycle = self._cycle()
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })

        response = self.client.post("/api/payment-action-impact", data={
            "action_path": "/payment/state/0",
            "state": "pending",
        })
        impact = response.get_json()["impact"]
        self.assertEqual(impact["before"]["current_balance"], 920.0)
        self.assertEqual(impact["before"]["unpaid_payments_total"], 0.0)
        self.assertEqual(impact["after"]["current_balance"], 1000.0)
        self.assertEqual(impact["after"]["unpaid_payments_total"], 80.0)
        self.assertEqual(impact["after"]["estimated_after_payments_and_envelopes"], 520.0)

    def test_payment_impact_preview_for_delete_pending_payment(self):
        response = self.client.post("/api/payment-action-impact", data={
            "action_path": "/payment/delete/0",
        })
        impact = response.get_json()["impact"]
        self.assertEqual(impact["before"]["unpaid_payments_total"], 80.0)
        self.assertEqual(impact["after"]["current_balance"], 1000.0)
        self.assertEqual(impact["after"]["unpaid_payments_total"], 0.0)
        self.assertEqual(impact["after"]["estimated_after_payments_and_envelopes"], 600.0)

    def test_payment_delete_removes_stale_payment_events(self):
        cycle = self._cycle()
        pe.save_payment_events([
            {"payment_id": "p1", "cycle_key": cycle, "state": "pending"},
            {"payment_id": "other", "cycle_key": cycle, "state": "paid_me"},
        ])

        self.client.post("/payment/delete/0")

        events = pe.load_payment_events()
        self.assertIsNone(pe.get_payment_event(events, "p1", cycle))
        self.assertIsNotNone(pe.get_payment_event(events, "other", cycle))

    def test_mark_paid_keeps_real_estimate_stable(self):
        before = bfs.build_balance_first_summary()

        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": self._cycle(), "state": "paid_me",
        })

        after = bfs.build_balance_first_summary()
        self.assertEqual(before["estimated_after_payments"], 920.0)
        self.assertEqual(after["current_balance"], 920.0)
        self.assertEqual(after["unpaid_payments_total"], 0.0)
        self.assertEqual(after["estimated_after_payments"], 920.0)

    def test_legacy_paid_event_without_balance_marker_is_adjusted_once(self):
        cycle = self._cycle()
        pe.save_payment_events([
            {"payment_id": "p1", "cycle_key": cycle, "state": "paid_me"}
        ])
        payload = {"payment_id": "p1", "cycle_key": cycle, "state": "paid_me"}

        before = bfs.build_balance_first_summary()
        self.assertEqual(before["current_balance"], 1000.0)
        self.assertEqual(before["unsettled_paid_total"], 80.0)
        self.assertEqual(before["estimated_after_payments"], 920.0)

        self.client.post("/payment/state/by-id", data=payload)
        self.assertEqual(self._settings()["account_balance"], 920.0)
        after = bfs.build_balance_first_summary()
        self.assertEqual(after["unsettled_paid_total"], 0.0)
        self.assertEqual(after["estimated_after_payments"], 920.0)

        self.client.post("/payment/state/by-id", data=payload)
        self.assertEqual(self._settings()["account_balance"], 920.0)

    def test_legacy_paid_event_shows_balance_settle_action_until_adjusted(self):
        cycle = self._cycle()
        pe.save_payment_events([
            {"payment_id": "p1", "cycle_key": cycle, "state": "paid_me"}
        ])

        html = self.client.get("/payments").data.decode()
        self.assertIn("Zúčtovať v zostatku", html)

        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })
        html = self.client.get("/payments").data.decode()
        self.assertNotIn("Zúčtovať v zostatku", html)

    def test_paid_to_pending_restores_account_but_keeps_real_estimate_stable(self):
        cycle = self._cycle()
        before = bfs.build_balance_first_summary()
        self.assertEqual(before["current_balance"], 1000.0)
        self.assertEqual(before["unpaid_payments_total"], 80.0)
        self.assertEqual(before["estimated_after_payments"], 920.0)

        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })
        paid = bfs.build_balance_first_summary()
        self.assertEqual(paid["current_balance"], 920.0)
        self.assertEqual(paid["unpaid_payments_total"], 0.0)
        self.assertEqual(paid["estimated_after_payments"], 920.0)

        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "pending",
        })

        pending = bfs.build_balance_first_summary()
        self.assertEqual(self._settings()["account_balance"], 1000.0)
        self.assertEqual(pending["unpaid_payments_total"], 80.0)
        self.assertEqual(pending["estimated_after_payments"], 920.0)
        event = pe.get_payment_event(pe.load_payment_events(), "p1", cycle)
        self.assertEqual(event["state"], "pending")
        self.assertNotIn("main_balance_adjusted", event)

    def test_delete_pending_payment_after_paid_undo_releases_holdback(self):
        cycle = self._cycle()
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "pending",
        })
        self.client.post("/payment/delete/0")

        result = bfs.build_balance_first_summary()
        self.assertEqual(result["current_balance"], 1000.0)
        self.assertEqual(result["unpaid_payments_total"], 0.0)
        self.assertEqual(result["estimated_after_payments"], 1000.0)

    def test_delete_paid_adjusted_payment_keeps_spent_money_out_of_balance(self):
        cycle = self._cycle()
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })
        self.client.post("/payment/delete/0")

        result = bfs.build_balance_first_summary()
        self.assertEqual(result["current_balance"], 920.0)
        self.assertEqual(result["unpaid_payments_total"], 0.0)
        self.assertEqual(result["estimated_after_payments"], 920.0)

    def test_re_marking_previously_adjusted_payment_does_not_subtract_twice(self):
        cycle = self._cycle()
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "pending",
        })
        self.client.post("/payment/state/by-id", data={
            "payment_id": "p1", "cycle_key": cycle, "state": "paid_me",
        })

        self.assertEqual(self._settings()["account_balance"], 920.0)
        result = bfs.build_balance_first_summary()
        self.assertEqual(result["estimated_after_payments"], 920.0)


class DeferredViewTabSplitTests(AppViewsTestCase):
    """The /deferred view's Po termíne/Čoskoro/Neskôr tabs (visual redesign)
    split the same deferred list three ways by days_left -- this must never
    change what counts as deferred, only how it's grouped for display."""

    def test_deferred_to_date_already_passed_is_carried_over_not_left_in_deferred(self):
        # docs/balance_first_rules.md: once deferred_to's month is the
        # current cycle's month or earlier, resolve_deferred_carryovers()
        # promotes the item out of "deferred" into that cycle's unpaid list
        # -- so it must never still show up on the /deferred tabs, only on
        # /payments (as an overdue carryover).
        events = pe.load_payment_events()
        events = pe.defer_payment_to_date(events, "p1", "2026-06", date(2026, 6, 1))
        pe.save_payment_events(events)

        deferred_html = self.client.get("/deferred").data.decode()
        self.assertNotIn("Elektrina", deferred_html)

        payments_html = self.client.get("/payments").data.decode()
        inbox = payments_html.split('id="payment-inbox"')[1].split('id="zaplatene"')[0]
        self.assertIn("Elektrina", inbox)
        self.assertIn("po splatnosti", inbox)

    def test_far_future_deferred_item_appears_under_neskor(self):
        events = pe.load_payment_events()
        events = pe.defer_payment_to_date(events, "p1", "2026-07", date(2026, 12, 1))
        pe.save_payment_events(events)

        html = self.client.get("/deferred").data.decode()
        neskor = html.split('id="d-neskor"')[1]
        po_terminie = html.split('id="d-po-terminie"')[1].split('id="d-coskoro"')[0]
        self.assertIn("Elektrina", neskor)
        self.assertNotIn("Elektrina", po_terminie)


class ReceiptImageRouteTests(AppViewsTestCase):
    def test_valid_receipt_id_serves_the_image_bytes(self):
        (web.RECEIPTS_DIR / "abc123abc123.jpg").write_bytes(b"fake-jpeg-bytes")
        response = self.client.get("/receipt/image/abc123abc123")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"fake-jpeg-bytes")
        finally:
            response.close()

    def test_missing_receipt_id_returns_404(self):
        response = self.client.get("/receipt/image/doesnotexist1")
        self.assertEqual(response.status_code, 404)

    def test_receipt_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/receipt/upload",
            data={"image": (BytesIO(b"not-an-image"), "receipt.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_hex_receipt_id_is_rejected_before_touching_disk(self):
        response = self.client.get("/receipt/image/..%2f..%2fetc%2fpasswd")
        self.assertEqual(response.status_code, 404)


class HistoryTimelineGroupingTests(AppViewsTestCase):
    def test_history_groups_entries_by_day_newest_day_first(self):
        (web.AUDIT_LOG_PATH).write_text(json.dumps([
            {"at": "2026-07-08T10:00:00", "action": "balance_updated", "detail": "a"},
            {"at": "2026-07-10T09:00:00", "action": "balance_updated", "detail": "b"},
            {"at": "2026-07-10T14:30:00", "action": "payment_paid", "detail": "c"},
        ]))
        html = self.client.get("/history").data.decode()
        self.assertLess(html.index("2026-07-10"), html.index("2026-07-08"))


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
