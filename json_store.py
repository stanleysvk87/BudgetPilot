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
import contextlib
import hashlib
import json
import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path

import paths

try:
    import fcntl
except ImportError:  # non-POSIX
    fcntl = None

_log = logging.getLogger(__name__)


# ---- Serializing read-modify-write sequences ----
#
# atomic_write_json() below makes a single write crash-safe, but it can't
# make "read balance -> subtract payment -> write balance" safe against a
# second request doing the same thing at the same time: both read 1000,
# both write 1000 - amount, and one subtraction is silently lost.
#
# Every deployment comment in this project justified skipping locks with
# "gunicorn runs --workers 1". That never actually covered this: Flask's
# own app.run() (documented in INSTALL.md/SECURITY.md, and what
# desktop_app.py uses) is threaded=True by default, and gunicorn's sync
# worker still interleaves nothing *between* processes but everything the
# dashboard's background fetch to /api/balance-first-summary does happens
# concurrently with form POSTs inside one process. So the guarantee has to
# come from here.
#
# Two layers, because both failure modes are real:
#   - a re-entrant thread lock, which is what actually fixes the default
#     single-process/threaded deployments;
#   - an flock() on a lock file, so raising BUDGETPILOT_WORKERS above 1
#     (or running the CLI next to the server) degrades to serialization
#     rather than to lost writes.
#
# The lock file lives in the OS temp dir, keyed by a hash of the data
# directory, so acquiring a lock never writes into data/ itself (which
# would trip paths.guard_against_production_dir() and litter backups).
_thread_lock = threading.RLock()
_lock_depth = threading.local()


def _lock_file_for(directory) -> Path:
    key = hashlib.sha256(str(Path(directory).resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"budgetpilot-data-{key}.lock"


@contextlib.contextmanager
def data_lock(directory=None):
    """Hold the data-directory write lock for the duration of the block.

    Re-entrant within a thread; blocks other threads and (where flock is
    available) other processes using the same data directory.
    """
    directory = Path(directory) if directory is not None else paths.data_dir()
    with _thread_lock:
        depth = getattr(_lock_depth, "value", 0)
        _lock_depth.value = depth + 1
        handle = None
        # Only the outermost acquisition takes the file lock: flock is
        # per-open-file-description, so a nested acquisition on a second
        # descriptor would deadlock against this same process.
        if depth == 0 and fcntl is not None:
            try:
                handle = _lock_file_for(directory).open("a+")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                _log.warning("could not take the data file lock: %s", exc)
                if handle is not None:
                    handle.close()
                handle = None
        try:
            yield
        finally:
            _lock_depth.value = depth
            if handle is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()


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
