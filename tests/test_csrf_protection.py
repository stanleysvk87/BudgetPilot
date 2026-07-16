#!/usr/bin/env python3
"""End-to-end regression tests for CSRF protection (budgetpilot_web.py's
require_csrf_token() before_request hook + the csrf_token() Jinja global).

Deliberately uses a plain, un-patched web.app.test_client() (NOT
csrf_test_support.CsrfAutoClient, which every other test file uses to
transparently attach a valid token so existing tests didn't need to
change) -- these tests exist specifically to prove the real mechanism
works: a page renders a real token, a POST without one is rejected with
a friendly error instead of a raw exception, a forged token is rejected,
and the exact token a real page rendered is accepted.

Run directly: python3 tests/test_csrf_protection.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budgetpilot as bp
import budgetpilot_web as web
import payment_events as pe
import balance_first_summary as bfs
from werkzeug.security import generate_password_hash

TOKEN_INPUT_RE = re.compile(r'name="csrf_token" value="([0-9a-f]+)"')


class CsrfProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)

        (data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0, "use_reserve": False, "safe_min": 0,
            "payday_day": 15, "real_balance": 1000.0,
        }))
        (data / "incomes.json").write_text(json.dumps([]))
        # first_run_wizard's before_request gate redirects every request to
        # /setup/full whenever payments.json is empty -- at least one
        # payment is needed so GET requests here actually render the real
        # page (and its csrf_token input) instead of a 302 to the wizard.
        (data / "payments.json").write_text(json.dumps([
            {"id": "p1", "name": "Elektrina", "amount": 80.0, "day": 5, "due_day": 5,
             "frequency": "monthly", "start_month": "2026-01", "active": True},
        ]))
        (data / "payment_events.json").write_text(json.dumps([]))
        (data / "expenses.json").write_text(json.dumps([]))
        (data / "debts.json").write_text(json.dumps([]))
        (data / "onetime.json").write_text(json.dumps([]))
        (data / "envelopes.json").write_text(json.dumps([]))
        (data / "audit_log.json").write_text(json.dumps([]))
        (data / "users.json").write_text(json.dumps({
            "users": [{
                "username": "admin",
                "password_hash": generate_password_hash("correct horse battery staple"),
                "created_at": "2026-07-15T12:00:00",
                "updated_at": "2026-07-15T12:00:00",
            }]
        }))
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
            mock.patch.object(web, "LOGIN_LOCKOUT_PATH", data / "login_lockout.json"),
            mock.patch.object(web, "RECEIPTS_DIR", data / "receipts"),
            mock.patch.object(pe, "PAYMENT_EVENTS", data / "payment_events.json"),
            mock.patch.object(bfs, "DATA", data),
            mock.patch.object(web, "run_core", return_value=""),
            # GET "/" -> render_page() -> three_month_forecast() calls
            # bp.calc_month() in-process, bypassing the run_core stub above --
            # see tests/test_production_data_guard.py.
            mock.patch.object(bp, "SETTINGS", data / "settings.json"),
            mock.patch.object(bp, "INCOMES", data / "incomes.json"),
            mock.patch.object(bp, "PAYMENTS", data / "payments.json"),
            mock.patch.object(bp, "EXPENSES", data / "expenses.json"),
            mock.patch.object(bp, "DEBTS", data / "debts.json"),
            mock.patch.object(bp, "ONETIME", data / "onetime.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        web.app.config["TESTING"] = True
        # No csrf_test_support.install() here on purpose -- a plain
        # FlaskClient exercises the real cookie/session/token round trip.
        self.client = web.app.test_client()
        with self.client.session_transaction() as sess:
            sess[web.AUTH_SESSION_KEY] = "admin"

    def _extract_token(self, html):
        match = TOKEN_INPUT_RE.search(html)
        self.assertIsNotNone(match, "page did not render a csrf_token hidden input")
        return match.group(1)

    def test_get_page_renders_a_real_csrf_token(self):
        html = self.client.get("/").data.decode()
        token = self._extract_token(html)
        self.assertGreaterEqual(len(token), 16)

    def test_get_requests_never_require_a_token(self):
        for path in ("/", "/payments", "/envelopes", "/expenses", "/manage", "/problems"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f"GET {path} should never need a CSRF token")

    def test_post_without_a_token_is_rejected_with_a_friendly_error(self):
        self.client.get("/")  # establishes a session
        response = self.client.post("/income/add", data={"name": "Vyplata", "amount": "2000", "day": "15"})
        self.assertEqual(response.status_code, 400)
        body = response.data.decode()
        self.assertIn("Bezpečnostná kontrola zlyhala", body)
        self.assertNotIn("Traceback", body)
        incomes = json.loads((Path(self.tmp.name) / "incomes.json").read_text())
        self.assertEqual(incomes, [])

    def test_post_with_a_forged_token_is_rejected(self):
        self.client.get("/")
        response = self.client.post("/income/add", data={
            "name": "Vyplata", "amount": "2000", "day": "15",
            "csrf_token": "0" * 32,
        })
        self.assertEqual(response.status_code, 400)

    def test_post_with_the_real_rendered_token_succeeds(self):
        html = self.client.get("/").data.decode()
        token = self._extract_token(html)
        response = self.client.post("/income/add", data={
            "name": "Vyplata", "amount": "2000", "day": "15",
            "csrf_token": token,
        })
        self.assertEqual(response.status_code, 302)
        incomes = json.loads((Path(self.tmp.name) / "incomes.json").read_text())
        self.assertEqual(len(incomes), 1)
        self.assertEqual(incomes[0]["name"], "Vyplata")

    def test_token_stays_valid_across_requests_in_the_same_session(self):
        html = self.client.get("/").data.decode()
        token = self._extract_token(html)

        r1 = self.client.post("/income/add", data={"name": "A", "amount": "10", "day": "1", "csrf_token": token})
        r2 = self.client.post("/income/add", data={"name": "B", "amount": "20", "day": "2", "csrf_token": token})
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        incomes = json.loads((Path(self.tmp.name) / "incomes.json").read_text())
        self.assertEqual(len(incomes), 2)

    def test_different_clients_get_different_tokens(self):
        token_a = self._extract_token(self.client.get("/").data.decode())
        other_client = web.app.test_client()
        with other_client.session_transaction() as sess:
            sess[web.AUTH_SESSION_KEY] = "admin"
        token_b = self._extract_token(other_client.get("/").data.decode())
        self.assertNotEqual(token_a, token_b)


if __name__ == "__main__":
    unittest.main()
