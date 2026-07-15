#!/usr/bin/env python3
"""Regression tests for the production-data safety net in paths.py.

Context: real household payments/payment_events data was lost in July
2026 because something touched the live data/ directory instead of an
isolated one. paths.guard_against_production_dir() (wired into every
json_store.read_json()/atomic_write_json() call) exists to make that
class of bug impossible to reintroduce silently -- these tests pin that
behavior down, including for scripts that don't import unittest/pytest
(migration/diagnostic one-offs), which is why some cases run in a real
subprocess rather than in-process.

None of these tests perform I/O against the real production data
directory: guard_against_production_dir() never touches the filesystem
(it only resolves the path), and every wiring test either uses a mocked
guard with a harmless tmp path, or runs entirely inside an isolated
directory.

Run directly: python3 tests/test_production_data_guard.py
Or with unittest: python3 -m unittest discover -s tests
"""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json_store
import paths


class GuardDetectsProductionPathTests(unittest.TestCase):
    """Pure checks against guard_against_production_dir() itself -- no
    filesystem I/O happens here, the function only resolves paths."""

    def test_raises_for_the_production_data_dir_itself(self):
        with self.assertRaises(paths.ProductionDataGuardError):
            paths.guard_against_production_dir(paths.PRODUCTION_DATA_DIR)

    def test_raises_for_a_file_inside_the_production_data_dir(self):
        with self.assertRaises(paths.ProductionDataGuardError):
            paths.guard_against_production_dir(paths.PRODUCTION_DATA_DIR / "settings.json")

    def test_raises_for_a_nested_path_inside_the_production_data_dir(self):
        with self.assertRaises(paths.ProductionDataGuardError):
            paths.guard_against_production_dir(
                paths.PRODUCTION_DATA_DIR / "receipts" / "photo.jpg"
            )

    def test_does_not_raise_for_an_isolated_tmp_path(self):
        with paths.isolated_runtime_dir() as tmp:
            paths.guard_against_production_dir(tmp / "settings.json")  # must not raise

    def test_does_not_raise_for_an_unrelated_sibling_directory(self):
        # A directory that merely starts with the same prefix (e.g.
        # ~/BudgetPilot-old/data) must not be treated as the production dir.
        sibling = paths.PRODUCTION_BASE_DIR.parent / (paths.PRODUCTION_BASE_DIR.name + "-old") / "data"
        paths.guard_against_production_dir(sibling)  # must not raise

    def test_inactive_outside_test_mode(self):
        # In-process this is unreachable (unittest is always loaded while
        # this test itself runs), so exercise it directly against the
        # detection function instead of the OS-process-level behavior,
        # which is covered by the subprocess tests below.
        with mock.patch.object(paths, "_test_mode_active", return_value=False):
            paths.guard_against_production_dir(paths.PRODUCTION_DATA_DIR)  # must not raise


class JsonStoreCallsTheGuardTests(unittest.TestCase):
    """Confirm read_json()/atomic_write_json() consult the guard before
    doing anything else, using a mocked guard and a harmless tmp path so
    no real file (production or otherwise) is ever at risk here."""

    def setUp(self):
        self.tmp_ctx = paths.isolated_runtime_dir()
        self.tmp = self.tmp_ctx.__enter__()
        self.addCleanup(self.tmp_ctx.__exit__, None, None, None)

    def test_read_json_consults_the_guard_first(self):
        harmless = self.tmp / "settings.json"
        with mock.patch.object(
            json_store.paths, "guard_against_production_dir",
            side_effect=paths.ProductionDataGuardError("blocked"),
        ) as guard:
            with self.assertRaises(paths.ProductionDataGuardError):
                json_store.read_json(harmless, {})
        guard.assert_called_once_with(harmless)

    def test_atomic_write_json_consults_the_guard_first(self):
        harmless = self.tmp / "settings.json"
        with mock.patch.object(
            json_store.paths, "guard_against_production_dir",
            side_effect=paths.ProductionDataGuardError("blocked"),
        ) as guard:
            with self.assertRaises(paths.ProductionDataGuardError):
                json_store.atomic_write_json(harmless, {"n": 1})
        guard.assert_called_once_with(harmless)
        # The guard fired before any write -- nothing should exist on disk.
        self.assertFalse(harmless.exists())

    def test_normal_reads_and_writes_still_work_inside_an_isolated_dir(self):
        path = self.tmp / "settings.json"
        json_store.atomic_write_json(path, {"n": 1})
        self.assertEqual(json_store.read_json(path, {}), {"n": 1})


class IsolatedRuntimeDirTests(unittest.TestCase):
    def test_points_app_base_and_data_dir_at_the_temp_directory(self):
        with paths.isolated_runtime_dir() as tmp:
            self.assertEqual(paths.app_base(), tmp)
            self.assertEqual(paths.data_dir(), tmp / "data")

    def test_environment_is_restored_after_the_context_exits(self):
        import os
        home_before = os.environ.get("BUDGETPILOT_HOME")
        mode_before = os.environ.get(paths.TEST_MODE_ENV_VAR)
        with paths.isolated_runtime_dir():
            pass
        self.assertEqual(os.environ.get("BUDGETPILOT_HOME"), home_before)
        self.assertEqual(os.environ.get(paths.TEST_MODE_ENV_VAR), mode_before)

    def test_environment_is_restored_even_if_the_body_raises(self):
        import os
        home_before = os.environ.get("BUDGETPILOT_HOME")
        with self.assertRaises(ValueError):
            with paths.isolated_runtime_dir():
                raise ValueError("boom")
        self.assertEqual(os.environ.get("BUDGETPILOT_HOME"), home_before)


class LoadDemoDataScriptRespectsTheGuardTests(unittest.TestCase):
    """scripts/load_demo_data.py writes with shutil, bypassing json_store,
    so it carries its own explicit guard_against_production_dir() call --
    make sure that's actually wired up and that the script still works
    normally inside an isolated directory."""

    def test_demo_loader_writes_into_the_isolated_dir_not_production(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import load_demo_data
        with paths.isolated_runtime_dir() as tmp:
            rc = load_demo_data.main()
            self.assertEqual(rc, 0)
            self.assertTrue((tmp / "data" / "settings.json").exists())

    def test_demo_loader_calls_the_guard(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import load_demo_data
        with paths.isolated_runtime_dir() as tmp:
            with mock.patch.object(
                load_demo_data, "guard_against_production_dir",
                side_effect=paths.ProductionDataGuardError("blocked"),
            ) as guard:
                with self.assertRaises(paths.ProductionDataGuardError):
                    load_demo_data.main()
            guard.assert_called_once_with(tmp / "data")


def _run_subprocess_snippet(snippet, env_overrides=None):
    import os
    env = dict(os.environ)
    env.pop(paths.TEST_MODE_ENV_VAR, None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class BareScriptWithoutUnittestOrPytestTests(unittest.TestCase):
    """The in-process tests above all run under unittest, which alone
    activates the guard. A one-off migration/diagnostic script imports
    neither unittest nor pytest, so its protection comes only from
    BUDGETPILOT_TEST_MODE -- verify that in a real subprocess where
    unittest genuinely isn't loaded."""

    def test_bare_script_without_test_mode_is_not_blocked(self):
        # This mirrors how the real server runs: no test markers, so the
        # guard must be transparent. Only checks the guard function itself
        # (no I/O), so it's safe even though it targets the real prod path.
        result = _run_subprocess_snippet(
            "import sys; sys.path.insert(0, '.'); import paths; "
            "assert 'unittest' not in sys.modules and 'pytest' not in sys.modules; "
            "paths.guard_against_production_dir(paths.PRODUCTION_DATA_DIR / 'settings.json'); "
            "print('NOT-BLOCKED')"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NOT-BLOCKED", result.stdout)

    def test_bare_script_with_test_mode_env_var_is_blocked(self):
        result = _run_subprocess_snippet(
            "import sys; sys.path.insert(0, '.'); import paths; "
            "assert 'unittest' not in sys.modules and 'pytest' not in sys.modules; "
            "paths.guard_against_production_dir(paths.PRODUCTION_DATA_DIR / 'settings.json')",
            env_overrides={paths.TEST_MODE_ENV_VAR: "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ProductionDataGuardError", result.stderr)

    def test_bare_script_using_isolated_runtime_dir_can_write_freely(self):
        result = _run_subprocess_snippet(
            "import sys; sys.path.insert(0, '.'); import paths, json_store; "
            "assert 'unittest' not in sys.modules and 'pytest' not in sys.modules; "
            "\nwith paths.isolated_runtime_dir() as tmp:\n"
            "    json_store.atomic_write_json(tmp / 'probe.json', {'ok': True})\n"
            "    assert json_store.read_json(tmp / 'probe.json', {}) == {'ok': True}\n"
            "print('ISOLATED-WRITE-OK')"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ISOLATED-WRITE-OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
