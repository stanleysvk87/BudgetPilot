#!/usr/bin/env python3
"""Minimal audit/history log — a plain JSON list of user-visible actions
(balance updated, payment marked paid, payment deferred, envelope amount
changed, OCR expense saved, manual expense added).

Deliberately simple: nothing here feeds the forecast/balance calculation,
it's purely a human-readable trail for the "Audit/history" dashboard
section. No file I/O helpers beyond load/append — same pattern as
payment_events.py's load/save, just for a log instead of state.
"""
import json
from datetime import datetime

MAX_ENTRIES = 200


def load_audit_log(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    return entries
