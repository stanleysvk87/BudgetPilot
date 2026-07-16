#!/usr/bin/env python3
"""Authentication/access-control tests for BudgetPilot's single-admin mode."""
import concurrent.futures
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import budgetpilot as bp
import budgetpilot_web as web
import balance_first_summary as bfs
import payment_events as pe
from werkzeug.security import check_password_hash


TOKEN_INPUT_RE = re.compile(r'name="csrf_token" value="([0-9a-f]+)"')


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        (self.data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0,
            "real_balance": 1000.0,
            "payday_day": 15,
            "use_reserve": False,
            "safe_min": 0,
        }))
        (self.data / "incomes.json").write_text(json.dumps([]))
        (self.data / "payments.json").write_text(json.dumps([
            {"id": "p1", "name": "Elektrina", "amount": 80.0, "day": 5, "due_day": 5,
             "frequency": "monthly", "start_month": "2026-01", "active": True},
        ]))
        (self.data / "payment_events.json").write_text(json.dumps([]))
        (self.data / "expenses.json").write_text(json.dumps([]))
        (self.data / "debts.json").write_text(json.dumps([]))
        (self.data / "onetime.json").write_text(json.dumps([]))
        (self.data / "envelopes.json").write_text(json.dumps([]))
        (self.data / "audit_log.json").write_text(json.dumps([]))
        (self.data / "receipts").mkdir(exist_ok=True)

        patches = [
            mock.patch.object(web, "BASE", self.data),
            mock.patch.object(web, "DATA", self.data),
            mock.patch.object(web, "SETTINGS", self.data / "settings.json"),
            mock.patch.object(web, "INCOMES", self.data / "incomes.json"),
            mock.patch.object(web, "PAYMENTS", self.data / "payments.json"),
            mock.patch.object(web, "EXPENSES", self.data / "expenses.json"),
            mock.patch.object(web, "DEBTS", self.data / "debts.json"),
            mock.patch.object(web, "ONETIME", self.data / "onetime.json"),
            mock.patch.object(web, "ENVELOPES", self.data / "envelopes.json"),
            mock.patch.object(web, "AUDIT_LOG_PATH", self.data / "audit_log.json"),
            mock.patch.object(web, "LOGIN_LOCKOUT_PATH", self.data / "login_lockout.json"),
            mock.patch.object(web, "RECEIPTS_DIR", self.data / "receipts"),
            mock.patch.object(pe, "PAYMENT_EVENTS", self.data / "payment_events.json"),
            mock.patch.object(bfs, "DATA", self.data),
            mock.patch.object(web, "run_core", return_value=""),
            mock.patch.object(bp, "SETTINGS", self.data / "settings.json"),
            mock.patch.object(bp, "INCOMES", self.data / "incomes.json"),
            mock.patch.object(bp, "PAYMENTS", self.data / "payments.json"),
            mock.patch.object(bp, "EXPENSES", self.data / "expenses.json"),
            mock.patch.object(bp, "DEBTS", self.data / "debts.json"),
            mock.patch.object(bp, "ONETIME", self.data / "onetime.json"),
            mock.patch.dict(web.os.environ, {
                "BUDGETPILOT_PASSWORD": "",
                "BUDGETPILOT_USER": "",
            }, clear=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        web.app.config["TESTING"] = True
        previous_auth_bypass = web.app.config.get("BUDGETPILOT_AUTH_BYPASS")
        web.app.config["BUDGETPILOT_AUTH_BYPASS"] = False
        self.addCleanup(web.app.config.__setitem__, "BUDGETPILOT_AUTH_BYPASS", previous_auth_bypass)
        self.client = web.app.test_client()

    def token_from(self, response):
        match = TOKEN_INPUT_RE.search(response.data.decode())
        self.assertIsNotNone(match)
        return match.group(1)

    def create_admin(self, username="admin", password="synthetic-passphrase"):
        response = self.client.get("/auth/setup")
        token = self.token_from(response)
        return self.client.post("/auth/setup", data={
            "username": username,
            "password": password,
            "password_confirm": password,
            "csrf_token": token,
        })

    def login(self, username="admin", password="synthetic-passphrase", next_url="/"):
        response = self.client.get(f"/login?next={next_url}")
        token = self.token_from(response)
        return self.client.post("/login", data={
            "username": username,
            "password": password,
            "next": next_url,
            "csrf_token": token,
        })


class AdminSetupTests(AuthTestCase):
    def test_first_run_administrator_creation_hashes_password_and_logs_in(self):
        response = self.create_admin()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        store = json.loads((self.data / "users.json").read_text())
        user = store["users"][0]
        self.assertEqual(user["username"], "admin")
        self.assertNotEqual(user["password_hash"], "synthetic-passphrase")
        self.assertIn(":", user["password_hash"])
        self.assertTrue(check_password_hash(user["password_hash"], "synthetic-passphrase"))

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_administrator_setup_is_prevented(self):
        self.create_admin()
        response = self.client.get("/auth/setup")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        store = json.loads((self.data / "users.json").read_text())
        self.assertEqual(len(store["users"]), 1)

    def test_setup_requires_matching_passwords(self):
        token = self.token_from(self.client.get("/auth/setup"))
        response = self.client.post("/auth/setup", data={
            "username": "admin",
            "password": "synthetic-passphrase",
            "password_confirm": "different-passphrase",
            "csrf_token": token,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.data / "users.json").exists())

    def test_session_secret_creation_is_worker_safe(self):
        secret_path = self.data / ".session_secret_key"
        with mock.patch.object(web, "SECRET_KEY_PATH", secret_path):
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                keys = list(executor.map(lambda _: web._load_or_create_secret_key(), range(24)))

        self.assertTrue(secret_path.exists())
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual(secret_path.read_text().strip(), keys[0])
        self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)


class LoginLogoutTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.create_admin()
        self.client.get("/logout")

    def test_protected_page_redirects_to_login(self):
        response = self.client.get("/payments")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_protected_api_endpoint_redirects_when_unauthenticated(self):
        response = self.client.get("/api/envelopes")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_unauthenticated_state_change_does_not_modify_data(self):
        response = self.client.post("/income/add", data={"name": "X", "amount": "10", "day": "1"})
        self.assertEqual(response.status_code, 302)
        incomes = json.loads((self.data / "incomes.json").read_text())
        self.assertEqual(incomes, [])

    def test_valid_login_preserves_requested_destination(self):
        response = self.login(next_url="/payments")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/payments")
        self.assertEqual(self.client.get("/payments").status_code, 200)

    def test_invalid_login_does_not_authenticate_or_reveal_user_existence(self):
        response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Neplatné prihlasovacie údaje", response.data.decode())
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_logout_invalidates_session(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)
        self.client.get("/logout")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_session_does_not_survive_admin_password_store_removal(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)
        (self.data / "users.json").write_text(json.dumps({"users": []}))
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/auth/setup")

    def test_login_rate_limit_after_repeated_failures(self):
        for _ in range(web.MAX_LOGIN_ATTEMPTS):
            self.login(password="wrong-password")
        response = self.login(password="synthetic-passphrase")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Príliš veľa neúspešných pokusov", response.data.decode())


if __name__ == "__main__":
    unittest.main()
