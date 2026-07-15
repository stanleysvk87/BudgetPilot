#!/usr/bin/env python3
"""Shared JSON persistence helpers.

Every module that reads or writes a data/*.json file should go through
read_json()/atomic_write_json() rather than rolling its own read/write --
before this module existed, budgetpilot_web.py, budgetpilot.py,
audit_log.py, payment_events.py, envelope_editor.py,
balance_first_summary.py, and first_run_wizard.py each had their own
near-identical (and, in several cases, non-atomic) copy of this logic.
Consolidating them here means every data file gets the same durability
guarantee on write and the same missing-vs-corrupt handling on read.
"""
import json
import logging
import os
import uuid
from pathlib import Path

import paths

_log = logging.getLogger(__name__)


def read_json(path, default):
    """Load JSON from `path`, distinguishing two very different cases a
    bare `except Exception: return default` used to conflate:

    - the file simply doesn't exist yet (first run, optional data file)
      -> silently return `default`; this is normal and expected.
    - the file exists but fails to parse (corruption, a partial write
      from a crash, hand-editing gone wrong) -> log an error (visible in
      the server log/journal) and return `default`, but never raise --
      a damaged data file must degrade the feature it belongs to, not
      crash the whole application.
    """
    paths.guard_against_production_dir(path)
    path = Path(path)
    if not path.exists():
        return default

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.error("could not read %s: %s -- using default instead", path, exc)
        return default

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _log.error("%s contains invalid JSON (%s) -- using default instead", path, exc)
        return default


def atomic_write_json(path, data):
    """Write `data` as JSON to `path` without ever leaving a partially
    written file behind: write to a sibling temp file, fsync it, then
    atomically replace `path`, and fsync the containing directory so the
    rename itself survives a crash/power loss, not just the file bytes.
    """
    paths.guard_against_production_dir(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()
