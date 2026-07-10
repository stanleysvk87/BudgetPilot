#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import date
import tkinter as tk
from tkinter import ttk, messagebox

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"

DATA.mkdir(parents=True, exist_ok=True)

# ---------- DATA ----------
def load(p, d):
    if not p.exists():
        p.write_text(json.dumps(d, indent=2))
    return json.loads(p.read_text())

def save(p, d):
    p.write_text(json.dumps(d, indent=2))

def run_core(args=None):
    try:
        cmd = [str(BASE / "budgetpilot.py")]
        if args:
            cmd += args
        return subprocess.check_output(cmd, text=True)
    except Exception as e:
        return str(e)

# ---------- APP ----------
root = tk.Tk()
root.title("BudgetPilot v3")
root.geometry("1300x850")

main = ttk.Frame(root)
main.pack(fill="both", expand=True)

# ---------- LEFT (SCROLL) ----------
left_canvas = tk.Canvas(main, width=450)
scroll = ttk.Scrollbar(main, orient="vertical", command=left_canvas.yview)
left = ttk.Frame(left_canvas)

left.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
left_canvas.create_window((0, 0), window=left, anchor="nw")
left_canvas.configure(yscrollcommand=scroll.set)

left_canvas.pack(side="left", fill="y")
scroll.pack(side="left", fill="y")

# scroll kolieskom
left_canvas.bind_all("<MouseWheel>", lambda e: left_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

# ---------- RIGHT ----------
right = ttk.Frame(main)
right.pack(side="right", fill="both", expand=True, padx=10)

# ---------- DASHBOARD ----------
dash = ttk.Frame(right)
dash.pack(fill="x", pady=5)

lbl_money = ttk.Label(dash, text="€ 0", font=("Arial", 28, "bold"))
lbl_money.pack(anchor="w")

lbl_day = ttk.Label(dash, text="€/deň: 0", font=("Arial", 14))
lbl_day.pack(anchor="w")

lbl_status = ttk.Label(dash, text="STAV", font=("Arial", 14))
lbl_status.pack(anchor="w")

# ---------- OUTPUT ----------
output = tk.Text(right, height=25, font=("Monospace", 10))
output.pack(fill="both", expand=True)

def refresh():
    out = run_core()
    output.delete("1.0", tk.END)
    output.insert(tk.END, out)

    for line in out.splitlines():
        if "Použiteľné peniaze" in line:
            lbl_money.config(text=line.split(":")[1].strip())
        if "Na deň" in line:
            lbl_day.config(text=line.split(":")[1].strip())
        if "Stav" in line:
            lbl_status.config(text=line.split(":")[1].strip())

    refresh_lists()

# ---------- ÚČET ----------
box = ttk.LabelFrame(left, text="Účet + rezerva")
box.pack(fill="x", pady=5, padx=5)

settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})

balance = ttk.Entry(box)
balance.insert(0, settings.get("account_balance",0))
balance.pack(fill="x")

reserve_enabled = tk.BooleanVar(value=settings.get("use_reserve",False))
ttk.Checkbutton(box, text="Použiť rezervu", variable=reserve_enabled).pack(anchor="w")

reserve = ttk.Entry(box)
reserve.insert(0, settings.get("safe_min",0))
reserve.pack(fill="x")

def save_account():
    save(SETTINGS,{
        "account_balance": float(balance.get()),
        "use_reserve": reserve_enabled.get(),
        "safe_min": float(reserve.get() or 0)
    })
    refresh()

ttk.Button(box, text="Uložiť", command=save_account).pack(fill="x", pady=5)

# ---------- PRÍJEM ----------
box = ttk.LabelFrame(left, text="Príjem")
box.pack(fill="x", pady=5, padx=5)

inc_name = ttk.Entry(box)
inc_name.insert(0,"Výplata")
inc_name.pack(fill="x")

inc_amount = ttk.Entry(box)
inc_amount.insert(0,"2000")
inc_amount.pack(fill="x")

inc_day = ttk.Spinbox(box, from_=1, to=31)
inc_day.set(15)
inc_day.pack(fill="x")

def add_income():
    data = load(INCOMES,[])
    data.append({
        "name": inc_name.get(),
        "amount": float(inc_amount.get()),
        "day": int(inc_day.get()),
        "frequency":"monthly",
        "start":"2026-01-01"
    })
    save(INCOMES,data)
    refresh()

ttk.Button(box, text="Pridať príjem", command=add_income).pack(fill="x", pady=5)

# ---------- PLATBA ----------
box = ttk.LabelFrame(left, text="Platba")
box.pack(fill="x", pady=5, padx=5)

pay_type = ttk.Combobox(box, values=["Hypotéka","Elektrina","Voda","PZP","Internet","Iné"])
pay_type.set("Hypotéka")
pay_type.pack(fill="x")

pay_name = ttk.Entry(box)
pay_name.pack(fill="x")

pay_amount = ttk.Entry(box)
pay_amount.pack(fill="x")

pay_day = ttk.Spinbox(box, from_=1, to=31)
pay_day.pack(fill="x")

pay_freq = ttk.Combobox(box, values=["monthly","quarterly","yearly","custom"])
pay_freq.set("monthly")
pay_freq.pack(fill="x")

pay_every = ttk.Entry(box)
pay_every.pack(fill="x")

def add_payment():
    name = pay_name.get() if pay_type.get()=="Iné" else pay_type.get()
    item = {
        "name": name,
        "amount": float(pay_amount.get()),
        "day": int(pay_day.get()),
        "frequency": pay_freq.get(),
        "start":"2026-01-01"
    }
    if pay_freq.get()=="custom":
        item["every_months"] = int(pay_every.get() or 1)

    data = load(PAYMENTS,[])
    data.append(item)
    save(PAYMENTS,data)
    refresh()

ttk.Button(box, text="Pridať platbu", command=add_payment).pack(fill="x", pady=5)

# ---------- RÝCHLY VÝDAVOK ----------
box = ttk.LabelFrame(left, text="Rýchly výdavok")
box.pack(fill="x", pady=5, padx=5)

quick = ttk.Entry(box)
quick.insert(0,"50")
quick.pack(fill="x")

def quick_exp():
    data = load(EXPENSES,[])
    data.append({
        "name":"rýchly výdavok",
        "amount": float(quick.get()),
        "date": date.today().isoformat()
    })
    save(EXPENSES,data)
    refresh()

ttk.Button(box, text="Pridať", command=quick_exp).pack(fill="x")

# ---------- DETAILNÝ VÝDAVOK ----------
box = ttk.LabelFrame(left, text="Výdavok")
box.pack(fill="x", pady=5, padx=5)

exp_name = ttk.Combobox(box, values=["Potraviny","Nafta","Večera","Deti","Iné"])
exp_name.set("Potraviny")
exp_name.pack(fill="x")

exp_amount = ttk.Entry(box)
exp_amount.pack(fill="x")

exp_date = ttk.Entry(box)
exp_date.insert(0, date.today().isoformat())
exp_date.pack(fill="x")

def add_exp():
    data = load(EXPENSES,[])
    data.append({
        "name": exp_name.get(),
        "amount": float(exp_amount.get()),
        "date": exp_date.get()
    })
    save(EXPENSES,data)
    refresh()

ttk.Button(box, text="Pridať výdavok", command=add_exp).pack(fill="x")

# ---------- LISTY ----------
box = ttk.LabelFrame(left, text="Zoznamy")
box.pack(fill="both", pady=5, padx=5)

income_list = tk.Listbox(box, height=5)
income_list.pack(fill="x")

payment_list = tk.Listbox(box, height=6)
payment_list.pack(fill="x")

expense_list = tk.Listbox(box, height=6)
expense_list.pack(fill="x")

def refresh_lists():
    income_list.delete(0,tk.END)
    payment_list.delete(0,tk.END)
    expense_list.delete(0,tk.END)

    for i in load(INCOMES,[]):
        income_list.insert(tk.END,f"{i['name']} {i['amount']}€")

    for p in load(PAYMENTS,[]):
        payment_list.insert(tk.END,f"{p['name']} {p['amount']}€")

    for e in load(EXPENSES,[]):
        expense_list.insert(tk.END,f"{e['name']} {e['amount']}€")

refresh()
root.mainloop()
