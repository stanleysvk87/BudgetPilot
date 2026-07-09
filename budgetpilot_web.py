#!/usr/bin/env python3
import json
import subprocess
import uuid
from pathlib import Path
from datetime import date
from flask import Flask, request, redirect, render_template_string

import obligations as ob
import receipts
import payment_events as pe
from forecast import payment_state, PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"
SNAPSHOTS = DATA / "snapshots.json"

DATA.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)

PAYMENT_TYPES = ["Hypotéka","Nájom","Elektrina","Voda","Plyn","Internet","Paušál","PZP","Havarijná poistka","STK","Olej + filtre","Diaľničná známka","Iné"]
EXPENSE_TYPES = ["Rýchly výdavok","Potraviny","Nafta","Večera","Deti","Lekáreň","Oblečenie","Domácnosť","Iné"]

FREQ_LABEL = {
    "monthly": "mesačne",
    "quarterly": "štvrťročne",
    "yearly": "ročne",
    "custom_months": "vlastné",
    "once": "jednorazovo"
}

STATE_LABEL = {
    PENDING: "Nezaplatené",
    PAID_ME: "Zaplatené z účtu",
    PAID_OTHER: "Zaplatil niekto iný",
    PAID_RESERVE: "Zaplatené z rezervy",
    DEFERRED: "Odložené",
}
STATE_BADGE_CLASS = {
    PENDING: "",
    PAID_ME: "ok",
    PAID_OTHER: "ok",
    PAID_RESERVE: "ok",
    DEFERRED: "warn",
}
# States settable directly from the dropdown; deferred has its own
# "Odložiť o 7 dní" button since it needs a computed deferred_to date.
SELECTABLE_STATES = [PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE]

URGENCY_LABEL_SK = {
    pe.OVERDUE: "Po termíne",
    pe.DUE_TODAY: "Dnes",
    pe.SOON: "Čoskoro",
    pe.LATER: "Neskôr",
}

def load(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False))
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def go_home():
    return redirect("/")

def run_core(args=None):
    try:
        cmd = [str(BASE / "budgetpilot.py")]
        if args:
            cmd += args
        return subprocess.check_output(cmd, text=True)
    except Exception as e:
        return f"CHYBA:\n{e}"

def parse_dash(core):
    d = {
        "money": "-", "day": "-", "status": "-", "status_class": "ok",
        "balance": "-", "unpaid_total": "-", "remaining": "-", "next_payday": "-",
    }
    for line in core.splitlines():
        if "Suma na účte teraz" in line:
            d["balance"] = line.split(":", 1)[1].strip()
        elif "Ešte musíš zaplatiť" in line:
            d["unpaid_total"] = line.split(":", 1)[1].strip()
        elif "Reálne voľné od dnes" in line:
            d["remaining"] = line.split(":", 1)[1].strip()
        elif "Ďalšia výplata" in line:
            d["next_payday"] = line.split(":", 1)[1].strip()
        elif "Použiteľné peniaze" in line:
            d["money"] = line.split(":", 1)[1].strip()
        elif "Na deň" in line:
            d["day"] = line.split(":", 1)[1].strip()
        elif "Stav" in line:
            d["status"] = line.split(":", 1)[1].strip()

    if "PROBLÉM" in d["status"]:
        d["status_class"] = "bad"
    elif "POZOR" in d["status"]:
        d["status_class"] = "warn"
    else:
        d["status_class"] = "ok"
    return d

def payment_form_from_item(item=None):
    if not item:
        return {"type":"Hypotéka","name":"","amount":"","day":"1","month":"1","year":"2026","frequency":"monthly","every_months":""}
    start = item.get("start", "2026-01-01")
    try:
        y, m, d = start.split("-")
    except Exception:
        y, m, d = "2026", "1", str(item.get("day", 1))
    name = item.get("name", "")
    typ = name if name in PAYMENT_TYPES else "Iné"
    return {
        "type": typ,
        "name": name if typ == "Iné" else "",
        "amount": item.get("amount", ""),
        "day": item.get("day", d),
        "month": int(m),
        "year": int(y),
        "frequency": item.get("frequency", "monthly"),
        "every_months": item.get("every_months", "")
    }

HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BudgetPilot</title>
<style>
:root{--bg:#0f172a;--card:#1f2937;--line:#374151;--text:#e5e7eb;--muted:#9ca3af;--blue:#2563eb;--red:#b91c1c;--green:#22c55e;--orange:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#0f172a,#111827);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.app{display:grid;grid-template-columns:370px 1fr;gap:18px;padding:18px}
.table-scroll{overflow-x:auto}
.sidebar{display:flex;flex-direction:column;gap:14px}
.card{background:rgba(31,41,55,.95);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.25)}
h1{font-size:28px;margin:0 0 6px} h2{font-size:20px;margin:0 0 14px}
label{display:block;margin-top:8px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #4b5563;background:#0b1220;color:var(--text);margin-top:6px}
button{padding:10px 14px;border:0;border-radius:12px;background:var(--blue);color:white;font-weight:700;cursor:pointer}
.danger{background:var(--red)} .secondary{background:#4b5563}
.btn-row{display:flex;gap:8px;margin-top:10px}.btn-row button{flex:1}
.topgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.metric .label{font-size:13px;color:var(--muted)} .metric .value{font-size:32px;font-weight:900;margin-top:4px}
.ok{color:var(--green)} .warn{color:var(--orange)} .bad{color:var(--red)}
.main{display:flex;flex-direction:column;gap:14px}
table{width:100%;border-collapse:collapse} th,td{padding:11px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px} th{color:var(--muted);font-size:13px}
.actions{display:flex;gap:6px;justify-content:flex-end}.actions form{margin:0}
.actions-stack{display:flex;flex-direction:column;gap:6px;align-items:stretch;min-width:160px}.actions-stack form{margin:0}.actions-stack select{margin:0}
.small{font-size:13px;color:var(--muted);line-height:1.35}.inline{display:grid;grid-template-columns:1fr 1fr;gap:8px}
pre{white-space:pre-wrap;background:#020617;border:1px solid var(--line);border-radius:14px;padding:14px;overflow:auto;max-height:380px;font-size:13px}
.badge{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;background:#374151}
.badge.ok{background:#14532d} .badge.warn{background:#78350f}
a{color:white;text-decoration:none}
.topnav{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px;padding:12px 18px;background:rgba(15,23,42,.97);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.topnav .brand{font-weight:900;margin-right:8px}
.topnav a,.topnav .navlink{color:var(--text);text-decoration:none;padding:8px 10px;border-radius:10px;font-size:14px}
.topnav a:hover{background:var(--line)}
.topnav .navlink.disabled{color:var(--muted);cursor:default}
.summarygrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.summarygrid .metric .value{font-size:26px}
.section{margin-bottom:14px}
.urgency-overdue{color:var(--red);font-weight:700}
.urgency-due_today{color:var(--orange);font-weight:700}
.urgency-soon{color:var(--orange)}
.urgency-later{color:var(--muted)}
details.card summary{cursor:pointer;font-size:20px;font-weight:700}
@media(max-width:1000px){
.app{grid-template-columns:1fr;display:flex;flex-direction:column}
.main{order:1} .sidebar{order:2}
.topgrid{grid-template-columns:1fr} .summarygrid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:600px){
.app{padding:10px} table{min-width:560px}
.topnav{padding:10px 12px;gap:2px 10px} .topnav a,.topnav .navlink{padding:10px 12px;font-size:15px}
.summarygrid{grid-template-columns:1fr}
}
</style>
</head>
<body>
<nav class="topnav">
<span class="brand">BudgetPilot</span>
<a href="#overview">Prehľad</a>
<a href="#payments">Platby</a>
<a href="#expenses">Výdavky</a>
<a href="#settings">Nastavenia</a>
<span class="navlink disabled">Obálky (čoskoro)</span>
<span class="navlink disabled">Dlhy (čoskoro)</span>
<span class="navlink disabled">Kalendár (čoskoro)</span>
</nav>
<div class="app">

<aside class="sidebar">
<div class="card" id="settings">
<h1>BudgetPilot</h1>
<div class="small">Hrubá pravda o mesiaci. Bez AI, bez blbostí.</div>
</div>

{% if setup_needed %}
<div class="card" style="border-color:var(--orange)">
<h2>⚠️ Dokonči nastavenie</h2>
<div class="small">Chýba deň výplaty alebo reálny zostatok k dnešnému dňu.</div>
<div class="btn-row"><a href="/setup"><button type="button">Otvoriť nastavenie</button></a></div>
</div>
{% endif %}

<div class="card">
<h2>Účet + rezerva</h2>
<form method="post" action="/settings">
<label>Suma na účte teraz</label>
<input name="account_balance" value="{{settings.get('account_balance',0)}}">
<label><input type="checkbox" name="use_reserve" {% if settings.get('use_reserve') %}checked{% endif %} style="width:auto"> Mám reálnu rezervu bokom</label>
<label>Rezerva bokom</label>
<input name="safe_min" value="{{settings.get('safe_min',0)}}">
<div class="small">Rezerva sa neráta medzi použiteľné peniaze. Zapni iba keď ju máš naozaj bokom.</div>
<div class="btn-row"><button>Uložiť</button></div>
</form>
</div>

<div class="card">
<h2>{% if edit_income is not none %}Upraviť príjem{% else %}Príjem{% endif %}</h2>
<form method="post" action="{% if edit_income is not none %}/income/update/{{edit_income}}{% else %}/income/add{% endif %}">
<label>Názov</label><input name="name" value="{{income_form.get('name','Výplata netto')}}">
<label>Suma</label><input name="amount" value="{{income_form.get('amount','2000')}}">
<label>Deň v mesiaci</label><input name="day" value="{{income_form.get('day','15')}}">
<div class="btn-row">
<button>{% if edit_income is not none %}Uložiť úpravu{% else %}Pridať príjem{% endif %}</button>
{% if edit_income is not none %}<a href="/"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>

<div class="card">
<h2>{% if edit_payment is not none %}Upraviť platbu{% else %}Pravidelná platba{% endif %}</h2>
<form method="post" action="{% if edit_payment is not none %}/payment/update/{{edit_payment}}{% else %}/payment/add{% endif %}">
<label>Typ</label>
<select name="type">{% for t in payment_types %}<option {% if payment_form.type==t %}selected{% endif %}>{{t}}</option>{% endfor %}</select>
<label>Názov pri „Iné“</label><input name="name" value="{{payment_form.name}}" placeholder="napr. škôlka, leasing, daň">
<label>Suma</label><input name="amount" value="{{payment_form.amount}}" placeholder="napr. 820">
<div class="inline">
<div><label>Deň</label><input name="day" value="{{payment_form.day}}"></div>
<div><label>Mesiac štartu</label><input name="month" value="{{payment_form.month}}"></div>
</div>
<label>Rok štartu</label><input name="year" value="{{payment_form.year}}">
<label>Opakovanie</label>
<select name="frequency">
{% for f in ["monthly","quarterly","yearly","custom_months","once"] %}
<option value="{{f}}" {% if payment_form.frequency==f %}selected{% endif %}>{{freq_label.get(f,f)}}</option>
{% endfor %}
</select>
<label>Ak vlastné: každých X mesiacov</label><input name="every_months" value="{{payment_form.every_months}}" placeholder="napr. 24">
<div class="btn-row">
<button>{% if edit_payment is not none %}Uložiť úpravu{% else %}Pridať platbu{% endif %}</button>
{% if edit_payment is not none %}<a href="/"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>

<div class="card">
<h2>Rýchly výdavok</h2>
<form method="post" action="/expense/add">
<input type="hidden" name="name" value="Rýchly výdavok">
<label>Suma</label><input name="amount" placeholder="napr. 50">
<input type="hidden" name="date" value="{{today}}">
<div class="btn-row"><button>Pridať</button></div>
</form>
</div>

<div class="card">
<h2>{% if edit_expense is not none %}Upraviť výdavok{% else %}Detailný výdavok{% endif %}</h2>
<form method="post" action="{% if edit_expense is not none %}/expense/update/{{edit_expense}}{% else %}/expense/add{% endif %}">
<label>Typ</label>
<select name="name">{% for t in expense_types %}<option {% if expense_form.name==t %}selected{% endif %}>{{t}}</option>{% endfor %}</select>
<label>Suma</label><input name="amount" value="{{expense_form.amount}}">
<label>Dátum</label><input name="date" value="{{expense_form.date}}">
<div class="btn-row">
<button>{% if edit_expense is not none %}Uložiť úpravu{% else %}Pridať výdavok{% endif %}</button>
{% if edit_expense is not none %}<a href="/"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>
</aside>

<main class="main" id="overview">
<div class="summarygrid">
<div class="card metric"><div class="label">Zostatok na účte</div><div class="value">{{summary.balance}}</div></div>
<div class="card metric"><div class="label">Nezaplatené (do výplaty)</div><div class="value">{{summary.unpaid_total}}</div></div>
<div class="card metric"><div class="label">Zostane po povinných platbách</div><div class="value">{{summary.remaining}}</div></div>
<div class="card metric"><div class="label">Bezpečne minúť</div><div class="value {{dash.status_class}}">{{summary.safe_to_spend}}</div></div>
<div class="card metric"><div class="label">Na deň do výplaty</div><div class="value">{{summary.daily_safe_to_spend}}</div></div>
<div class="card metric"><div class="label">Ďalšia výplata</div><div class="value">{{summary.next_payday}}</div></div>
</div>

<div class="card section">
<h2>Nezaplatené / treba zaplatiť</h2>
{% if unpaid %}
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Termín</th><th>Priorita</th><th>Naliehavosť</th><th></th></tr>
{% for p in unpaid %}
<tr>
<td>{{p.name}}</td><td>{{p.amount}} €</td><td>{{p.due_date}}</td><td>{{p.get('priority','-')}}</td>
<td class="urgency-{{p.urgency}}">{{urgency_label_sk.get(p.urgency, p.urgency)}}</td>
<td class="actions-stack">
<form method="post" action="/payment/state/{{p._index}}">
<select name="state">{% for s in selectable_states %}<option value="{{s}}">{{state_label.get(s,s)}}</option>{% endfor %}</select>
<button class="secondary">Nastaviť</button>
</form>
<form method="post" action="/payment/defer/{{p._index}}"><button class="secondary">Odložiť o 7 dní</button></form>
</td></tr>
{% endfor %}
</table>
</div>
{% else %}<div class="small">Nič nečaká na zaplatenie. ✅</div>{% endif %}
</div>

<div class="card section">
<h2>Odložené</h2>
{% if deferred %}
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Odložené do</th><th></th></tr>
{% for p in deferred %}
<tr>
<td>{{p.name}}</td><td>{{p.amount}} €</td><td>{{p.get('deferred_to','-')}}</td>
<td class="actions-stack">
<form method="post" action="/payment/state/{{p._index}}">
<select name="state">{% for s in selectable_states %}<option value="{{s}}">{{state_label.get(s,s)}}</option>{% endfor %}</select>
<button class="secondary">Nastaviť</button>
</form>
<form method="post" action="/payment/defer/{{p._index}}"><button class="secondary">Odložiť o 7 dní</button></form>
</td></tr>
{% endfor %}
</table>
</div>
{% else %}<div class="small">Nič odložené.</div>{% endif %}
</div>

<details class="card section">
<summary>Zaplatené ({{paid|length}})</summary>
{% if paid %}
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Stav</th></tr>
{% for p in paid %}
<tr><td>{{p.name}}</td><td>{{p.amount}} €</td><td><span class="badge {{state_badge_class.get(p.state,'')}}">{{state_label.get(p.state, p.state)}}</span></td></tr>
{% endfor %}
</table>
</div>
{% else %}<div class="small">Zatiaľ nič zaplatené v tomto cykle.</div>{% endif %}
</details>

<div class="card">
<h2>Môžem minúť?</h2>
<form method="get" action="/">
<div class="inline"><input name="test" placeholder="napr. 50" value="{{test_amount}}"><button>Otestovať</button></div>
</form>
{% if test_result %}<pre>{{test_result}}</pre>{% endif %}
</div>

<div class="card">
<h2>Príjmy</h2>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th></th></tr>
{% for x in incomes %}
<tr><td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('day')}}</td>
<td class="actions">
<form method="get" action="/edit/income/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/income/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>

<div class="card" id="payments">
<h2>Platby (všetky, vrátane šablón)</h2>
<div class="small">Stav platí pre aktuálny cyklus ({{cycle_key}}). Úprava platby mení iba šablónu, nie stav v tomto cykle.</div>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th>Frekvencia</th><th>Stav</th><th></th></tr>
{% for x in payments %}
{% set rx = payments_resolved[loop.index0] %}
<tr>
<td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('day')}}</td>
<td>{{freq_label.get(x.get('frequency'), x.get('frequency'))}}{% if x.get('frequency')=='custom_months' %} / {{x.get('every_months')}} mes.{% endif %}</td>
<td><span class="badge {{state_badge_class.get(rx.state,'')}}">{{state_label.get(rx.state, rx.state)}}</span>{% if rx.state=='deferred' and rx.get('deferred_to') %}<br><span class="small">do {{rx.deferred_to}}</span>{% endif %}</td>
<td class="actions-stack">
<form method="post" action="/payment/state/{{loop.index0}}">
<select name="state">
{% for s in selectable_states %}<option value="{{s}}" {% if rx.state==s %}selected{% endif %}>{{state_label.get(s,s)}}</option>{% endfor %}
</select>
<button class="secondary">Nastaviť</button>
</form>
<form method="post" action="/payment/defer/{{loop.index0}}"><button class="secondary">Odložiť o 7 dní</button></form>
<form method="get" action="/edit/payment/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/payment/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>

<div class="card" id="expenses">
<h2>Výdavky navyše</h2>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Dátum</th><th></th></tr>
{% for x in expenses %}
<tr><td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('date')}}</td>
<td class="actions">
<form method="get" action="/edit/expense/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/expense/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>

<details class="card">
<summary>Technický výstup</summary>
<pre>{{core}}</pre>
</details>
</main>
</div>
</body>
</html>
"""

def resolve_payments_for_cycle(payments, today):
    """Each template resolved to its due date for `today`'s month, plus the
    effective state/deferred_to for the current cycle. Same length/order as
    `payments`, so `loop.index0` still lines up for the management table
    and the per-payment action routes (/payment/state/<i>, /payment/defer/<i>)."""
    cycle_key = pe.get_current_cycle_key(today)
    events = pe.load_payment_events()
    resolved = []
    for idx, p in enumerate(payments):
        item = dict(p)
        item["due_date"] = ob.recurring_due_date(p, today.year, today.month)
        item["_index"] = idx
        resolved.append(item)
    return pe.apply_payment_events(resolved, events, cycle_key), cycle_key

def render_page(edit_income=None, edit_payment=None, edit_expense=None):
    settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})
    incomes = load(INCOMES, [])
    payments = load(PAYMENTS, [])
    expenses = load(EXPENSES, [])
    setup_needed = ob.needs_setup(settings, payments)
    core = run_core()
    test_amount = request.args.get("test", "")
    test_result = run_core(["spend", test_amount]) if test_amount else ""

    today = date.today()
    payments_resolved, cycle_key = resolve_payments_for_cycle(payments, today)
    active_resolved = [
        p for p in payments_resolved
        if ob.is_recurring_active(payments[p["_index"]], today.year, today.month)
    ]
    groups = pe.group_payments_by_status(active_resolved, today)

    dash = parse_dash(core)
    summary = {
        "balance": dash["balance"],
        "unpaid_total": dash["unpaid_total"],
        "remaining": dash["remaining"],
        "safe_to_spend": dash["money"],
        "daily_safe_to_spend": dash["day"],
        "next_payday": dash["next_payday"] if dash["next_payday"] != "-" else (
            f"deň {settings.get('payday_day')}" if settings.get("payday_day") else "-"
        ),
    }

    income_form = {"name":"Výplata netto","amount":"2000","day":"15"}
    payment_form = payment_form_from_item(None)
    expense_form = {"name":"Potraviny","amount":"","date":date.today().isoformat()}

    if edit_income is not None and edit_income < len(incomes):
        income_form = incomes[edit_income]
    if edit_payment is not None and edit_payment < len(payments):
        payment_form = payment_form_from_item(payments[edit_payment])
    if edit_expense is not None and edit_expense < len(expenses):
        expense_form = expenses[edit_expense]

    return render_template_string(
        HTML,
        settings=settings, incomes=incomes, payments=payments, expenses=expenses,
        core=core, dash=dash, summary=summary, today=today.isoformat(),
        payments_resolved=payments_resolved, cycle_key=cycle_key,
        unpaid=groups["unpaid"], deferred=groups["deferred"], paid=groups["paid"],
        urgency_label_sk=URGENCY_LABEL_SK,
        payment_types=PAYMENT_TYPES, expense_types=EXPENSE_TYPES, freq_label=FREQ_LABEL,
        test_result=test_result, test_amount=test_amount,
        edit_income=edit_income, edit_payment=edit_payment, edit_expense=edit_expense,
        income_form=income_form, payment_form=payment_form, expense_form=expense_form,
        setup_needed=setup_needed,
        state_label=STATE_LABEL,
        state_badge_class=STATE_BADGE_CLASS, selectable_states=SELECTABLE_STATES
    )

@app.route("/")
def index():
    return render_page()

@app.route("/edit/income/<int:i>")
def edit_income(i):
    return render_page(edit_income=i)

@app.route("/edit/payment/<int:i>")
def edit_payment(i):
    return render_page(edit_payment=i)

@app.route("/edit/expense/<int:i>")
def edit_expense(i):
    return render_page(edit_expense=i)

@app.post("/settings")
def settings_save():
    settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})
    updates = {
        "account_balance": float(request.form.get("account_balance",0) or 0),
        "use_reserve": bool(request.form.get("use_reserve")),
        "safe_min": float(request.form.get("safe_min",0) or 0),
    }
    save(SETTINGS, ob.merge_settings(settings, updates))
    return go_home()

@app.post("/income/add")
def income_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(INCOMES, [])
        data.append({"name":request.form.get("name","Výplata"),"amount":float(amount),"day":int(request.form.get("day",1) or 1),"frequency":"monthly","start":"2026-01-01"})
        save(INCOMES, data)
    return go_home()

@app.post("/income/update/<int:i>")
def income_update(i):
    data = load(INCOMES, [])
    if i < len(data):
        data[i].update({"name":request.form.get("name","Výplata"),"amount":float(request.form.get("amount",0) or 0),"day":int(request.form.get("day",1) or 1)})
    save(INCOMES, data)
    return go_home()

@app.post("/income/delete/<int:i>")
def income_delete(i):
    data = load(INCOMES, [])
    if i < len(data): data.pop(i)
    save(INCOMES, data)
    return go_home()

def make_payment_from_form():
    """Fields the main-dashboard payment form actually submits. Used both
    to build a new payment and as the update dict when editing one — it
    must NOT include metadata (id, priority, flexibility, active, state,
    ...) the form doesn't expose, or an edit would clobber it."""
    typ = request.form.get("type","Iné")
    name = request.form.get("name","").strip() if typ == "Iné" else typ
    if not name: name = "Iné"
    day = int(request.form.get("day",1) or 1)
    month = int(request.form.get("month",1) or 1)
    year = int(request.form.get("year",2026) or 2026)
    freq = request.form.get("frequency","monthly")
    start = f"{year:04d}-{month:02d}-{day:02d}"
    item = {
        "name": name,
        "amount": float(request.form.get("amount",0) or 0),
        "day": day,
        "due_day": day,
        "frequency": freq,
        "start": start,
        "start_month": start[:7],
    }
    if freq == "custom_months":
        item["every_months"] = int(request.form.get("every_months",1) or 1)
    return item

@app.post("/payment/add")
def payment_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(PAYMENTS, [])
        item = ob.ensure_recurring_compatible(make_payment_from_form(), new_id=uuid.uuid4().hex[:8])
        data.append(item)
        save(PAYMENTS, data)
    return go_home()

@app.post("/payment/update/<int:i>")
def payment_update(i):
    data = load(PAYMENTS, [])
    if i < len(data):
        data[i] = ob.merge_payment_fields(data[i], make_payment_from_form())
    save(PAYMENTS, data)
    return go_home()

@app.post("/payment/state/<int:i>")
def payment_set_state(i):
    data = load(PAYMENTS, [])
    new_state = request.form.get("state", PENDING)
    if i < len(data) and new_state in SELECTABLE_STATES and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.set_payment_event(events, data[i]["id"], cycle_key, new_state)
        pe.save_payment_events(events)
    return go_home()

@app.post("/payment/defer/<int:i>")
def payment_defer(i):
    data = load(PAYMENTS, [])
    if i < len(data) and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.defer_payment_event(events, data[i]["id"], cycle_key, today)
        pe.save_payment_events(events)
    return go_home()

@app.post("/payment/delete/<int:i>")
def payment_delete(i):
    data = load(PAYMENTS, [])
    if i < len(data): data.pop(i)
    save(PAYMENTS, data)
    return go_home()

@app.post("/expense/add")
def expense_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(EXPENSES, [])
        data.append({
            "name": request.form.get("name","Výdavok"),
            "amount": float(amount),
            "date": request.form.get("date", date.today().isoformat()),
            "source": receipts.SOURCE_MANUAL,
        })
        save(EXPENSES, data)
    return go_home()

@app.post("/expense/update/<int:i>")
def expense_update(i):
    data = load(EXPENSES, [])
    if i < len(data):
        updates = {
            "name": request.form.get("name","Výdavok"),
            "amount": float(request.form.get("amount",0) or 0),
            "date": request.form.get("date", date.today().isoformat()),
        }
        data[i] = {**data[i], **updates}
    save(EXPENSES, data)
    return go_home()

@app.post("/expense/delete/<int:i>")
def expense_delete(i):
    data = load(EXPENSES, [])
    if i < len(data): data.pop(i)
    save(EXPENSES, data)
    return go_home()

SETUP_HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BudgetPilot — nastavenie</title>
<style>
:root{--bg:#0f172a;--card:#1f2937;--line:#374151;--text:#e5e7eb;--muted:#9ca3af;--blue:#2563eb;--red:#b91c1c;--green:#22c55e;--orange:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#0f172a,#111827);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:18px}
.wrap{max-width:520px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.card{background:rgba(31,41,55,.95);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.25)}
h1{font-size:26px;margin:0 0 6px} h2{font-size:19px;margin:0 0 12px}
label{display:block;margin-top:8px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #4b5563;background:#0b1220;color:var(--text);margin-top:6px}
button{padding:10px 14px;border:0;border-radius:12px;background:var(--blue);color:white;font-weight:700;cursor:pointer}
.danger{background:var(--red)} .secondary{background:#4b5563}
.btn-row{display:flex;gap:8px;margin-top:10px}.btn-row button{flex:1}
.small{font-size:13px;color:var(--muted);line-height:1.35}
table{width:100%;border-collapse:collapse} th,td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:13px} th{color:var(--muted)}
.actions{display:flex;gap:6px;justify-content:flex-end}.actions form{margin:0}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;background:#374151}
.badge.ok{background:#14532d}
a{color:white;text-decoration:none}
</style>
</head>
<body>
<div class="wrap">

<div class="card">
<h1>Nastavenie</h1>
<div class="small">Toto vyplníš raz na začiatku a potom vždy, keď príde výplata.</div>
</div>

<div class="card">
<h2>Deň výplaty a reálny zostatok</h2>
<form method="post" action="/setup/balance">
<label>Deň výplaty v mesiaci</label>
<input name="payday_day" value="{{settings.get('payday_day','')}}" placeholder="napr. 15">
<label>Reálny zostatok na účte teraz</label>
<input name="real_balance" value="{{settings.get('real_balance', settings.get('account_balance', ''))}}" placeholder="napr. 850">
<label>Rezerva bokom (voliteľné)</label>
<input name="reserve_amount" value="{{settings.get('reserve_amount', settings.get('safe_min', 0))}}">
<div class="small">Tento zostatok je od teraz zdroj pravdy pre nový cyklus — prepíše predchádzajúce odhady.</div>
<div class="btn-row"><button>Uložiť</button></div>
</form>
</div>

<div class="card">
<h2>Pridať pravidelnú platbu</h2>
<form method="post" action="/setup/recurring">
<label>Názov</label><input name="name" placeholder="napr. škôlka">
<label>Suma</label><input name="amount" placeholder="napr. 120">
<label>Deň splatnosti v mesiaci</label><input name="due_day" placeholder="napr. 5">
<label>Priorita</label>
<select name="priority">
<option value="mandatory">nevyhnutná</option>
<option value="important">dôležitá</option>
<option value="flexible">flexibilná</option>
<option value="optional">voliteľná</option>
</select>
<label>Flexibilita</label>
<select name="flexibility">
<option value="hard_due">musí byť v termíne</option>
<option value="can_defer">dá sa posunúť</option>
<option value="optional">voliteľná</option>
</select>
<div class="btn-row"><button>Pridať platbu</button></div>
</form>
</div>

<div class="card">
<h2>Pravidelné platby</h2>
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th>Stav</th><th></th></tr>
{% for x in recurring %}
<tr>
<td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('due_day', x.get('day'))}}</td>
<td>{% if x.get('active', True) %}<span class="badge ok">aktívna</span>{% else %}<span class="badge">zrušená</span>{% endif %}</td>
<td class="actions">
{% if x.get('id') %}
<form method="post" action="/setup/recurring/toggle/{{x.get('id')}}"><button class="secondary">{% if x.get('active', True) %}Zrušiť{% else %}Obnoviť{% endif %}</button></form>
{% endif %}
</td>
</tr>
{% endfor %}
</table>
<div class="small">Pravidelné platby sa objavujú v prehľade každý mesiac automaticky, kým ich nezrušíš.</div>
</div>

<div class="card">
<a href="/"><button type="button" class="secondary">Späť na prehľad</button></a>
</div>

</div>
</body>
</html>
"""

@app.route("/setup")
def setup_page():
    settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})
    recurring = load(PAYMENTS, [])
    return render_template_string(SETUP_HTML, settings=settings, recurring=recurring)

@app.post("/setup/balance")
def setup_balance():
    settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})
    real_balance = float(request.form.get("real_balance", 0) or 0)
    reserve_amount = float(request.form.get("reserve_amount", 0) or 0)
    payday_raw = request.form.get("payday_day", "").strip()

    settings["real_balance"] = real_balance
    settings["reserve_amount"] = reserve_amount
    settings["account_balance"] = real_balance
    settings["safe_min"] = reserve_amount
    settings["use_reserve"] = reserve_amount > 0
    if payday_raw:
        settings["payday_day"] = int(payday_raw)
    save(SETTINGS, settings)

    snapshots = load(SNAPSHOTS, [])
    snapshots.append(ob.new_cycle_snapshot(real_balance, reserve_amount))
    save(SNAPSHOTS, snapshots)

    return redirect("/setup")

@app.post("/setup/recurring")
def setup_recurring_add():
    amount = request.form.get("amount", "").strip()
    name = request.form.get("name", "").strip()
    if amount and name:
        data = load(PAYMENTS, [])
        due_day = int(request.form.get("due_day", 1) or 1)
        today_iso = date.today().isoformat()
        data.append({
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "amount": float(amount),
            "day": due_day,
            "due_day": due_day,
            "frequency": "monthly",
            "start": today_iso,
            "start_month": today_iso[:7],
            "priority": request.form.get("priority", "mandatory"),
            "flexibility": request.form.get("flexibility", "hard_due"),
            "active": True,
            "paid": False,
        })
        save(PAYMENTS, data)
    return redirect("/setup")

@app.post("/setup/recurring/toggle/<item_id>")
def setup_recurring_toggle(item_id):
    data = load(PAYMENTS, [])
    for item in data:
        if item.get("id") == item_id:
            item["active"] = not item.get("active", True)
            break
    save(PAYMENTS, data)
    return redirect("/setup")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=False)
