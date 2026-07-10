#!/usr/bin/env python3
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime
from pathlib import Path

from flask import jsonify, redirect, request


BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

PAID_STATES = {"paid", "paid_me", "paid_other", "paid_reserve"}
DEFERRED_STATE = "deferred"


def _read_json(name: str, default):
    path = DATA / name
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(name: str, value) -> None:
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _num(value, default=0.0) -> float:
    try:
        return float(str(value).replace("€", "").replace(" ", "").replace(",", ".").strip() or default)
    except Exception:
        return float(default)


def _norm(value: str) -> str:
    value = str(value or "").strip().lower()
    table = str.maketrans({
        "á": "a", "ä": "a", "č": "c", "ď": "d", "é": "e", "í": "i",
        "ľ": "l", "ĺ": "l", "ň": "n", "ó": "o", "ô": "o", "ŕ": "r",
        "š": "s", "ť": "t", "ú": "u", "ý": "y", "ž": "z",
    })
    value = value.translate(table)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _cycle() -> str:
    t = date.today()
    return f"{t.year:04d}-{t.month:02d}"


def _payment_id(item: dict) -> str:
    return str(item.get("payment_id") or item.get("obligation_id") or item.get("id") or "")


def _event_state(event: dict) -> str:
    return str(event.get("state") or event.get("status") or "").strip()


def _event_cycle(event: dict) -> str:
    return str(
        event.get("cycle_key")
        or event.get("cycle")
        or event.get("month")
        or event.get("start_month")
        or event.get("period")
        or ""
    ).strip()


def _event_applies(event: dict, cycle: str) -> bool:
    event_cycle = _event_cycle(event)
    return event_cycle in {"", cycle}


def _events_by_payment_id(events: list, cycle: str) -> dict:
    result = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if not _event_applies(event, cycle):
            continue
        pid = _payment_id(event)
        if pid:
            result[pid] = event
    return result


def _envelope_amount(e: dict) -> float:
    vals = []
    for key in ("monthly_budget", "budget", "amount", "monthly_limit", "limit"):
        if key in e:
            v = _num(e.get(key), 0)
            if v > 0:
                vals.append(v)
    return max(vals) if vals else 0.0


def _expense_amount(e: dict) -> float:
    for key in ("amount", "total", "price", "value", "suma"):
        if key in e:
            v = _num(e.get(key), 0)
            if v > 0:
                return v
    return 0.0


def _expense_text(e: dict) -> str:
    parts = []
    for key in ("category", "envelope", "name", "title", "merchant", "description", "note", "source"):
        if e.get(key):
            parts.append(str(e.get(key)))
    return _norm(" ".join(parts))


def _expense_month(e: dict) -> str:
    for key in ("date", "created_at", "timestamp", "paid_at"):
        value = str(e.get(key) or "").strip()
        if len(value) >= 7 and value[4] == "-":
            return value[:7]
    return _cycle()


def _expense_matches_envelope(expense: dict, envelope_name: str) -> bool:
    text = _expense_text(expense)
    env = _norm(envelope_name)

    if not text:
        return False

    if env and env in text:
        return True

    aliases = {
        "strava": ["strava", "potraviny", "jedlo", "food", "lidl", "kaufland", "tesco", "billa"],
        "nafta": ["nafta", "palivo", "fuel", "benzina", "slovnaft", "omv", "shell"],
    }

    for alias in aliases.get(env, []):
        if alias in text:
            return True

    return False


def _is_mandatory(p: dict) -> bool:
    priority = str(p.get("priority") or "mandatory").strip().lower()
    flexibility = str(p.get("flexibility") or "hard_due").strip().lower()
    return priority in {"mandatory", "important"} or flexibility == "hard_due"


def _due_date_for_current_month(p: dict) -> str:
    t = date.today()
    try:
        day = int(float(str(p.get("due_day", p.get("day", t.day))).strip()))
    except Exception:
        day = t.day

    last_day = calendar.monthrange(t.year, t.month)[1]
    day = max(1, min(last_day, day))
    return date(t.year, t.month, day).isoformat()


def build_balance_first_summary() -> dict:
    settings = _read_json("settings.json", {})
    payments = _read_json("payments.json", [])
    events = _read_json("payment_events.json", [])
    envelopes = _read_json("envelopes.json", [])
    expenses = _read_json("expenses.json", [])

    if not isinstance(settings, dict):
        settings = {}
    if not isinstance(payments, list):
        payments = []
    if not isinstance(events, list):
        events = []
    if not isinstance(envelopes, list):
        envelopes = []
    if not isinstance(expenses, list):
        expenses = []

    cycle = _cycle()
    today = date.today().isoformat()
    balance = _num(settings.get("account_balance", settings.get("real_balance", 0)), 0)

    event_by_pid = _events_by_payment_id(events, cycle)

    unpaid_total = 0.0
    mandatory_total = 0.0
    optional_total = 0.0
    deferred_total = 0.0
    overdue_count = 0
    unpaid_items = []
    deferred_items = []

    for p in payments:
        if not isinstance(p, dict):
            continue
        if p.get("active", True) is False:
            continue

        pid = _payment_id(p)
        amount = _num(p.get("amount"), 0)
        if amount <= 0:
            continue

        event = event_by_pid.get(pid)
        state = _event_state(event) if event else "pending"

        due_date = _due_date_for_current_month(p)
        mandatory = _is_mandatory(p)

        if state in PAID_STATES:
            continue

        if state == DEFERRED_STATE:
            deferred_total += amount
            deferred_items.append({
                "id": pid,
                "name": str(p.get("name") or "Platba"),
                "amount": round(amount, 2),
                "deferred_to": event.get("deferred_to") if isinstance(event, dict) else "",
                "mandatory": mandatory,
            })
            continue

        overdue = due_date < today
        unpaid_total += amount

        if mandatory:
            mandatory_total += amount
        else:
            optional_total += amount

        if overdue:
            overdue_count += 1

        unpaid_items.append({
            "id": pid,
            "name": str(p.get("name") or "Platba"),
            "amount": round(amount, 2),
            "due_date": due_date,
            "mandatory": mandatory,
            "overdue": overdue,
        })

    envelope_budget_total = 0.0
    envelope_spent_total = 0.0
    envelope_remaining_total = 0.0
    envelope_over_total = 0.0
    envelope_items = []

    current_expenses = [
        e for e in expenses
        if isinstance(e, dict) and _expense_month(e) == cycle and _expense_amount(e) > 0
    ]

    for env in envelopes:
        if not isinstance(env, dict):
            continue
        if env.get("active", True) is False:
            continue

        budget = _envelope_amount(env)
        if budget <= 0:
            continue

        name = str(env.get("name") or env.get("category") or "Obálka")
        spent = sum(
            _expense_amount(exp)
            for exp in current_expenses
            if _expense_matches_envelope(exp, name)
        )

        remaining = max(budget - spent, 0.0)
        over = max(spent - budget, 0.0)

        envelope_budget_total += budget
        envelope_spent_total += spent
        envelope_remaining_total += remaining
        envelope_over_total += over

        envelope_items.append({
            "id": str(env.get("id") or ""),
            "name": name,
            "amount": round(budget, 2),
            "budget": round(budget, 2),
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "over": round(over, 2),
        })

    # Balance-first: current balance is already real money after actual spending.
    # Therefore the dashboard subtracts unpaid payments and the REMAINING envelope budget,
    # not already-spent envelope money again.
    after_mandatory = balance - mandatory_total
    after_payments = balance - unpaid_total
    after_all = balance - unpaid_total - envelope_remaining_total

    return {
        "cycle": cycle,
        "today": today,
        "current_balance": round(balance, 2),

        "unpaid_payments_total": round(unpaid_total, 2),
        "unpaid_mandatory_total": round(mandatory_total, 2),
        "unpaid_optional_total": round(optional_total, 2),
        "unpaid_payment_count": len(unpaid_items),

        "deferred_payments_total": round(deferred_total, 2),
        "deferred_payment_count": len(deferred_items),
        "overdue_count": overdue_count,

        "envelopes_total": round(envelope_budget_total, 2),
        "envelopes_spent_total": round(envelope_spent_total, 2),
        "envelopes_remaining_total": round(envelope_remaining_total, 2),
        "envelopes_over_total": round(envelope_over_total, 2),
        "envelope_count": len(envelope_items),

        "estimated_after_mandatory": round(after_mandatory, 2),
        "estimated_after_payments": round(after_payments, 2),
        "estimated_after_payments_and_envelopes": round(after_all, 2),
        "missing_after_everything": round(abs(after_all), 2) if after_all < 0 else 0.0,

        "last_manual_review": settings.get("last_manual_review") or settings.get("setup_date") or "",
        "unpaid_payment_items": unpaid_items,
        "deferred_payment_items": deferred_items,
        "envelope_items": envelope_items,
    }


def register_balance_first_summary(app):
    @app.get("/api/balance-first-summary")
    def api_balance_first_summary():
        return jsonify(build_balance_first_summary())

    @app.post("/api/balance/update")
    def api_balance_update():
        settings = _read_json("settings.json", {})
        if not isinstance(settings, dict):
            settings = {}

        balance = _num(request.form.get("account_balance"), 0)
        now = datetime.now().isoformat(timespec="seconds")

        settings["account_balance"] = balance
        settings["real_balance"] = balance
        settings["last_manual_review"] = now
        settings["balance_first"] = True
        settings["income_required"] = False
        settings["manual_confirmation_required"] = True
        settings["data_profile"] = "real_runtime"

        _write_json("settings.json", settings)

        snapshots = _read_json("snapshots.json", [])
        if not isinstance(snapshots, list):
            snapshots = []

        snapshots.append({
            "date": date.today().isoformat(),
            "real_balance": balance,
            "reserve_amount": _num(settings.get("reserve_amount"), 0),
            "note": "manual_dashboard_balance_update",
            "created_at": now,
        })
        _write_json("snapshots.json", snapshots)

        return redirect(request.referrer or "/?v=balance-updated")
