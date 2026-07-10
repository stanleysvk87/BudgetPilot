#!/usr/bin/env python3
"""Editable monthly envelopes for BudgetPilot."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from flask import jsonify, redirect, request


BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
ENVELOPES = DATA / "envelopes.json"


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        envelopes = _read_json(ENVELOPES, [])
        if not isinstance(envelopes, list):
            envelopes = []

        normalized = [_normalize(e) for e in envelopes if isinstance(e, dict) and e.get("active", True) is not False]
        _write_json(ENVELOPES, normalized)

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

        return redirect(request.referrer or "/?v=envelopes-updated")
