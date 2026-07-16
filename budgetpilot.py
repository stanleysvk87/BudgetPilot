#!/usr/bin/env python3
import sys
import os
from datetime import date
import calendar

from forecast import forecast as run_forecast, payment_state, current_cash_position
from obligations import month_key, debt_to_payment, generate_onetime_for_month, is_recurring_active
from payment_events import load_payment_events, apply_payment_events
from paths import app_base, data_dir
import json_store
from i18n import DEFAULT_LANGUAGE, normalize_language, translate

BASE = app_base()
DATA = data_dir()
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"
DEBTS = DATA / "debts.json"
ONETIME = DATA / "onetime.json"

TODAY = date.today()
SAFE_MIN = None

CLI_LANGUAGE = normalize_language(os.environ.get("BUDGETPILOT_LANG", DEFAULT_LANGUAGE))

def t(text):
    return translate(text, CLI_LANGUAGE)

def load(path, default):
    if not path.exists():
        json_store.atomic_write_json(path, default)
    return json_store.read_json(path, default)

def month_days(year, month):
    return calendar.monthrange(year, month)[1]

def next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)

def occurs(item, year, month):
    """Whether `item` is due in `year`/`month`.

    Thin wrapper kept for backward compatibility (this name is the
    original, CLI-side occurrence check) — the actual logic now lives in
    obligations.is_recurring_active(), the one canonical implementation
    also used by the web dashboard and balance_first_summary.py. See that
    function's docstring for why this consolidation matters.
    """
    return is_recurring_active(item, year, month)

def due_date(item, year, month):
    day = max(1, min(int(item.get("day", 1)), month_days(year, month)))
    return date(year, month, day)

def next_income_date_all(incomes):
    dates = []
    y, m = TODAY.year, TODAY.month

    for _ in range(24):
        for inc in incomes:
            if occurs(inc, y, m):
                d = due_date(inc, y, m)
                if d > TODAY:
                    dates.append(d)
        y, m = next_month(y, m)

    return sorted(dates)[0] if dates else None

def status_text(money, daily=None):
    if money < 0:
        return "❌ PROBLÉM"
    if daily is not None and daily < 15:
        return "⚠️ POZOR"
    if money < 100:
        return "⚠️ POZOR"
    return "✅ OK"

def verdict_text(after, per_day):
    if after < 0:
        return "❌ Nedávaj to. Chýbajú peniaze."
    if per_day is not None and per_day < 15:
        return "⚠️ Radšej nie. Pôjdeš na doraz."
    if per_day is not None and per_day < 30:
        return "🤏 Môžeš, ale nepreháňaj."
    return "✅ Kľudne."

def calc_month(year, month):
    settings = load(SETTINGS, {"account_balance": 0})
    incomes = load(INCOMES, [])
    payments = load(PAYMENTS, [])
    expenses = load(EXPENSES, [])
    debts = load(DEBTS, [])
    onetime = load(ONETIME, [])
    events = load_payment_events()

    account_balance = float(settings.get("account_balance", 0))
    use_reserve = bool(settings.get("use_reserve", False))
    safe_min = float(settings.get("safe_min", 0)) if use_reserve else 0

    month_start = date(year, month, 1)
    month_end = date(year, month, month_days(year, month))
    is_current_month = year == TODAY.year and month == TODAY.month

    income_items = [i for i in incomes if occurs(i, year, month)]
    # A one-time obligation only ever appears in the single month it's due,
    # resolved with a "day" field so it plugs into the same due_date()/
    # cycle-state machinery as a recurring payment below.
    onetime_this_month = []
    for item in generate_onetime_for_month(onetime, year, month):
        item["day"] = item["due_date"].day
        item.setdefault("frequency", "once")
        onetime_this_month.append(item)
    # Effective payment state is resolved per cycle: a July event never
    # affects August, and a payment with no event for this cycle defaults
    # to pending, regardless of whatever state its template last carried.
    payment_items = apply_payment_events(
        [p for p in payments if occurs(p, year, month)] + onetime_this_month,
        events, month_key(year, month),
    )
    expense_items = [
        e for e in expenses
        if month_start <= date.fromisoformat(e["date"]) <= month_end
    ]

    income_total = sum(float(i["amount"]) for i in income_items)
    payment_total = sum(float(p["amount"]) for p in payment_items)
    expense_total = sum(float(e["amount"]) for e in expense_items)
    planned_month_balance = income_total - payment_total - expense_total

    next_income = next_income_date_all(incomes)

    future_income = 0
    unpaid_required_before_payday = 0

    if is_current_month:
        for i in income_items:
            if due_date(i, year, month) > TODAY:
                future_income += float(i["amount"])

        # payment_items is already scoped to this month's occurrences, so
        # every pending item here belongs in the forecast -- including one
        # whose calendar due_date has already passed. An unpaid bill does
        # not stop reducing safe-to-spend just because it's now overdue;
        # matches balance_first_summary.py's build_balance_first_summary(),
        # which already counts an overdue-but-unpaid item toward its
        # unpaid_total instead of dropping it.
        upcoming_payments = [
            {**p, "due_date": due_date(p, year, month)}
            for p in payment_items
        ]
        # I_owe debts reduce the forecast exactly like any other pending
        # obligation once due; owed_to_me debts are never converted here
        # (see obligations.debt_to_payment) so they can't inflate it. Same
        # overdue rule as payments above: an already-due debt still counts.
        # Debts aren't month-scoped like payments, so still bound them to
        # "due before the next payday" when that date is known, so a debt
        # due much later doesn't prematurely reduce today's safe-to-spend.
        upcoming_debts = [
            dp for dp in (debt_to_payment(d) for d in debts)
            if dp is not None and dp["due_date"] is not None
            and (next_income is None or dp["due_date"] <= next_income)
        ]
        fc = run_forecast(account_balance, upcoming_payments + upcoming_debts, TODAY, next_income)
        unpaid_required_before_payday = fc["required_main"]

        # Current cash position: only money available *now*. Future income
        # must never inflate this, or a real shortfall reads as "safe".
        position = current_cash_position(account_balance, unpaid_required_before_payday, safe_min)
        safe_to_spend_now = position["safe_to_spend_now"]
        shortfall_before_payday = position["shortfall_before_payday"]

        # Separate projection that *may* include future income — never
        # shown as if it were money available today.
        projected_after_payday = (
            account_balance + future_income - unpaid_required_before_payday - expense_total - safe_min
        )
    else:
        safe_to_spend_now = max(planned_month_balance, 0.0)
        shortfall_before_payday = min(planned_month_balance, 0.0)
        projected_after_payday = planned_month_balance

    days_to_income = max((next_income - TODAY).days, 0) if next_income else None

    daily_limit = None
    if is_current_month and days_to_income and days_to_income > 0:
        daily_limit = max(safe_to_spend_now, 0) / days_to_income

    return {
        "year": year,
        "month": month,
        "account_balance": account_balance,
        "safe_min": safe_min,
        "use_reserve": use_reserve,
        "income_total": income_total,
        "payment_total": payment_total,
        "expense_total": expense_total,
        "planned_month_balance": planned_month_balance,
        "future_income": future_income,
        "unpaid_required_before_payday": unpaid_required_before_payday,
        "safe_to_spend_now": safe_to_spend_now,
        "shortfall_before_payday": shortfall_before_payday,
        "projected_after_payday": projected_after_payday,
        "daily_limit": daily_limit,
        "days_to_income": days_to_income,
        "next_income_date": next_income.isoformat() if next_income else None,
        "status": status_text(safe_to_spend_now, daily_limit),
        "payments": payment_items,
        "incomes": income_items,
    }

def print_month(r):
    name = calendar.month_name[r["month"]]
    print()
    print(f"===== {name.upper()} {r['year']} =====")
    print(f"{t('Dnes:'):<24}{TODAY}")
    print()
    print(f"{t('Suma na účte teraz:'):<24}{r['account_balance']:.2f} €")
    if r["use_reserve"]:
        print(f"{t('Rezerva bokom:'):<24}{r['safe_min']:.2f} €")
        print(t("Poznámka: rezerva sa neráta ako použiteľné peniaze."))
    else:
        print(f"{t('Rezerva:'):<24}{t('vypnutá')}")
    print()
    print(f"{t('Plánovaný príjem:'):<24}{r['income_total']:.2f} €")
    print(f"{t('Plánované platby:'):<24}{r['payment_total']:.2f} €")
    print(f"{t('Plán mesiaca:'):<24}{r['planned_month_balance']:.2f} €")
    print()
    print(f"{t('Ešte príde príjem:'):<24}{r['future_income']:.2f} €")
    print(f"{t('Nezaplatené do výplaty:'):<24}{r['unpaid_required_before_payday']:.2f} €")
    print(f"{t('Bezpečne minúť teraz:'):<24}{r['safe_to_spend_now']:.2f} €")
    if r["shortfall_before_payday"] < 0:
        print(f"{t('Chýba do výplaty:'):<24}{r['shortfall_before_payday']:.2f} €")
    print(f"{t('Odhad po najbližšej výplate:'):<32}{r['projected_after_payday']:.2f} €")
    print(f"{t('Stav:'):<24}{t(r['status'])}")

    if r["days_to_income"] is not None:
        print(f"{t('Do ďalšej výplaty:'):<24}{r['days_to_income']} {t('dní')}")
    if r["daily_limit"] is not None:
        print(f"{t('Na deň:'):<24}{r['daily_limit']:.2f} €")
    if r.get("next_income_date"):
        print(f"{t('Ďalšia výplata:'):<24}{r['next_income_date']}")

    print()
    print(t("Príjmy tento mesiac:"))
    for i in sorted(r["incomes"], key=lambda x: x.get("day", 1)):
        d = due_date(i, r["year"], r["month"])
        stav = t("ešte príde") if d > TODAY else t("už v účte / pred dneškom")
        print(f"- {i['name']}: {float(i['amount']):.2f} € | {t('deň')} {i.get('day')} | {stav}")

    print()
    print(t("Platby tento mesiac:"))
    for p in sorted(r["payments"], key=lambda x: x.get("day", 1)):
        d = due_date(p, r["year"], r["month"])
        stav = t("ešte príde") if d >= TODAY else t("pred dneškom")
        print(f"- {p['name']}: {float(p['amount']):.2f} € | {t('deň')} {p.get('day')} | {t(p.get('frequency'))} | {stav}")

def simulate(months=18):
    y, m = TODAY.year, TODAY.month
    print()
    print(t("===== SIMULÁCIA PLÁNU ====="))
    for _ in range(months):
        r = calc_month(y, m)
        print(
            f"{y}-{m:02d} | {t('príjem')} {r['income_total']:.0f} € | "
            f"{t('platby')} {r['payment_total']:.0f} € | {t('plán')} {r['planned_month_balance']:.0f} € | {t(r['status'])}"
        )
        y, m = next_month(y, m)

def can_spend(amount):
    r = calc_month(TODAY.year, TODAY.month)
    usable_before = r["safe_to_spend_now"]
    after = usable_before - amount

    per_day = None
    if r["days_to_income"] and r["days_to_income"] > 0:
        per_day = max(after, 0) / r["days_to_income"]

    print()
    print(t("===== TEST VÝDAVKU ====="))
    print(f"{t('Chceš minúť:'):<24}{amount:.2f} €")
    print(f"{t('Bezpečne minúť teraz:'):<24}{usable_before:.2f} €")
    print(f"{t('Voľné po výdavku:'):<24}{after:.2f} €")

    if r["days_to_income"] and r["days_to_income"] > 0:
        print(f"{t('Do výplaty:'):<24}{r['days_to_income']} {t('dní')}")
        print(f"{t('Na deň po výdavku:'):<24}{per_day:.2f} €")

    print(f"{t('Verdikt:'):<24}{t(verdict_text(after, per_day))}")

def main():
    DATA.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        if sys.argv[1] == "spend":
            if len(sys.argv) < 3:
                print(t("Použitie: ./budgetpilot.py spend 45"))
                return
            can_spend(float(sys.argv[2]))
            return

    r = calc_month(TODAY.year, TODAY.month)
    print_month(r)
    simulate(18)

if __name__ == "__main__":
    main()
