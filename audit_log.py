#!/usr/bin/env python3
"""Minimal audit/history log — a plain JSON list of user-visible actions
(balance updated, payment marked paid, payment deferred, envelope amount
changed, OCR expense saved, manual expense added).

Deliberately simple: nothing here feeds the forecast/balance calculation,
it's purely a human-readable trail for the "Audit/history" dashboard
section. No file I/O helpers beyond load/append — same pattern as
payment_events.py's load/save, just for a log instead of state.
"""
from datetime import datetime

import json_store

MAX_ENTRIES = 200


def load_audit_log(path):
    return json_store.read_json(path, [])


def log_action(path, action, detail="", now=None):
    """Append one entry and persist, keeping only the most recent
    MAX_ENTRIES so the file doesn't grow without bound."""
    entries = load_audit_log(path)
    entries.append({
        "at": (now or datetime.now()).isoformat(timespec="seconds"),
        "action": action,
        "detail": detail,
    })
    entries = entries[-MAX_ENTRIES:]
    json_store.atomic_write_json(path, entries)
    return entries
