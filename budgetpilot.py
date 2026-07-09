#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import date
import calendar

from forecast import forecast as run_forecast, payment_state
from obligations import month_key

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"

TODAY = date.today()
SAFE_MIN = None

def load(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False))
    return json.loads(path.read_text())

def month_days(year, month):
    return calendar.monthrange(year, month)[1]

def next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)

def occurs(item, year, month):
    if not item.get("active", True):
        return False
    cancelled_from = item.get("cancelled_from_month")
    if cancelled_from and month_key(year, month) >= cancelled_from:
        return False

    freq = item.get("frequency", "monthly")
    start = date.fromisoformat(item.get("start", f"{year}-01-01"))
    current = date(year, month, 1)
    start_month = date(start.year, start.month, 1)

    if current < start_month:
        return False

    diff = (year - start.year) * 12 + (month - start.month)

    if freq == "monthly":
        return True
    if freq == "quarterly":
        return diff % 3 == 0
    if freq == "yearly":
        return start.month == month
    if freq == "custom_months":
        return diff % int(item.get("every_months", 1)) == 0
    if freq == "once":
        return start.year == year and start.month == month

    return False

def due_date(item, year, month):
    return date(year, month, min(int(item.get("day", 1)), month_days(year, month)))

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

    account_balance = float(settings.get("account_balance", 0))
    use_reserve = bool(settings.get("use_reserve", False))
    safe_min = float(settings.get("safe_min", 0)) if use_reserve else 0

    month_start = date(year, month, 1)
    month_end = date(year, month, month_days(year, month))
    is_current_month = year == TODAY.year and month == TODAY.month

    income_items = [i for i in incomes if occurs(i, year, month)]
    payment_items = [p for p in payments if occurs(p, year, month)]
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
    future_required = 0

    if is_current_month:
        for i in income_items:
            if due_date(i, year, month) > TODAY:
                future_income += float(i["amount"])

        upcoming_payments = [
            {**p, "due_date": due_date(p, year, month)}
            for p in payment_items
            if due_date(p, year, month) >= TODAY
        ]
        fc = run_forecast(account_balance, upcoming_payments, TODAY, next_income)
        future_required = fc["required_main"]

        real_available = account_balance + future_income - future_required - expense_total
    else:
        real_available = planned_month_balance

    days_to_income = max((next_income - TODAY).days, 0) if next_income else None

    usable_money = real_available - safe_min if is_current_month else real_available
    daily_limit = None

    if is_current_month and days_to_income and days_to_income > 0:
        daily_limit = max(usable_money, 0) / days_to_income

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
        "future_required": future_required,
        "real_available": real_available,
        "usable_money": usable_money,
        "daily_limit": daily_limit,
        "days_to_income": days_to_income,
        "status": status_text(usable_money, daily_limit),
        "payments": payment_items,
        "incomes": income_items,
    }

def print_month(r):
    name = calendar.month_name[r["month"]]
    print()
    print(f"===== {name.upper()} {r['year']} =====")
    print(f"Dnes:                   {TODAY}")
    print()
    print(f"Suma na účte teraz:     {r['account_balance']:.2f} €")
    if r["use_reserve"]:
        print(f"Rezerva bokom:          {r['safe_min']:.2f} €")
        print("Poznámka: rezerva sa neráta ako použiteľné peniaze.")
    else:
        print("Rezerva:                vypnutá")
    print()
    print(f"Plánovaný príjem:       {r['income_total']:.2f} €")
    print(f"Plánované platby:       {r['payment_total']:.2f} €")
    print(f"Plán mesiaca:           {r['planned_month_balance']:.2f} €")
    print()
    print(f"Ešte príde príjem:      {r['future_income']:.2f} €")
    print(f"Ešte musíš zaplatiť:    {r['future_required']:.2f} €")
    print(f"Reálne voľné od dnes:   {r['real_available']:.2f} €")
    print(f"Použiteľné peniaze:     {r['usable_money']:.2f} €")
    print(f"Stav:                   {r['status']}")

    if r["days_to_income"] is not None:
        print(f"Do ďalšej výplaty:      {r['days_to_income']} dní")
    if r["daily_limit"] is not None:
        print(f"Na deň:                 {r['daily_limit']:.2f} €")

    print()
    print("Príjmy tento mesiac:")
    for i in sorted(r["incomes"], key=lambda x: x.get("day", 1)):
        d = due_date(i, r["year"], r["month"])
        stav = "ešte príde" if d > TODAY else "už v účte / pred dneškom"
        print(f"- {i['name']}: {float(i['amount']):.2f} € | deň {i.get('day')} | {stav}")

    print()
    print("Platby tento mesiac:")
    for p in sorted(r["payments"], key=lambda x: x.get("day", 1)):
        d = due_date(p, r["year"], r["month"])
        stav = "ešte príde" if d >= TODAY else "pred dneškom"
        print(f"- {p['name']}: {float(p['amount']):.2f} € | deň {p.get('day')} | {p.get('frequency')} | {stav}")

def simulate(months=18):
    y, m = TODAY.year, TODAY.month
    print()
    print("===== SIMULÁCIA PLÁNU =====")
    for _ in range(months):
        r = calc_month(y, m)
        print(
            f"{y}-{m:02d} | príjem {r['income_total']:.0f} € | "
            f"platby {r['payment_total']:.0f} € | plán {r['planned_month_balance']:.0f} € | {r['status']}"
        )
        y, m = next_month(y, m)

def can_spend(amount):
    r = calc_month(TODAY.year, TODAY.month)
    usable_before = r["usable_money"]
    after = usable_before - amount

    per_day = None
    if r["days_to_income"] and r["days_to_income"] > 0:
        per_day = max(after, 0) / r["days_to_income"]

    print()
    print("===== TEST VÝDAVKU =====")
    print(f"Chceš minúť:            {amount:.2f} €")
    print(f"Použiteľné peniaze:     {usable_before:.2f} €")
    print(f"Voľné po výdavku:       {after:.2f} €")

    if r["days_to_income"] and r["days_to_income"] > 0:
        print(f"Do výplaty:             {r['days_to_income']} dní")
        print(f"Na deň po výdavku:      {per_day:.2f} €")

    print(f"Verdikt:                {verdict_text(after, per_day)}")

def main():
    DATA.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        if sys.argv[1] == "spend":
            if len(sys.argv) < 3:
                print("Použitie: ./budgetpilot.py spend 45")
                return
            can_spend(float(sys.argv[2]))
            return

    r = calc_month(TODAY.year, TODAY.month)
    print_month(r)
    simulate(18)

if __name__ == "__main__":
    main()
