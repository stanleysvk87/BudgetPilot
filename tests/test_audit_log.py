#!/usr/bin/env python3
"""Tests for audit_log.py — a simple JSON action trail.

Run directly: python3 tests/test_audit_log.py
Or with unittest: python3 -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_log import load_audit_log, log_action, MAX_ENTRIES


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "audit_log.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_missing_file_returns_empty_list(self):
        self.assertEqual(load_audit_log(self.path), [])

    def test_log_action_persists_entry(self):
        log_action(self.path, "balance_updated", "1000 -> 950", now=datetime(2026, 7, 10, 9, 0))
        entries = load_audit_log(self.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "balance_updated")
        self.assertEqual(entries[0]["detail"], "1000 -> 950")
        self.assertEqual(entries[0]["at"], "2026-07-10T09:00:00")

    def test_multiple_actions_append_in_order(self):
        log_action(self.path, "payment_paid", now=datetime(2026, 7, 10, 9, 0))
        log_action(self.path, "payment_deferred", now=datetime(2026, 7, 10, 9, 5))
        entries = load_audit_log(self.path)
        self.assertEqual([e["action"] for e in entries], ["payment_paid", "payment_deferred"])

    def test_log_is_capped_at_max_entries(self):
        for i in range(MAX_ENTRIES + 10):
            log_action(self.path, f"action_{i}")
        entries = load_audit_log(self.path)
        self.assertEqual(len(entries), MAX_ENTRIES)
        self.assertEqual(entries[-1]["action"], f"action_{MAX_ENTRIES + 9}")

    def test_corrupt_file_treated_as_empty(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("not json")
        self.assertEqual(load_audit_log(self.path), [])


if __name__ == "__main__":
    unittest.main()
