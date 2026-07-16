#!/usr/bin/env python3
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from flask import jsonify, redirect, request

import audit_log
import obligations as ob
import json_store
from paths import app_base, data_dir

BASE = app_base()
DATA = data_dir()
AUDIT_LOG_PATH = DATA / "audit_log.json"

PAID_STATES = {"paid", "paid_me", "paid_other", "paid_reserve"}
DEFERRED_STATE = "deferred"


def _read_json(name: str, default):
    return json_store.read_json(DATA / name, default)


def _write_json(name: str, value) -> None:
    json_store.atomic_write_json(DATA / name, value)


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


def _target_cycle(deferred_to: str) -> str:
    return str(deferred_to)[:7]


def _deferred_carryovers(payments: list, events: list, cycle: str) -> tuple:
    """Deferred-state events from ANY cycle, split by whether their
    deferred_to date now falls in `cycle`'s month or earlier (must show
    as an active unpaid item THIS cycle — never silently stay hidden as
    "deferred" once the date arrives/passes) or a still-future month
    (stays deferred). A carryover is always an item *in addition to*
    that same payment's own natural occurrence this cycle, never a
    replacement for it — see docs/balance_first_rules.md.
    """
    payments_by_id = {_payment_id(p): p for p in payments if isinstance(p, dict) and _payment_id(p)}
    unpaid_carryovers, deferred_carryovers = [], []

    for event in events:
        if not isinstance(event, dict):
            continue
        if _event_state(event) != DEFERRED_STATE:
            continue
        deferred_to = str(event.get("deferred_to") or "").strip()
        if len(deferred_to) < 7 or deferred_to[4] != "-":
            continue

        pid = _payment_id(event)
        template = payments_by_id.get(pid)
        if template is None:
            continue

        origin_cycle = _event_cycle(event) or cycle
        target_cycle = _target_cycle(deferred_to)
        amount = _num(template.get("amount"), 0)
        if amount <= 0:
            continue
        mandatory = _is_mandatory(template)
        name = str(template.get("name") or "Platba")
        if target_cycle <= cycle:
            name = name + (
                " — odložené z minulého obdobia" if origin_cycle == cycle
                else f" — odložené z {origin_cycle}"
            )
            unpaid_carryovers.append({
                "id": pid,
                "name": name,
                "amount": round(amount, 2),
                "due_date": deferred_to,
                "mandatory": mandatory,
                "overdue": deferred_to < date.today().isoformat(),
                "origin_cycle_key": origin_cycle,
            })
        else:
            deferred_carryovers.append({
                "id": pid,
                "name": name,
                "amount": round(amount, 2),
                "deferred_to": deferred_to,
                "mandatory": mandatory,
                "origin_cycle_key": origin_cycle,
            })

    return unpaid_carryovers, deferred_carryovers


def _due_date_for_current_month(p: dict) -> str:
    due_date = str(p.get("due_date") or "").strip()
    if len(due_date) >= 10 and due_date[4] == "-" and due_date[7] == "-":
        return due_date[:10]

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
    onetime = _read_json("onetime.json", [])
    events = _read_json("payment_events.json", [])
    envelopes = _read_json("envelopes.json", [])
    expenses = _read_json("expenses.json", [])

    if not isinstance(settings, dict):
        settings = {}
    if not isinstance(payments, list):
        payments = []
    if not isinstance(onetime, list):
        onetime = []
    if not isinstance(events, list):
        events = []
    if not isinstance(envelopes, list):
        envelopes = []
    if not isinstance(expenses, list):
        expenses = []

    cycle = _cycle()
    now = date.today()
    today = now.isoformat()
    balance = _num(settings.get("account_balance", settings.get("real_balance", 0)), 0)
    current_onetime = [
        p for p in onetime
        if isinstance(p, dict) and str(p.get("due_date") or "")[:7] == cycle
    ]
    # Recurring payments are only obligations THIS month if their own
    # frequency (monthly/quarterly/yearly/custom_months/once) actually
    # lands here -- ob.is_recurring_active() is the same canonical check
    # the web dashboard uses, so a yearly bill can no longer show up as
    # "unpaid" in a month it was never due (see obligations.py docstring).
    active_payments = [
        p for p in payments
        if isinstance(p, dict) and ob.is_recurring_active(p, now.year, now.month)
    ]
    payment_templates = active_payments + current_onetime

    event_by_pid = _events_by_payment_id(events, cycle)

    unpaid_total = 0.0
    mandatory_total = 0.0
    optional_total = 0.0
    unsettled_paid_total = 0.0
    deferred_total = 0.0
    overdue_count = 0
    unpaid_items = []
    unsettled_paid_items = []
    deferred_items = []

    for p in payment_templates:
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

        if state == "paid_me" and not bool(event and event.get("main_balance_adjusted")):
            unsettled_paid_total += amount
            unsettled_paid_items.append({
                "id": pid,
                "name": str(p.get("name") or "Platba"),
                "amount": round(amount, 2),
                "due_date": due_date,
            })
            continue

        if state in PAID_STATES:
            continue

        if state == DEFERRED_STATE:
            # Handled below by _deferred_carryovers(), which — unlike this
            # per-cycle-only lookup — knows whether the deferred_to date
            # has actually arrived and promotes it to unpaid when it has,
            # instead of leaving it parked under "deferred" forever.
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

    unpaid_carryovers, deferred_carryovers = _deferred_carryovers(payments + onetime, events, cycle)
    for item in unpaid_carryovers:
        unpaid_total += item["amount"]
        if item["mandatory"]:
            mandatory_total += item["amount"]
        else:
            optional_total += item["amount"]
        if item["overdue"]:
            overdue_count += 1
        unpaid_items.append(item)
    for item in deferred_carryovers:
        deferred_total += item["amount"]
        deferred_items.append(item)

    envelope_budget_total = 0.0
    envelope_spent_total = 0.0
    envelope_remaining_total = 0.0
    envelope_over_total = 0.0
    envelope_items = []

    current_expenses = [
        e for e in expenses
        if isinstance(e, dict) and _expense_month(e) == cycle and _expense_amount(e) > 0
    ]

    # Each expense counts toward at most one envelope: _expense_matches_envelope
    # is a substring/alias match, so a single expense's text (e.g. "nafta v
    # Kauflande") can satisfy more than one envelope's pattern. Summing every
    # matching envelope independently would count that expense's amount more
    # than once in envelope_spent_total/envelope_remaining_total below, which
    # feed directly into the dashboard's real-balance estimate. First envelope
    # (in list order) that matches claims the expense; later envelopes skip it.
    claimed_expense_indexes = set()

    for env in envelopes:
        if not isinstance(env, dict):
            continue
        if env.get("active", True) is False:
            continue

        budget = _envelope_amount(env)
        if budget <= 0:
            continue

        name = str(env.get("name") or env.get("category") or "Obálka")
        spent = 0.0
        for idx, exp in enumerate(current_expenses):
            if idx in claimed_expense_indexes:
                continue
            if _expense_matches_envelope(exp, name):
                spent += _expense_amount(exp)
                claimed_expense_indexes.add(idx)

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
    # Hold back unpaid payments plus paid-from-account events that have not
    # yet been reflected in the stored balance; then subtract only the
    # REMAINING envelope budget, not already-spent envelope money again.
    payment_holdback_total = unpaid_total + unsettled_paid_total
    after_mandatory = balance - mandatory_total - unsettled_paid_total
    after_payments = balance - payment_holdback_total
    after_all = balance - payment_holdback_total - envelope_remaining_total

    # Dashboard-summary-only fields (docs/navigation_layout.md): counts and
    # top-N previews so the dashboard never needs the full unpaid/deferred
    # lists itself -- those live on /payments and /deferred.
    soon_cutoff = (date.today() + timedelta(days=3)).isoformat()
    due_soon_count = sum(
        1 for item in unpaid_items
        if not item["overdue"] and item["due_date"] <= soon_cutoff
    )
    deferred_sorted = sorted(deferred_items, key=lambda item: item.get("deferred_to") or "9999-99-99")
    next_deferred_item = deferred_sorted[0] if deferred_sorted else None
    top_deferred_items = deferred_sorted[:3]
    # DATA / "audit_log.json" computed fresh (not the module-level
    # AUDIT_LOG_PATH constant) so this stays correct when DATA is patched
    # to an isolated dir in tests, matching every other _read_json() call
    # in this function.
    recent_activity = list(reversed(audit_log.load_audit_log(DATA / "audit_log.json")))[:5]

    return {
        "cycle": cycle,
        "today": today,
        "current_balance": round(balance, 2),

        "unpaid_payments_total": round(unpaid_total, 2),
        "unpaid_mandatory_total": round(mandatory_total, 2),
        "unpaid_optional_total": round(optional_total, 2),
        "unpaid_payment_count": len(unpaid_items),
        "unsettled_paid_total": round(unsettled_paid_total, 2),
        "unsettled_paid_count": len(unsettled_paid_items),

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
        "unsettled_paid_items": unsettled_paid_items,
        "deferred_payment_items": deferred_items,
        "envelope_items": envelope_items,

        # Dashboard-summary aliases/additions -- additive only, existing
        # fields above are unchanged so current consumers keep working.
        "unpaid_count": len(unpaid_items),
        "deferred_count": len(deferred_items),
        "due_soon_count": due_soon_count,
        "next_deferred_item": next_deferred_item,
        "top_deferred_items": top_deferred_items,
        "recent_activity": recent_activity,
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

        audit_log.log_action(AUDIT_LOG_PATH, "balance_updated", f"{balance:.2f} €")

        return redirect(request.referrer or "/?v=balance-updated")
