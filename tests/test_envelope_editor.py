#!/usr/bin/env python3
"""Tests for envelope_editor.py's /api/envelopes routes.

Previously untested (see the engineering review): GET /api/envelopes had
a destructive side effect -- it rewrote envelopes.json on every call and,
in doing so, permanently dropped any envelope with active=False. This
file exists specifically to close that coverage gap and pin the fix.

Run directly: python3 tests/test_envelope_editor.py
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
import envelope_editor
import csrf_test_support


class EnvelopeEditorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)
        self.envelopes_path = data / "envelopes.json"
        self.envelopes_path.write_text(json.dumps([
            {"id": "e1", "name": "Strava", "category": "Strava", "monthly_limit": 400.0, "active": True},
            {"id": "e2", "name": "Zábava", "category": "Zábava", "monthly_limit": 50.0, "active": False},
        ]))
        # first_run_wizard's before_request gate runs on every route (not
        # just "/") and reads web.SETTINGS/web.PAYMENTS -- unpatched, it
        # falls back to the real production data dir. See
        # tests/test_production_data_guard.py.
        settings_path = data / "settings.json"
        settings_path.write_text(json.dumps({"account_balance": 1000.0, "real_balance": 1000.0}))
        payments_path = data / "payments.json"
        payments_path.write_text(json.dumps([{"id": "p1", "name": "Elektrina", "amount": 80.0, "day": 5}]))

        patches = [
            mock.patch.object(envelope_editor, "ENVELOPES", self.envelopes_path),
            mock.patch.object(envelope_editor, "AUDIT_LOG_PATH", data / "audit_log.json"),
            mock.patch.object(web, "SETTINGS", settings_path),
            mock.patch.object(web, "PAYMENTS", payments_path),
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

    def _raw_envelopes_on_disk(self):
        return json.loads(self.envelopes_path.read_text())


class GetEnvelopesDoesNotMutateDiskTests(EnvelopeEditorTestCase):
    def test_get_does_not_change_the_file_on_disk_at_all(self):
        before = self.envelopes_path.read_text()
        response = self.client.get("/api/envelopes")
        self.assertEqual(response.status_code, 200)
        after = self.envelopes_path.read_text()
        self.assertEqual(before, after, "GET /api/envelopes must never modify persistent data")

    def test_inactive_envelope_survives_repeated_gets(self):
        for _ in range(3):
            self.client.get("/api/envelopes")
        raw = self._raw_envelopes_on_disk()
        self.assertEqual(len(raw), 2)
        self.assertTrue(any(e.get("id") == "e2" for e in raw))

    def test_response_still_excludes_inactive_envelopes(self):
        response = self.client.get("/api/envelopes")
        payload = response.get_json()
        ids = [e["id"] for e in payload["envelopes"]]
        self.assertEqual(ids, ["e1"])

    def test_response_normalizes_legacy_field_names(self):
        response = self.client.get("/api/envelopes")
        payload = response.get_json()
        self.assertEqual(len(payload["envelopes"]), 1)
        entry = payload["envelopes"][0]
        self.assertEqual(entry["id"], "e1")
        self.assertEqual(entry["name"], "Strava")
        self.assertEqual(entry["amount"], 400.0)
        self.assertTrue(entry["updated_at"])  # normalization always stamps this


class UpdateEnvelopeStillPersistsTests(EnvelopeEditorTestCase):
    def test_update_by_id_changes_amount_and_persists(self):
        response = self.client.post("/api/envelopes/update", data={"id": "e1", "name": "Strava", "amount": "500"})
        self.assertEqual(response.status_code, 302)
        raw = self._raw_envelopes_on_disk()
        updated = next(e for e in raw if e["id"] == "e1")
        self.assertEqual(updated["monthly_limit"], 500.0)

    def test_update_with_new_name_creates_a_new_envelope(self):
        self.client.post("/api/envelopes/update", data={"name": "Doprava", "amount": "80"})
        raw = self._raw_envelopes_on_disk()
        self.assertTrue(any(e.get("name") == "Doprava" and e.get("monthly_limit") == 80.0 for e in raw))


if __name__ == "__main__":
    unittest.main()
