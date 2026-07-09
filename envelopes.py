#!/usr/bin/env python3
"""Pure helpers for monthly spending envelopes (budget per category).

No file I/O and no dependency on the rest of BudgetPilot — takes plain
data in, returns plain data out, so it can be unit tested in isolation
(see forecast.py/obligations.py for the same pattern).

An envelope is a recurring monthly limit for one category — it is not
re-entered every month, the same way a recurring payment isn't. Actual
spend for "this month" is always computed fresh from expenses.json, so
there is nothing to reset when a new month starts.
"""
from datetime import date


def _month_key(year, month):
    return f"{year:04d}-{month:02d}"


def expenses_in_month(expenses, year, month):
    key = _month_key(year, month)
    return [e for e in expenses if e.get("date", "")[:7] == key]


def spent_by_category(expenses):
    """Total spend per category (expense['name']) across the given expenses."""
    totals = {}
    for e in expenses:
        cat = e.get("name", "Iné")
        totals[cat] = totals.get(cat, 0.0) + float(e["amount"])
    return totals


def envelope_status(category, monthly_limit, spent):
    remaining = monthly_limit - spent
    return {
        "category": category,
        "monthly_limit": monthly_limit,
        "spent": spent,
        "remaining": remaining,
        "over_budget": remaining < 0,
    }


def envelopes_summary(envelope_defs, expenses_this_month):
    """Per-category status (in envelope_defs order) plus overall totals.

    envelope_defs: list of {"category": str, "monthly_limit": float, ...}.
    Categories with no envelope defined are not included — they're
    unbudgeted, not over budget.
    """
    totals = spent_by_category(expenses_this_month)
    rows = [
        envelope_status(env["category"], float(env["monthly_limit"]), totals.get(env["category"], 0.0))
        for env in envelope_defs
    ]
    total_limit = sum(r["monthly_limit"] for r in rows)
    total_spent = sum(r["spent"] for r in rows)
    return {
        "rows": rows,
        "total_limit": total_limit,
        "total_spent": total_spent,
        "total_remaining": total_limit - total_spent,
    }


def average_monthly_spend(expenses, category, months, today=None):
    """Average spend in `category` per month, over the `months` complete
    calendar months before the current one.

    The current, still-open month is deliberately excluded — including a
    half-finished month would skew the average low. Months with zero
    matching expenses (no history yet, or genuinely nothing spent) count
    as 0 in the average, so a brand-new category correctly averages down
    rather than being excluded from the denominator.
    """
    if today is None:
        today = date.today()
    if months <= 0:
        return 0.0

    y, m = today.year, today.month
    keys = []
    for _ in range(months):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        keys.append(_month_key(y, m))

    monthly_totals = [
        sum(float(e["amount"]) for e in expenses if e.get("name") == category and e.get("date", "")[:7] == key)
        for key in keys
    ]
    return sum(monthly_totals) / len(monthly_totals)
