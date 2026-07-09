#!/usr/bin/env python3
"""Pure helpers for the financial-calendar data model.

Covers recurring obligations, one-time obligations, debts, and account
snapshots. No file I/O and no dependency on the rest of BudgetPilot — takes
plain data in, returns plain data out, so it can be unit tested in
isolation (see forecast.py for the same pattern).
"""
from datetime import date, timedelta
import calendar

from forecast import PENDING, PAID_ME, DEFERRED, VALID_STATES

RECEIVED = "received"
I_OWE = "I_owe"
OWED_TO_ME = "owed_to_me"


def _month_days(year, month):
    return calendar.monthrange(year, month)[1]


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def _as_date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


# ---- Recurring obligations ----

def is_recurring_active(item, year, month):
    """Whether a recurring obligation applies in the given month.

    Backward compatible with legacy data/payments.json entries: items with
    no 'active' field default to active, and 'start_month' falls back to
    the legacy 'start' date field when absent.
    """
    if not item.get("active", True):
        return False

    cancelled_from = item.get("cancelled_from_month")
    if cancelled_from and month_key(year, month) >= cancelled_from:
        return False

    start_month = item.get("start_month")
    if not start_month and item.get("start"):
        start_month = item["start"][:7]
    if start_month and month_key(year, month) < start_month:
        return False

    return True


def recurring_due_date(item, year, month):
    day = int(item.get("due_day", item.get("day", 1)))
    return date(year, month, min(day, _month_days(year, month)))


def generate_recurring_for_month(recurring, year, month):
    """Active recurring obligations resolved to concrete due dates for one month."""
    result = []
    for item in recurring:
        if is_recurring_active(item, year, month):
            resolved = dict(item)
            resolved["due_date"] = recurring_due_date(item, year, month)
            result.append(resolved)
    return result


# ---- One-time obligations ----

def onetime_due_in_month(item, year, month):
    due = item.get("due_date")
    if not due:
        return False
    d = _as_date(due)
    return d.year == year and d.month == month


def generate_onetime_for_month(onetime, year, month):
    result = []
    for item in onetime:
        if onetime_due_in_month(item, year, month):
            resolved = dict(item)
            resolved["due_date"] = _as_date(item["due_date"])
            result.append(resolved)
    return result


# ---- Debts ----

def debt_to_payment(debt):
    """Convert a debt into a payment-shaped dict for forecast(), or None.

    I_owe debts behave like any other pending obligation and reduce the
    forecast when due. Money owed to me must never be converted here — it
    is not safe/available cash until it is explicitly marked 'received'.
    """
    if debt.get("direction") != I_OWE:
        return None
    state = debt.get("state", PENDING)
    if state in (RECEIVED, PAID_ME):
        return None
    return {
        "amount": float(debt["amount"]),
        "due_date": _as_date(debt.get("due_date")),
        "state": state if state != RECEIVED else PENDING,
    }


# ---- First-run setup ----

def needs_setup(settings, recurring):
    """First-run setup is required until a real balance and payday exist."""
    if not settings.get("payday_day"):
        return True
    if settings.get("real_balance") is None:
        return True
    return False


# ---- Monthly cycle / account snapshot ----

def new_cycle_snapshot(real_balance, reserve_amount=0.0, note="", today=None):
    """Build a new account snapshot to anchor a monthly cycle.

    The snapshot's real_balance is the source of truth for the new cycle:
    resolve_account_balance() lets it override whatever the previous
    month's settings assumed.
    """
    if today is None:
        today = date.today()
    return {
        "date": today.isoformat(),
        "real_balance": float(real_balance),
        "reserve_amount": float(reserve_amount),
        "note": note,
    }


def latest_snapshot(snapshots):
    if not snapshots:
        return None
    return max(snapshots, key=lambda s: s["date"])


def resolve_account_balance(settings, snapshots):
    """The current real balance: the latest payday snapshot wins over
    whatever stale balance is sitting in settings."""
    snap = latest_snapshot(snapshots)
    if snap is not None:
        return snap["real_balance"]
    return float(settings.get("real_balance", settings.get("account_balance", 0)) or 0)


# ---- Settings / payment merge helpers ----

def merge_settings(existing, updates):
    """Merge submitted settings fields into the existing settings dict.

    Only the keys present in `updates` are overwritten; everything else
    (payday_day, real_balance, reserve_amount, ...) is preserved. Prevents
    a form that only edits account_balance/use_reserve/safe_min from
    dropping first-run setup fields it never saw.
    """
    merged = dict(existing)
    merged.update(updates)
    return merged


def merge_payment_fields(existing, updates):
    """Merge submitted form fields into an existing payment, preserving
    metadata the form doesn't touch (id, priority, flexibility, active,
    start_month, state, cancelled_from_month, paid, ...)."""
    merged = dict(existing)
    merged.update(updates)
    return merged


def set_payment_state(payment, state, deferred_to=None):
    """Return `payment` with its state changed, all other metadata kept.

    Keeps the legacy 'paid' boolean in sync (True only for paid_me) so any
    code still reading 'paid' directly (or old data without a 'state'
    field) sees consistent behavior. `deferred_to` is only applied when
    the new state is DEFERRED; it is otherwise left untouched, so a
    payment that was previously deferred keeps its last deferred_to if
    later moved back to deferred without specifying a new date.
    """
    if state not in VALID_STATES:
        raise ValueError(f"unknown payment state: {state!r}")
    merged = dict(payment)
    merged["state"] = state
    merged["paid"] = (state == PAID_ME)
    if state == DEFERRED and deferred_to is not None:
        merged["deferred_to"] = deferred_to
    return merged


def defer_payment(payment, today, days=7):
    """Push a payment `days` further out, stacking on any existing deferral.

    Simplest safe deferred action the current data model supports: there
    is no per-cycle due-date override, so deferring repeatedly keeps
    adding `days` to the last deferred_to (or to today, the first time).
    """
    base = payment.get("deferred_to")
    base_date = _as_date(base) if base else today
    new_target = base_date + timedelta(days=days)
    return set_payment_state(payment, DEFERRED, deferred_to=new_target.isoformat())


def ensure_recurring_compatible(payment, new_id=None):
    """Fill in whatever a payment needs to work with the recurring
    obligation model, without overwriting values already present.
    """
    payment = dict(payment)
    if not payment.get("id"):
        payment["id"] = new_id
    if "due_day" not in payment:
        payment["due_day"] = payment.get("day", 1)
    if "day" not in payment:
        payment["day"] = payment["due_day"]
    if "start_month" not in payment and payment.get("start"):
        payment["start_month"] = payment["start"][:7]
    payment.setdefault("frequency", "monthly")
    payment.setdefault("priority", "mandatory")
    payment.setdefault("flexibility", "hard_due")
    payment.setdefault("active", True)
    if "paid" not in payment and "state" not in payment:
        payment["paid"] = False
    return payment
