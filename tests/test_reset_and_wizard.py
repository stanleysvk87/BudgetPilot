#!/usr/bin/env python3
"""Tests for:
- the "Vymazat vsetko" full-reset action (settings_reset()) -- wrong
  confirmation code must no-op, correct code must back up everything
  before wiping and leave the app in a fresh-install state.
- the first-run wizard's payment frequency field (previously hardcoded
  to "monthly" regardless of what was selected).

Isolated via temp dirs for both data/ and backups/ (settings_reset()
writes to BASE / "backups", not just DATA, so BASE needs patching too
or tests would write real backup directories on disk).

Run directly: python3 tests/test_reset_and_wizard.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for csrf_test_support

import budgetpilot_web as web
import first_run_wizard as wiz
import audit_log
import csrf_test_support


class FullResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.data = self.base / "data"
        self.data.mkdir(parents=True)

        self.settings_path = self.data / "settings.json"
        self.payments_path = self.data / "payments.json"
        self.audit_path = self.data / "audit_log.json"
        self.receipts_dir = self.data / "receipts"
        self.receipts_dir.mkdir()

        self.settings_path.write_text(json.dumps({"account_balance": 555.0, "real_balance": 555.0}))
        self.payments_path.write_text(json.dumps([{"id": "p1", "name": "Elektrina", "amount": 80.0}]))
        self.audit_path.write_text(json.dumps([{"at": "x", "action": "balance_updated", "detail": "555"}]))
        (self.receipts_dir / "abc123.jpg").write_bytes(b"fake-photo-bytes")

        patches = [
            mock.patch.object(web, "BASE", self.base),
            mock.patch.object(web, "DATA", self.data),
            mock.patch.object(web, "SETTINGS", self.settings_path),
            mock.patch.object(web, "PAYMENTS", self.payments_path),
            mock.patch.object(web, "AUDIT_LOG_PATH", self.audit_path),
            mock.patch.object(web, "RECEIPTS_DIR", self.receipts_dir),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        web.app.config["TESTING"] = True
        previous_auth_bypass = web.app.config.get("BUDGETPILOT_AUTH_BYPASS")
        web.app.config["BUDGETPILOT_AUTH_BYPASS"] = True
        self.addCleanup(web.app.config.__setitem__, "BUDGETPILOT_AUTH_BYPASS", previous_auth_bypass)
        previous_client_class = csrf_test_support.install(web.app)
        self.addCleanup(setattr, web.app, "test_client_class", previous_client_class)
        self.client = web.app.test_client()

    def test_wrong_code_does_not_touch_any_data(self):
        response = self.client.post("/settings/reset", data={"confirm_code": "nope"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("reset_error", response.headers["Location"])
        settings = json.loads(self.settings_path.read_text())
        self.assertEqual(settings["account_balance"], 555.0)
        payments = json.loads(self.payments_path.read_text())
        self.assertEqual(len(payments), 1)
        self.assertFalse((self.base / "backups").exists())

    def test_correct_code_backs_up_before_wiping(self):
        self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE})

        backups = list((self.base / "backups").glob("*-full-reset"))
        self.assertEqual(len(backups), 1)
        backed_up_settings = json.loads((backups[0] / "data" / "settings.json").read_text())
        self.assertEqual(backed_up_settings["account_balance"], 555.0)
        backed_up_photo = backups[0] / "data" / "receipts" / "abc123.jpg"
        self.assertTrue(backed_up_photo.exists())
        self.assertEqual(backed_up_photo.read_bytes(), b"fake-photo-bytes")

    def test_correct_code_is_case_insensitive(self):
        response = self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE.lower()})
        self.assertEqual(json.loads(self.settings_path.read_text()), {})

    def test_correct_code_wipes_settings_and_payments(self):
        self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE})
        self.assertEqual(json.loads(self.settings_path.read_text()), {})
        self.assertEqual(json.loads(self.payments_path.read_text()), [])

    def test_correct_code_clears_receipt_photos_from_live_dir(self):
        self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE})
        self.assertEqual(list(self.receipts_dir.iterdir()), [])

    def test_correct_code_leaves_a_full_reset_audit_trail(self):
        self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE})
        entries = audit_log.load_audit_log(self.audit_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "full_reset")
        self.assertIn("full-reset", entries[0]["detail"])

    def test_after_reset_first_run_wizard_is_triggered(self):
        self.client.post("/settings/reset", data={"confirm_code": web.RESET_CONFIRM_CODE})
        with mock.patch.object(wiz, "DATA", self.data):
            self.assertTrue(wiz._needs_first_run())

    def test_restore_requires_confirmation_code(self):
        backup = self.base / "backups" / "20260711-120000-full-reset" / "data"
        backup.mkdir(parents=True)
        (backup / "settings.json").write_text(json.dumps({"account_balance": 777.0}))
        (backup / "payments.json").write_text(json.dumps([]))

        response = self.client.post("/settings/restore", data={
            "backup_name": "20260711-120000-full-reset",
            "confirm_code": "nope",
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("restore_error=code", response.headers["Location"])
        self.assertEqual(json.loads(self.settings_path.read_text())["account_balance"], 555.0)

    def test_restore_backup_preserves_current_data_in_pre_restore_backup(self):
        backup = self.base / "backups" / "20260711-120000-full-reset" / "data"
        backup_receipts = backup / "receipts"
        backup_receipts.mkdir(parents=True)
        (backup / "settings.json").write_text(json.dumps({"account_balance": 777.0, "real_balance": 777.0}))
        (backup / "payments.json").write_text(json.dumps([{"id": "p2", "name": "Internet", "amount": 20.0}]))
        (backup / "audit_log.json").write_text(json.dumps([]))
        (backup_receipts / "restored.jpg").write_bytes(b"restored-photo")

        response = self.client.post("/settings/restore", data={
            "backup_name": "20260711-120000-full-reset",
            "confirm_code": web.RESET_CONFIRM_CODE,
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("restored=20260711-120000-full-reset", response.headers["Location"])
        self.assertEqual(json.loads(self.settings_path.read_text())["account_balance"], 777.0)
        self.assertEqual(json.loads(self.payments_path.read_text())[0]["id"], "p2")
        self.assertTrue((self.receipts_dir / "restored.jpg").exists())

        pre_restore_backups = list((self.base / "backups").glob("*-pre-restore*"))
        self.assertEqual(len(pre_restore_backups), 1)
        preserved_settings = json.loads((pre_restore_backups[0] / "data" / "settings.json").read_text())
        self.assertEqual(preserved_settings["account_balance"], 555.0)

        entries = audit_log.load_audit_log(self.audit_path)
        self.assertEqual(entries[-1]["action"], "backup_restored")
        self.assertIn("20260711-120000-full-reset", entries[-1]["detail"])


class WizardFrequencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        patches = [mock.patch.object(wiz, "DATA", self.data)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _submit(self, form):
        from flask import Flask
        app = Flask(__name__)
        wiz.register_first_run_wizard(app)
        client = app.test_client()
        base_form = {"account_balance": "1000", "reserve_amount": "0"}
        base_form.update(form)
        return client.post("/setup/full", data=base_form)

    def test_quarterly_frequency_is_saved_not_hardcoded_monthly(self):
        self._submit({
            "pay_name_1": "Poistka", "pay_amount_1": "120", "pay_day_1": "10",
            "pay_frequency_1": "quarterly",
        })
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["frequency"], "quarterly")

    def test_yearly_frequency_is_saved(self):
        self._submit({
            "pay_name_1": "Dialnicna znamka", "pay_amount_1": "60", "pay_day_1": "1",
            "pay_frequency_1": "yearly",
        })
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["frequency"], "yearly")

    def test_custom_months_saves_every_months(self):
        self._submit({
            "pay_name_1": "STK", "pay_amount_1": "50", "pay_day_1": "5",
            "pay_frequency_1": "custom_months", "pay_every_months_1": "24",
        })
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["frequency"], "custom_months")
        self.assertEqual(payments[0]["every_months"], 24)

    def test_start_month_is_taken_from_form_not_always_current_month(self):
        self._submit({
            "pay_name_1": "Poistka", "pay_amount_1": "120", "pay_day_1": "10",
            "pay_frequency_1": "quarterly", "pay_month_1": "3",
        })
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["start"][5:7], "03")

    def test_default_frequency_still_monthly_when_not_selected(self):
        self._submit({"pay_name_1": "Internet", "pay_amount_1": "20", "pay_day_1": "15"})
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["frequency"], "monthly")

    def test_invalid_frequency_falls_back_to_monthly(self):
        self._submit({
            "pay_name_1": "Internet", "pay_amount_1": "20", "pay_day_1": "15",
            "pay_frequency_1": "not-a-real-frequency",
        })
        payments = json.loads((self.data / "payments.json").read_text())
        self.assertEqual(payments[0]["frequency"], "monthly")


if __name__ == "__main__":
    unittest.main()
