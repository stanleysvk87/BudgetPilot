#!/usr/bin/env python3
"""Monthly/cycle payment-state events.

Recurring payment templates live in data/payments.json and describe the
obligation itself (name, amount, due day, priority, ...) — they must not
carry a permanent paid/deferred state, because that state would otherwise
leak forward: marking Electricity paid_me in July must not make it
paid_me in August too.

Instead, state changes for a specific cycle are stored here, in
data/payment_events.json, keyed by (payment_id, cycle_key). If no event
exists for a payment in a cycle, its effective state defaults to pending.

Named around "cycle" rather than "month" throughout (cycle_key,
get_current_cycle_key, payment event/occurrence) so a future slice can
move from calendar-month cycles to payday-to-payday cycles without
reshaping this module.
"""
import json
from datetime import date, datetime, timedelta

from forecast import PENDING, PAID_ME, DEFERRED, VALID_STATES
from obligations import month_key
from paths import data_dir

DATA = data_dir()
PAYMENT_EVENTS = DATA / "payment_events.json"

OVERDUE = "overdue"
DUE_TODAY = "due_today"
SOON = "soon"
LATER = "later"
URGENCY_ORDER = {OVERDUE: 0, DUE_TODAY: 1, SOON: 2, LATER: 3}


def cycle_key_for_date(d):
    """YYYY-MM for now; calendar-month is the smallest safe cycle unit
    until payday-to-payday cycles are implemented."""
    return month_key(d.year, d.month)


def get_current_cycle_key(today=None, settings=None):
    """The cycle key `today` falls in. `settings` is accepted but unused —
    a future payday-cycle slice can read payday_day from it to compute
    payday-to-payday cycles instead of calendar months."""
    if today is None:
        today = date.today()
    return cycle_key_for_date(today)


def load_payment_events(path=None):
    path = path or PAYMENT_EVENTS
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def save_payment_events(events, path=None):
    path = path or PAYMENT_EVENTS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2, ensure_ascii=False))


def get_payment_event(events, payment_id, cycle_key):
    for e in events:
        if e.get("payment_id") == payment_id and e.get("cycle_key") == cycle_key:
            return e
    return None


def effective_payment_state(payment, event=None):
    """The state that actually applies for one cycle.

    Hard rule: an explicit event for this (payment_id, cycle_key) wins;
    otherwise the state is pending, full stop — a recurring template's own
    baked-in state/paid fields are never used as a fallback here (that
    would be exactly the July-leaks-into-August bug this module exists to
    fix). Legacy state/paid fields on a template are only meaningful for
    one-time migration into events, not as an ongoing fallback.
    """
    if event is not None and event.get("state") in VALID_STATES:
        return event["state"]
    return PENDING


def apply_payment_events(payments, events, cycle_key):
    """Return copies of `payments` with the effective state (and
    deferred_to/note, if any) for `cycle_key` baked in as 'state'/'paid'.

    Never mutates the templates or the input list. All other template
    metadata (id, name, amount, due_day, priority, flexibility, active,
    start_month, cancelled_from_month, ...) passes through untouched.
    """
    resolved = []
    for p in payments:
        event = get_payment_event(events, p.get("id"), cycle_key)
        item = dict(p)
        state = effective_payment_state(p, event)
        item["state"] = state
        item["paid"] = (state == PAID_ME)
        if event and event.get("deferred_to"):
            item["deferred_to"] = event["deferred_to"]
        elif state != DEFERRED:
            item.pop("deferred_to", None)
        if event and event.get("note"):
            item["note"] = event["note"]
        resolved.append(item)
    return resolved


def set_payment_event(events, payment_id, cycle_key, state, deferred_to=None, note=None, now=None):
    """Return a new events list with the event for (payment_id, cycle_key)
    created or replaced. Never touches any other cycle's event.

    `deferred_to`/`note` fall back to whatever the previous event for this
    same cycle had, so re-selecting a state from the dropdown doesn't
    silently wipe a deferred date or note that a different action set.
    `created_at` is preserved from the existing event (first-seen time),
    `updated_at` always reflects this call.
    """
    if state not in VALID_STATES:
        raise ValueError(f"unknown payment state: {state!r}")

    now = now or datetime.now()
    existing = get_payment_event(events, payment_id, cycle_key)
    remaining = [e for e in events if e is not existing]

    event = {
        "payment_id": payment_id,
        "cycle_key": cycle_key,
        "state": state,
        "created_at": (existing.get("created_at") if existing else None) or now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
    }
    resolved_deferred = deferred_to if deferred_to is not None else (existing.get("deferred_to") if existing else None)
    if state == DEFERRED and resolved_deferred:
        event["deferred_to"] = resolved_deferred
    resolved_note = note if note is not None else (existing.get("note") if existing else None)
    if resolved_note:
        event["note"] = resolved_note

    remaining.append(event)
    return remaining


def defer_payment_to_date(events, payment_id, cycle_key, deferred_to, note=None, now=None):
    """Defer a payment to an explicit, required target date.

    `cycle_key` identifies which event slot to write: the current cycle
    for a fresh defer action, or the payment's existing `origin_cycle_key`
    (see resolve_deferred_carryovers) when re-deferring/changing the date
    of an already-deferred item — reusing that same slot rather than
    creating a second, orphaned deferred event for the same payment.

    `deferred_to` must be a date object; the caller is responsible for
    parsing/validating user input before calling this (see
    budgetpilot_web.payment_event_defer() for the required-field /
    invalid-date rejection this function itself does not perform).
    """
    return set_payment_event(
        events, payment_id, cycle_key, DEFERRED,
        deferred_to=deferred_to.isoformat(), note=note, now=now,
    )


def defer_payment_event(events, payment_id, cycle_key, today, days=7):
    """Legacy one-click +7-days defer. Superseded in the web UI by
    defer_payment_to_date() (deferring now always requires an explicit
    date — see docs/balance_first_rules.md), kept here because it's
    still a valid pure building block and still covered by tests.
    """
    existing = get_payment_event(events, payment_id, cycle_key)
    base = existing.get("deferred_to") if existing else None
    base_date = date.fromisoformat(base) if base else today
    new_target = base_date + timedelta(days=days)
    return set_payment_event(events, payment_id, cycle_key, DEFERRED, deferred_to=new_target.isoformat())


def resolve_deferred_carryovers(payments, events, cycle_key, today):
    """Deferred-state events from ANY cycle, split into:

    - unpaid_carryovers: deferred_to now falls in `cycle_key`'s month or
      earlier — must show as an active unpaid item THIS cycle (rules 2/3
      in docs/balance_first_rules.md), never silently staying hidden as
      "deferred" once its date arrives or passes.
    - still_deferred: deferred_to is still in a later month — stays in
      the deferred bucket, not counted as unpaid yet.

    Each item is shaped like a resolved payment (dict copy of the
    matching entry in `payments`, plus 'due_date'/'state'/'urgency') so
    it can be merged into the same unpaid/deferred lists
    group_payments_by_status() produces, with two extra fields:
    'origin_cycle_key' (the cycle_key the deferred event actually lives
    under — the identity a re-defer/mark-paid action must target) and,
    for promoted items, 'carryover_label'.

    Deliberately independent of a payment's *current*-cycle event: if
    the same recurring payment also has its own fresh event for
    `cycle_key` (or no event at all, i.e. its own natural pending
    occurrence), that is resolved separately by apply_payment_events()/
    group_payments_by_status() — a carryover is always an *additional*
    item, never merged into or replacing the current month's own
    obligation (rule 5).
    """
    payments_by_id = {p.get("id"): p for p in payments if p.get("id")}
    unpaid_carryovers, still_deferred = [], []

    for event in events:
        if event.get("state") != DEFERRED:
            continue
        deferred_to_raw = event.get("deferred_to")
        if not deferred_to_raw:
            continue
        try:
            deferred_to = date.fromisoformat(deferred_to_raw)
        except (TypeError, ValueError):
            continue

        payment_id = event.get("payment_id")
        template = payments_by_id.get(payment_id)
        if template is None:
            continue

        origin_cycle_key = event.get("cycle_key")
        target_cycle_key = cycle_key_for_date(deferred_to)

        item = dict(template)
        item["due_date"] = deferred_to
        item["deferred_to"] = deferred_to_raw
        item["origin_cycle_key"] = origin_cycle_key

        if target_cycle_key <= cycle_key:
            item["state"] = PENDING
            item["urgency"] = urgency_label(deferred_to, today)
            item["carryover_label"] = (
                "Odložené z minulého obdobia" if origin_cycle_key == cycle_key
                else f"Odložené z {origin_cycle_key}"
            )
            unpaid_carryovers.append(item)
        else:
            item["state"] = DEFERRED
            still_deferred.append(item)

    return unpaid_carryovers, still_deferred


def urgency_label(due_date, today):
    """Display/sort-only label — never used to change forecast logic."""
    if due_date is None:
        return LATER
    delta = (due_date - today).days
    if delta < 0:
        return OVERDUE
    if delta == 0:
        return DUE_TODAY
    if delta <= 7:
        return SOON
    return LATER


def group_payments_by_status(payments, today):
    """Split cycle-resolved payments (each with 'state' and a 'due_date'
    date object) into unpaid/deferred/paid buckets for the dashboard.

    Unpaid is sorted most-urgent-first, then by due date, so the mobile
    view shows overdue/due-today/soon items ahead of anything due later.
    """
    unpaid, deferred, paid = [], [], []
    for p in payments:
        state = p.get("state", PENDING)
        if state == PENDING:
            item = dict(p)
            item["urgency"] = urgency_label(p.get("due_date"), today)
            unpaid.append(item)
        elif state == DEFERRED:
            deferred.append(dict(p))
        else:
            paid.append(dict(p))
    unpaid.sort(key=lambda p: (URGENCY_ORDER.get(p["urgency"], 9), p.get("due_date") or date.max))
    return {"unpaid": unpaid, "deferred": deferred, "paid": paid}
