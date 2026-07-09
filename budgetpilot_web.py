#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import date
from flask import Flask, request, redirect, render_template_string

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"

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
    d = {"money": "-", "day": "-", "status": "-", "status_class": "ok"}
    for line in core.splitlines():
        if "Použiteľné peniaze" in line:
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
<title>BudgetPilot</title>
<style>
:root{--bg:#0f172a;--card:#1f2937;--line:#374151;--text:#e5e7eb;--muted:#9ca3af;--blue:#2563eb;--red:#b91c1c;--green:#22c55e;--orange:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#0f172a,#111827);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.app{display:grid;grid-template-columns:370px 1fr;gap:18px;padding:18px}
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
.small{font-size:13px;color:var(--muted);line-height:1.35}.inline{display:grid;grid-template-columns:1fr 1fr;gap:8px}
pre{white-space:pre-wrap;background:#020617;border:1px solid var(--line);border-radius:14px;padding:14px;overflow:auto;max-height:380px;font-size:13px}
.badge{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;background:#374151}
a{color:white;text-decoration:none}
@media(max-width:1000px){.app{grid-template-columns:1fr}.topgrid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">

<aside class="sidebar">
<div class="card">
<h1>BudgetPilot</h1>
<div class="small">Hrubá pravda o mesiaci. Bez AI, bez blbostí.</div>
</div>

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

<main class="main">
<div class="topgrid">
<div class="card metric"><div class="label">Použiteľné peniaze</div><div class="value">{{dash.money}}</div></div>
<div class="card metric"><div class="label">Na deň</div><div class="value">{{dash.day}}</div></div>
<div class="card metric"><div class="label">Stav</div><div class="value {{dash.status_class}}">{{dash.status}}</div></div>
</div>

<div class="card">
<h2>Môžem minúť?</h2>
<form method="get" action="/">
<div class="inline"><input name="test" placeholder="napr. 50" value="{{test_amount}}"><button>Otestovať</button></div>
</form>
{% if test_result %}<pre>{{test_result}}</pre>{% endif %}
</div>

<div class="card">
<h2>Príjmy</h2>
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

<div class="card">
<h2>Platby</h2>
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th>Frekvencia</th><th>Stav</th><th></th></tr>
{% for x in payments %}
<tr>
<td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('day')}}</td>
<td>{{freq_label.get(x.get('frequency'), x.get('frequency'))}}{% if x.get('frequency')=='custom_months' %} / {{x.get('every_months')}} mes.{% endif %}</td>
<td>{% if x.get('paid') %}<span class="badge ok">zaplatené</span>{% else %}<span class="badge">nezaplatené</span>{% endif %}</td>
<td class="actions">
<form method="post" action="/payment/toggle/{{loop.index0}}"><button class="secondary">{% if x.get('paid') %}Odznačiť{% else %}Zaplatené{% endif %}</button></form>
<form method="get" action="/edit/payment/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/payment/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>

<div class="card">
<h2>Výdavky navyše</h2>
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

<details class="card">
<summary>Technický výstup</summary>
<pre>{{core}}</pre>
</details>
</main>
</div>
</body>
</html>
"""

def render_page(edit_income=None, edit_payment=None, edit_expense=None):
    settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})
    incomes = load(INCOMES, [])
    payments = load(PAYMENTS, [])
    expenses = load(EXPENSES, [])
    core = run_core()
    test_amount = request.args.get("test", "")
    test_result = run_core(["spend", test_amount]) if test_amount else ""

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
        core=core, dash=parse_dash(core), today=date.today().isoformat(),
        payment_types=PAYMENT_TYPES, expense_types=EXPENSE_TYPES, freq_label=FREQ_LABEL,
        test_result=test_result, test_amount=test_amount,
        edit_income=edit_income, edit_payment=edit_payment, edit_expense=edit_expense,
        income_form=income_form, payment_form=payment_form, expense_form=expense_form
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
    save(SETTINGS, {
        "account_balance": float(request.form.get("account_balance",0) or 0),
        "use_reserve": bool(request.form.get("use_reserve")),
        "safe_min": float(request.form.get("safe_min",0) or 0),
    })
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

def make_payment_from_form(existing_paid=False):
    typ = request.form.get("type","Iné")
    name = request.form.get("name","").strip() if typ == "Iné" else typ
    if not name: name = "Iné"
    day = int(request.form.get("day",1) or 1)
    month = int(request.form.get("month",1) or 1)
    year = int(request.form.get("year",2026) or 2026)
    freq = request.form.get("frequency","monthly")
    item = {"name":name,"amount":float(request.form.get("amount",0) or 0),"day":day,"frequency":freq,"priority":"mandatory","paid":existing_paid,"start":f"{year:04d}-{month:02d}-{day:02d}"}
    if freq == "custom_months":
        item["every_months"] = int(request.form.get("every_months",1) or 1)
    return item

@app.post("/payment/add")
def payment_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(PAYMENTS, [])
        data.append(make_payment_from_form(False))
        save(PAYMENTS, data)
    return go_home()

@app.post("/payment/update/<int:i>")
def payment_update(i):
    data = load(PAYMENTS, [])
    if i < len(data):
        paid = bool(data[i].get("paid", False))
        data[i] = make_payment_from_form(paid)
    save(PAYMENTS, data)
    return go_home()

@app.post("/payment/toggle/<int:i>")
def payment_toggle(i):
    data = load(PAYMENTS, [])
    if i < len(data):
        data[i]["paid"] = not data[i].get("paid", False)
    save(PAYMENTS, data)
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
        data.append({"name":request.form.get("name","Výdavok"),"amount":float(amount),"date":request.form.get("date",date.today().isoformat())})
        save(EXPENSES, data)
    return go_home()

@app.post("/expense/update/<int:i>")
def expense_update(i):
    data = load(EXPENSES, [])
    if i < len(data):
        data[i] = {"name":request.form.get("name","Výdavok"),"amount":float(request.form.get("amount",0) or 0),"date":request.form.get("date",date.today().isoformat())}
    save(EXPENSES, data)
    return go_home()

@app.post("/expense/delete/<int:i>")
def expense_delete(i):
    data = load(EXPENSES, [])
    if i < len(data): data.pop(i)
    save(EXPENSES, data)
    return go_home()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
