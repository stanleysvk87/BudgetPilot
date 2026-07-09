#!/usr/bin/env python3
"""Pure cashflow forecast calculation.

No file I/O and no dependency on the rest of BudgetPilot — takes plain
data in, returns plain data out, so it can be unit tested in isolation.
"""
from datetime import date

PENDING = "pending"
PAID_ME = "paid_me"
PAID_OTHER = "paid_other"
PAID_RESERVE = "paid_reserve"
DEFERRED = "deferred"

VALID_STATES = {PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED}


def payment_state(payment):
    """Normalize a payment's state, honoring the legacy boolean 'paid' field."""
    state = payment.get("state")
    if state in VALID_STATES:
        return state
    if payment.get("paid"):
        return PAID_ME
    return PENDING


def effective_due_date(payment, due_date):
    """The date a payment actually falls on, given its state.

    A deferred payment moves to 'deferred_to' if set, otherwise it keeps
    its original due date (still pending, just flagged for later review).
    'deferred_to' may arrive as an ISO date string straight out of JSON,
    so it's normalized to a date object here rather than pushing that
    requirement onto every caller.
    """
    deferred_to = payment.get("deferred_to")
    if payment_state(payment) == DEFERRED and deferred_to:
        return date.fromisoformat(deferred_to) if isinstance(deferred_to, str) else deferred_to
    return due_date


def forecast(account_balance, payments, today, horizon_end=None):
    """Compute how much main-account cash is still required by pending obligations.

    payments: list of dicts, each with at least {"amount": float}, a
        resolved "due_date" (date object), and either a "state" field
        (one of PENDING/PAID_ME/PAID_OTHER/PAID_RESERVE/DEFERRED) or the
        legacy boolean "paid".
    today, horizon_end: date objects. horizon_end is typically the next
        income date; when omitted, days_to_income/daily figures are None.

    Cashflow rule: only 'pending' payments, and 'deferred' payments whose
    new date still falls within [today, horizon_end], reduce the main
    account forecast. 'paid_me' is already reflected in account_balance.
    'paid_other' never touches the main account. 'paid_reserve' draws
    from the reserve, not the main account.
    """
    required_main = 0.0
    reserve_out = 0.0
    paid_other_total = 0.0
    paid_me_total = 0.0
    breakdown = {state: [] for state in VALID_STATES}

    for p in payments:
        state = payment_state(p)
        amount = float(p["amount"])
        due = effective_due_date(p, p.get("due_date"))
        breakdown[state].append(p)

        if state == PENDING:
            required_main += amount
        elif state == PAID_ME:
            paid_me_total += amount
        elif state == PAID_OTHER:
            paid_other_total += amount
        elif state == PAID_RESERVE:
            reserve_out += amount
        elif state == DEFERRED:
            if due is not None and today <= due and (horizon_end is None or due <= horizon_end):
                required_main += amount

    after_required = account_balance - required_main

    days_to_income = None
    daily_safe_to_spend = None
    if horizon_end is not None:
        days_to_income = max((horizon_end - today).days, 0)
        if days_to_income > 0:
            daily_safe_to_spend = max(after_required, 0) / days_to_income

    return {
        "required_main": required_main,
        "reserve_out": reserve_out,
        "paid_other_total": paid_other_total,
        "paid_me_total": paid_me_total,
        "after_required": after_required,
        "safe_to_spend": max(after_required, 0),
        "days_to_income": days_to_income,
        "daily_safe_to_spend": daily_safe_to_spend,
        "breakdown": breakdown,
    }
