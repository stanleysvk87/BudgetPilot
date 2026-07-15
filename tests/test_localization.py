#!/usr/bin/env python3
"""Localization tests for BudgetPilot's Slovak/English UI."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import balance_first_summary as bfs
import budgetpilot as bp
import budgetpilot_web as web
import i18n
import payment_events as pe
import csrf_test_support


class CatalogTests(unittest.TestCase):
    def test_english_catalog_has_every_slovak_key(self):
        self.assertEqual(i18n.missing_keys("en"), [])

    def test_missing_translation_falls_back_to_source_text(self):
        self.assertEqual(i18n.translate("Toto nie je v katalógu", "en"), "Toto nie je v katalógu")

    def test_language_code_is_normalized(self):
        self.assertEqual(i18n.normalize_language("en-US"), "en")
        self.assertEqual(i18n.normalize_language("xx"), "sk")


class LocalizedAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)
        (data / "settings.json").write_text(json.dumps({
            "account_balance": 1000.0,
            "real_balance": 1000.0,
            "payday_day": 15,
            "use_reserve": False,
            "safe_min": 0,
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
        (data / "envelopes.json").write_text(json.dumps([]))
        (data / "audit_log.json").write_text(json.dumps([]))
        (data / "receipts").mkdir(exist_ok=True)

        patches = [
            mock.patch.object(web, "BASE", data),
            mock.patch.object(web, "DATA", data),
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
            mock.patch.object(bp, "SETTINGS", data / "settings.json"),
            mock.patch.object(bp, "INCOMES", data / "incomes.json"),
            mock.patch.object(bp, "PAYMENTS", data / "payments.json"),
            mock.patch.object(bp, "EXPENSES", data / "expenses.json"),
            mock.patch.object(bp, "DEBTS", data / "debts.json"),
            mock.patch.object(bp, "ONETIME", data / "onetime.json"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        web.app.config["TESTING"] = True
        previous_auth_bypass = web.app.config.get("BUDGETPILOT_AUTH_BYPASS")
        web.app.config["BUDGETPILOT_AUTH_BYPASS"] = True
        self.addCleanup(web.app.config.__setitem__, "BUDGETPILOT_AUTH_BYPASS", previous_auth_bypass)
        previous_client_class = csrf_test_support.install(web.app)
        self.addCleanup(setattr, web.app, "test_client_class", previous_client_class)
        self.client = web.app.test_client()

    def test_language_switcher_persists_language_cookie(self):
        response = self.client.get("/language/en?next=/payments")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/payments")
        self.assertIn("budgetpilot_lang=en", response.headers.get("Set-Cookie", ""))

        html = self.client.get("/payments").data.decode()
        self.assertIn('<html lang="en">', html)
        self.assertIn("Payment management", html)
        self.assertIn("Actually available", html)

    def test_slovak_is_default_and_available(self):
        html = self.client.get("/payments").data.decode()
        self.assertIn('<html lang="sk">', html)
        self.assertIn("Správa platieb", html)
        self.assertIn("Reálne k dispozícii", html)

    def test_text_plain_auth_message_is_localized(self):
        with mock.patch.dict(web.os.environ, {"BUDGETPILOT_PASSWORD": "secret", "BUDGETPILOT_USER": "saldo"}):
            web.app.config["BUDGETPILOT_AUTH_BYPASS"] = False
            self.client.get("/language/en?next=/")
            response = self.client.get("/")
            self.assertEqual(response.status_code, 401)
            self.assertIn("Login is required.", response.data.decode())


if __name__ == "__main__":
    unittest.main()
