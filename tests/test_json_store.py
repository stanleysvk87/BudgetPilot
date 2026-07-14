#!/usr/bin/env python3
"""Tests for the shared JSON persistence helpers in json_store.py.

Run directly: python3 tests/test_json_store.py
Or with unittest: python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json_store


class ReadJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data = Path(self.tmpdir.name)

    def test_missing_file_returns_default_silently(self):
        path = self.data / "nope.json"
        self.assertEqual(json_store.read_json(path, []), [])
        self.assertEqual(json_store.read_json(path, {"a": 1}), {"a": 1})

    def test_valid_file_is_parsed(self):
        path = self.data / "ok.json"
        path.write_text(json.dumps([{"id": "p1", "amount": 5}]))
        self.assertEqual(json_store.read_json(path, []), [{"id": "p1", "amount": 5}])

    def test_corrupt_file_logs_and_returns_default_instead_of_raising(self):
        path = self.data / "broken.json"
        path.write_text("{not valid json at all")
        with self.assertLogs("json_store", level="ERROR") as logs:
            result = json_store.read_json(path, [])
        self.assertEqual(result, [])
        self.assertIn("broken.json", logs.output[0])

    def test_empty_file_is_treated_as_corrupt_not_a_crash(self):
        path = self.data / "empty.json"
        path.write_text("")
        with self.assertLogs("json_store", level="ERROR"):
            result = json_store.read_json(path, {"default": True})
        self.assertEqual(result, {"default": True})


class AtomicWriteJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data = Path(self.tmpdir.name)

    def test_write_then_read_round_trips(self):
        path = self.data / "out.json"
        json_store.atomic_write_json(path, {"balance": 12.5})
        self.assertEqual(json.loads(path.read_text()), {"balance": 12.5})

    def test_creates_missing_parent_directories(self):
        path = self.data / "nested" / "dir" / "out.json"
        json_store.atomic_write_json(path, [1, 2, 3])
        self.assertEqual(json.loads(path.read_text()), [1, 2, 3])

    def test_overwrite_replaces_previous_content(self):
        path = self.data / "out.json"
        json_store.atomic_write_json(path, {"n": 1})
        json_store.atomic_write_json(path, {"n": 2})
        self.assertEqual(json.loads(path.read_text()), {"n": 2})

    def test_no_leftover_temp_files_after_a_successful_write(self):
        path = self.data / "out.json"
        json_store.atomic_write_json(path, {"ok": True})
        leftovers = [p for p in self.data.iterdir() if p.name != "out.json"]
        self.assertEqual(leftovers, [])

    def test_output_ends_with_a_trailing_newline(self):
        path = self.data / "out.json"
        json_store.atomic_write_json(path, {"n": 1})
        self.assertTrue(path.read_text().endswith("\n"))


if __name__ == "__main__":
    unittest.main()
