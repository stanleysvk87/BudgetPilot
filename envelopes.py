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
import re
from datetime import date


# ---- Canonical expense <-> envelope matching ----
#
# This is the ONE implementation of "does this expense belong to this
# envelope", used by both consumers: the server-rendered envelope table
# (via envelopes_summary() below) and the balance-first summary that
# feeds the dashboard headline and the JS envelope cards
# (balance_first_summary.py imports from here).
#
# They used to disagree: this module matched expense["name"] == category
# exactly, while balance_first_summary.py did a normalized substring match
# plus an alias table. With an envelope "Strava" (limit 100) and one 40 EUR
# expense named "Lidl", the same page showed spent 0.00 / remaining 100.00
# in the table and spent 40.00 / remaining 60.00 in the cards -- and only
# the second moved "Reálne k dispozícii", the number the user acts on.
# The alias behavior is the documented one (docs/balance_first_rules.md),
# so that is what both sides now share.

CATEGORY_ALIASES = {
    "strava": ("strava", "potraviny", "jedlo", "food", "lidl", "kaufland", "tesco", "billa"),
    "nafta": ("nafta", "palivo", "fuel", "benzina", "slovnaft", "omv", "shell"),
}

# Expense fields searched for the envelope's name, in addition to the
# category itself -- an OCR'd receipt stores the shop under "merchant",
# not "name".
EXPENSE_TEXT_FIELDS = (
    "category", "envelope", "name", "title", "merchant", "description", "note", "source",
)

_DIACRITICS = str.maketrans({
    "á": "a", "ä": "a", "č": "c", "ď": "d", "é": "e", "í": "i",
    "ľ": "l", "ĺ": "l", "ň": "n", "ó": "o", "ô": "o", "ŕ": "r",
    "š": "s", "ť": "t", "ú": "u", "ý": "y", "ž": "z",
})


def normalize_text(value):
    """Lowercase, strip Slovak diacritics, collapse everything that isn't
    a letter or digit into single spaces. "Lekáreň  Dr.Max" -> "lekaren dr max"."""
    value = str(value or "").strip().lower().translate(_DIACRITICS)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def expense_text(expense):
    """The normalized haystack an envelope name is matched against."""
    parts = [str(expense.get(key)) for key in EXPENSE_TEXT_FIELDS if expense.get(key)]
    return normalize_text(" ".join(parts))


def expense_amount(expense):
    for key in ("amount", "total", "price", "value", "suma"):
        if key in expense:
            value = _to_float(expense.get(key))
            if value > 0:
                return value
    return 0.0


def envelope_name(envelope):
    return str(envelope.get("name") or envelope.get("category") or "Obálka").strip()


def envelope_limit(envelope):
    """An envelope's monthly limit, tolerating every key the app has ever
    written for it (envelope_editor.py mirrors the value into all five)."""
    values = [
        _to_float(envelope.get(key))
        for key in ("monthly_budget", "budget", "amount", "monthly_limit", "limit")
        if key in envelope
    ]
    positive = [v for v in values if v > 0]
    return max(positive) if positive else 0.0


def envelope_is_active(envelope):
    return envelope.get("active", True) is not False


def expense_matches_envelope(expense, name):
    """Whether `expense` counts against the envelope called `name`.

    Normalized (accent/case-insensitive) substring match of the envelope
    name against the expense's category/name/merchant/... text, plus the
    small CATEGORY_ALIASES table.
    """
    text = expense_text(expense)
    if not text:
        return False
    target = normalize_text(name)
    if target and target in text:
        return True
    return any(alias in text for alias in CATEGORY_ALIASES.get(target, ()))


def claim_expenses_by_envelope(envelope_defs, expenses):
    """Assign each expense to at most ONE envelope, first match in
    `envelope_defs` order wins.

    Matching is a substring/alias match, so one expense ("nafta v
    Kauflande") can satisfy several envelopes; counting it under each
    would inflate total spent -- and, through envelopes_remaining_total,
    the dashboard's real-balance estimate.

    Returns a list of (envelope, matched_expenses) in envelope_defs order.
    """
    claimed = set()
    result = []
    for envelope in envelope_defs:
        name = envelope_name(envelope)
        matched = []
        for index, expense in enumerate(expenses):
            if index in claimed:
                continue
            if expense_matches_envelope(expense, name):
                claimed.add(index)
                matched.append(expense)
        result.append((envelope, matched))
    return result


def _to_float(value, default=0.0):
    try:
        return float(str(value).replace("€", "").replace(" ", "").replace(",", ".").strip() or default)
    except (TypeError, ValueError):
        return float(default)


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
    unbudgeted, not over budget. Inactive envelopes are skipped, matching
    what the dashboard cards already did.

    Spend per envelope goes through the shared matcher above, so this
    table and the dashboard's real-balance estimate can no longer report
    different numbers for the same envelope.
    """
    active = [e for e in envelope_defs if envelope_is_active(e)]
    spendable = [e for e in expenses_this_month if expense_amount(e) > 0]
    rows = [
        envelope_status(
            envelope.get("category") or envelope_name(envelope),
            envelope_limit(envelope),
            sum(expense_amount(e) for e in matched),
        )
        for envelope, matched in claim_expenses_by_envelope(active, spendable)
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
        sum(
            expense_amount(e) for e in expenses
            if e.get("date", "")[:7] == key and expense_matches_envelope(e, category)
        )
        for key in keys
    ]
    return sum(monthly_totals) / len(monthly_totals)
