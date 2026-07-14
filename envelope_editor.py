#!/usr/bin/env python3
"""Editable monthly envelopes for BudgetPilot."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from flask import jsonify, redirect, request

import audit_log
import json_store
from paths import app_base, data_dir

BASE = app_base()
DATA = data_dir()
ENVELOPES = DATA / "envelopes.json"
AUDIT_LOG_PATH = DATA / "audit_log.json"


def _read_json(path: Path, default):
    return json_store.read_json(path, default)


def _write_json(path: Path, value) -> None:
    json_store.atomic_write_json(path, value)


def _num(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", ".").strip() or default)
    except Exception:
        return float(default)


def _amount(envelope: dict) -> float:
    for key in ("monthly_budget", "budget", "amount", "monthly_limit", "limit"):
        if key in envelope:
            value = _num(envelope.get(key), 0)
            if value > 0:
                return value
    return 0.0


def _name(envelope: dict) -> str:
    return str(envelope.get("name") or envelope.get("category") or "Obálka").strip()


def _normalize(envelope: dict, amount: float | None = None) -> dict:
    if not isinstance(envelope, dict):
        envelope = {}

    if not envelope.get("id"):
        envelope["id"] = "envelope-" + uuid.uuid4().hex[:8]

    name = _name(envelope)
    if not name:
        name = "Obálka"

    if amount is None:
        amount = _amount(envelope)

    envelope["name"] = name
    envelope["category"] = envelope.get("category") or name
    envelope["amount"] = amount
    envelope["budget"] = amount
    envelope["monthly_budget"] = amount
    envelope["monthly_limit"] = amount
    envelope["limit"] = amount
    envelope["frequency"] = "monthly"
    envelope["type"] = "envelope"
    envelope["active"] = True
    envelope["updated_at"] = datetime.now().isoformat(timespec="seconds")

    return envelope


def register_envelope_editor(app):
    @app.get("/api/envelopes")
    def api_envelopes():
        # Read-only: normalizes the response shape (old-style records
        # missing id/name/amount aliases still render correctly) without
        # ever writing back to disk. A GET must never modify persistent
        # data -- this endpoint previously rewrote envelopes.json on
        # every call and, in doing so, permanently dropped any envelope
        # with active=False from the file, not just from the response.
        envelopes = _read_json(ENVELOPES, [])
        if not isinstance(envelopes, list):
            envelopes = []

        normalized = [
            _normalize(dict(e)) for e in envelopes
            if isinstance(e, dict) and e.get("active", True) is not False
        ]

        return jsonify({
            "envelopes": [
                {
                    "id": e.get("id"),
                    "name": _name(e),
                    "amount": _amount(e),
                    "updated_at": e.get("updated_at", ""),
                }
                for e in normalized
            ]
        })

    @app.post("/api/envelopes/update")
    def api_envelopes_update():
        envelopes = _read_json(ENVELOPES, [])
        if not isinstance(envelopes, list):
            envelopes = []

        envelope_id = str(request.form.get("id") or "").strip()
        name = str(request.form.get("name") or "").strip()
        amount = _num(request.form.get("amount"), 0)

        if amount < 0:
            amount = 0.0

        found = None
        for e in envelopes:
            if not isinstance(e, dict):
                continue

            same_id = envelope_id and str(e.get("id", "")) == envelope_id
            same_name = name and _name(e).lower() == name.lower()

            if same_id or same_name:
                found = e
                break

        if found is None:
            found = {
                "id": envelope_id or "envelope-" + uuid.uuid4().hex[:8],
                "name": name or "Nová obálka",
                "category": name or "Nová obálka",
            }
            envelopes.append(found)

        if name:
            found["name"] = name
            found["category"] = name

        _normalize(found, amount)

        _write_json(ENVELOPES, envelopes)

        audit_log.log_action(AUDIT_LOG_PATH, "envelope_amount_changed", f"{_name(found)} -> {amount:.2f} €")

        return redirect(request.referrer or "/?v=envelopes-updated")
