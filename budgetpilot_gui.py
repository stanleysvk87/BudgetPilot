#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"

DATA.mkdir(parents=True, exist_ok=True)

PAYMENT_PRESETS = {
    "Hypotéka": "monthly",
    "Nájom": "monthly",
    "Elektrina": "monthly",
    "Plyn": "monthly",
    "Voda": "monthly",
    "Internet": "monthly",
    "Paušál": "monthly",
    "Havarijná poistka": "quarterly",
    "PZP / zákonná poistka": "yearly",
    "STK": "custom_months",
    "Olej + filtre": "custom_months",
    "Diaľničná známka": "yearly",
    "Poistka domácnosť": "yearly",
    "Iné": "monthly",
}

FREQ_LABELS = {
    "Mesačne": "monthly",
    "Štvrťročne": "quarterly",
    "Polročne": "custom_months",
    "Ročne": "yearly",
    "Každé 2 roky": "custom_months",
    "Jednorazovo": "once",
}

REVERSE_FREQ = {v: k for k, v in FREQ_LABELS.items()}

selected_income_index = None
selected_payment_index = None

def load(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False))
    return json.loads(path.read_text())

def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def refresh_output():
    try:
        out = subprocess.check_output([str(BASE / "budgetpilot.py")], text=True)
    except Exception as e:
        out = f"Chyba:\n{e}"
    output.delete("1.0", tk.END)
    output.insert(tk.END, out)

def refresh_lists():
    income_list.delete(0, tk.END)
    payment_list.delete(0, tk.END)

    for idx, item in enumerate(load(INCOMES, [])):
        income_list.insert(tk.END, f"{idx}: {item.get('name')} | {item.get('amount')} € | deň {item.get('day')}")

    for idx, item in enumerate(load(PAYMENTS, [])):
        txt = f"{idx}: {item.get('name')} | {item.get('amount')} € | deň {item.get('day')} | {item.get('frequency')}"
        if item.get("frequency") == "custom_months":
            txt += f" / {item.get('every_months')} mes."
        payment_list.insert(tk.END, txt)

def refresh_all():
    refresh_output()
    refresh_lists()

def clear_entry(e):
    e.delete(0, tk.END)

def set_entry(e, value):
    e.delete(0, tk.END)
    e.insert(0, str(value))

def save_balance():
    try:
        amount = float(balance_entry.get().replace(",", "."))
        use_reserve = reserve_enabled.get()
        reserve = float(reserve_entry.get().replace(",", ".")) if use_reserve else 0
        save(SETTINGS, {
            "account_balance": amount,
            "use_reserve": use_reserve,
            "safe_min": reserve
        })
        refresh_all()
    except ValueError:
        messagebox.showerror("Chyba", "Zadaj správnu sumu.")

def add_income():
    try:
        incomes = load(INCOMES, [])
        incomes.append({
            "name": income_type.get() or "Výplata netto",
            "amount": float(income_amount.get().replace(",", ".")),
            "day": int(income_day.get()),
            "frequency": "monthly",
            "start": "2026-01-01"
        })
        save(INCOMES, incomes)
        refresh_all()
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def update_income():
    global selected_income_index
    if selected_income_index is None:
        messagebox.showinfo("Info", "Najprv vyber príjem zo zoznamu.")
        return
    try:
        incomes = load(INCOMES, [])
        if selected_income_index >= len(incomes):
            return
        incomes[selected_income_index] = {
            "name": income_type.get() or "Výplata netto",
            "amount": float(income_amount.get().replace(",", ".")),
            "day": int(income_day.get()),
            "frequency": "monthly",
            "start": incomes[selected_income_index].get("start", "2026-01-01")
        }
        save(INCOMES, incomes)
        refresh_all()
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def on_income_select(event=None):
    global selected_income_index
    sel = income_list.curselection()
    if not sel:
        return
    selected_income_index = sel[0]
    data = load(INCOMES, [])
    if selected_income_index >= len(data):
        return
    item = data[selected_income_index]
    income_type.set(item.get("name", "Výplata netto"))
    set_entry(income_amount, item.get("amount", 0))
    income_day.set(str(item.get("day", 15)))

def preset_changed(event=None):
    name = payment_type.get()
    if name != "Iné":
        payment_name_var.set(name)

    freq = PAYMENT_PRESETS.get(name, "monthly")
    if freq == "monthly":
        payment_freq_label.set("Mesačne")
        clear_entry(payment_every)
    elif freq == "quarterly":
        payment_freq_label.set("Štvrťročne")
        clear_entry(payment_every)
    elif freq == "yearly":
        payment_freq_label.set("Ročne")
        clear_entry(payment_every)
    elif freq == "custom_months":
        payment_freq_label.set("Každé 2 roky")
        set_entry(payment_every, 24)

def freq_changed(event=None):
    label = payment_freq_label.get()
    clear_entry(payment_every)
    if label == "Polročne":
        set_entry(payment_every, 6)
    elif label == "Každé 2 roky":
        set_entry(payment_every, 24)

def payment_item_from_form(old=None):
    freq_label = payment_freq_label.get()
    freq = FREQ_LABELS.get(freq_label, "monthly")

    day = int(payment_day.get())
    month = int(payment_month.get())
    year = int(payment_year.get())

    item = {
        "name": payment_name_var.get().strip() or payment_type.get() or "Platba",
        "amount": float(payment_amount.get().replace(",", ".")),
        "day": day,
        "frequency": freq,
        "priority": "mandatory",
        "start": f"{year:04d}-{month:02d}-{day:02d}"
    }

    if freq == "custom_months":
        if freq_label == "Polročne":
            item["every_months"] = 6
        elif freq_label == "Každé 2 roky":
            item["every_months"] = 24
        else:
            item["every_months"] = int(payment_every.get() or "1")

    return item

def add_payment():
    try:
        payments = load(PAYMENTS, [])
        payments.append(payment_item_from_form())
        save(PAYMENTS, payments)
        clear_entry(payment_amount)
        refresh_all()
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def update_payment():
    global selected_payment_index
    if selected_payment_index is None:
        messagebox.showinfo("Info", "Najprv vyber platbu zo zoznamu.")
        return
    try:
        payments = load(PAYMENTS, [])
        if selected_payment_index >= len(payments):
            return
        payments[selected_payment_index] = payment_item_from_form(payments[selected_payment_index])
        save(PAYMENTS, payments)
        refresh_all()
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def on_payment_select(event=None):
    global selected_payment_index
    sel = payment_list.curselection()
    if not sel:
        return
    selected_payment_index = sel[0]
    data = load(PAYMENTS, [])
    if selected_payment_index >= len(data):
        return
    item = data[selected_payment_index]

    name = item.get("name", "Iné")
    if name in PAYMENT_PRESETS:
        payment_type.set(name)
    else:
        payment_type.set("Iné")

    payment_name_var.set(name)
    set_entry(payment_amount, item.get("amount", 0))
    payment_day.set(str(item.get("day", 1)))

    start = item.get("start", "2026-01-01")
    try:
        y, m, d = start.split("-")
        payment_year.set(y)
        payment_month.set(str(int(m)))
        payment_day.set(str(int(d)))
    except Exception:
        pass

    freq = item.get("frequency", "monthly")
    if freq == "custom_months":
        every = int(item.get("every_months", 1))
        if every == 6:
            payment_freq_label.set("Polročne")
        elif every == 24:
            payment_freq_label.set("Každé 2 roky")
        else:
            payment_freq_label.set("Polročne")
        set_entry(payment_every, every)
    elif freq == "quarterly":
        payment_freq_label.set("Štvrťročne")
        clear_entry(payment_every)
    elif freq == "yearly":
        payment_freq_label.set("Ročne")
        clear_entry(payment_every)
    elif freq == "once":
        payment_freq_label.set("Jednorazovo")
        clear_entry(payment_every)
    else:
        payment_freq_label.set("Mesačne")
        clear_entry(payment_every)

def delete_selected_income():
    global selected_income_index
    sel = income_list.curselection()
    if not sel:
        return
    idx = sel[0]
    data = load(INCOMES, [])
    if idx < len(data):
        removed = data.pop(idx)
        save(INCOMES, data)
        selected_income_index = None
        refresh_all()
        messagebox.showinfo("Zmazané", f"Zmazané: {removed.get('name')}")

def delete_selected_payment():
    global selected_payment_index
    sel = payment_list.curselection()
    if not sel:
        return
    idx = sel[0]
    data = load(PAYMENTS, [])
    if idx < len(data):
        removed = data.pop(idx)
        save(PAYMENTS, data)
        selected_payment_index = None
        refresh_all()
        messagebox.showinfo("Zmazané", f"Zmazané: {removed.get('name')}")

def add_expense():
    try:
        expenses = load(EXPENSES, [])
        expenses.append({
            "name": expense_name.get().strip() or "Výdavok",
            "amount": float(expense_amount.get().replace(",", ".")),
            "date": expense_date.get().strip(),
            "category": expense_category.get().strip() or "iné"
        })
        save(EXPENSES, expenses)
        expense_amount.delete(0, tk.END)
        refresh_all()
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def spend_test():
    try:
        amount = spend_entry.get().replace(",", ".")
        out = subprocess.check_output([str(BASE / "budgetpilot.py"), "spend", amount], text=True)
        output.delete("1.0", tk.END)
        output.insert(tk.END, out)
    except Exception as e:
        messagebox.showerror("Chyba", str(e))

def clear_all():
    global selected_income_index, selected_payment_index
    if not messagebox.askyesno("Reset", "Naozaj vymazať príjmy a platby?"):
        return
    save(INCOMES, [])
    save(PAYMENTS, [])
    selected_income_index = None
    selected_payment_index = None
    refresh_all()

root = tk.Tk()
root.title("BudgetPilot")
root.geometry("1180x860")

main = ttk.Frame(root, padding=10)
main.pack(fill=tk.BOTH, expand=True)

left_canvas = tk.Canvas(main, width=470)
left_scrollbar = ttk.Scrollbar(main, orient="vertical", command=left_canvas.yview)
left = ttk.Frame(left_canvas)

left.bind(
    "<Configure>",
    lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
)

left_canvas.create_window((0, 0), window=left, anchor="nw")
left_canvas.configure(yscrollcommand=left_scrollbar.set)

left_canvas.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
left_scrollbar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

def _on_mousewheel(event):
    left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

left_canvas.bind_all("<MouseWheel>", _on_mousewheel)

right = ttk.Frame(main)
right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

ttk.Label(left, text="BudgetPilot", font=("Sans", 18, "bold")).pack(anchor="w", pady=(0, 10))

box = ttk.LabelFrame(left, text="Suma na účte a rezerva")
box.pack(fill=tk.X, pady=5)

settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})

balance_entry = ttk.Entry(box)
balance_entry.insert(0, str(settings.get("account_balance", 0)))
balance_entry.pack(fill=tk.X, padx=8, pady=5)

reserve_enabled = tk.BooleanVar(value=bool(settings.get("use_reserve", False)))
ttk.Checkbutton(
    box,
    text="Mám rezervu bokom a nechcem ju rátať do míňania",
    variable=reserve_enabled
).pack(fill=tk.X, padx=8, pady=3)

reserve_entry = ttk.Entry(box)
reserve_entry.insert(0, str(settings.get("safe_min", 0)))
reserve_entry.pack(fill=tk.X, padx=8, pady=3)

ttk.Label(
    box,
    text="Rezerva = peniaze naozaj bokom. Ak ich nemáš, nechaj vypnuté."
).pack(anchor="w", padx=8)

ttk.Button(box, text="Uložiť účet/rezervu", command=save_balance).pack(fill=tk.X, padx=8, pady=5)

income_box = ttk.LabelFrame(left, text="Príjem")
income_box.pack(fill=tk.X, pady=5)

income_type = ttk.Combobox(income_box, values=["Výplata netto", "Výplata 2", "Brigáda", "Iný príjem"])
income_type.set("Výplata netto")
income_type.pack(fill=tk.X, padx=8, pady=3)

income_amount = ttk.Entry(income_box)
income_amount.insert(0, "2000")
income_amount.pack(fill=tk.X, padx=8, pady=3)

income_day = ttk.Spinbox(income_box, from_=1, to=31)
income_day.set("15")
income_day.pack(fill=tk.X, padx=8, pady=3)

row_income_btn = ttk.Frame(income_box)
row_income_btn.pack(fill=tk.X, padx=8, pady=5)
ttk.Button(row_income_btn, text="Pridať", command=add_income).pack(side=tk.LEFT, fill=tk.X, expand=True)
ttk.Button(row_income_btn, text="Uložiť úpravu", command=update_income).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

payment_box = ttk.LabelFrame(left, text="Pravidelná platba")
payment_box.pack(fill=tk.X, pady=5)

payment_type = ttk.Combobox(payment_box, values=list(PAYMENT_PRESETS.keys()), state="readonly")
payment_type.set("Hypotéka")
payment_type.bind("<<ComboboxSelected>>", preset_changed)
payment_type.pack(fill=tk.X, padx=8, pady=3)

payment_name_var = tk.StringVar(value="Hypotéka")
payment_name = ttk.Entry(payment_box, textvariable=payment_name_var)
payment_name.pack(fill=tk.X, padx=8, pady=3)

payment_amount = ttk.Entry(payment_box)
payment_amount.insert(0, "820")
payment_amount.pack(fill=tk.X, padx=8, pady=3)

date_row = ttk.Frame(payment_box)
date_row.pack(fill=tk.X, padx=8, pady=3)

payment_day = ttk.Spinbox(date_row, from_=1, to=31, width=5)
payment_day.set("20")
payment_day.pack(side=tk.LEFT)

payment_month = ttk.Spinbox(date_row, from_=1, to=12, width=5)
payment_month.set("1")
payment_month.pack(side=tk.LEFT, padx=5)

payment_year = ttk.Spinbox(date_row, from_=2026, to=2040, width=7)
payment_year.set("2026")
payment_year.pack(side=tk.LEFT)

payment_freq_label = ttk.Combobox(payment_box, values=list(FREQ_LABELS.keys()), state="readonly")
payment_freq_label.set("Mesačne")
payment_freq_label.bind("<<ComboboxSelected>>", freq_changed)
payment_freq_label.pack(fill=tk.X, padx=8, pady=3)

payment_every = ttk.Entry(payment_box)
payment_every.pack(fill=tk.X, padx=8, pady=3)

ttk.Label(payment_box, text="Dátum: deň / mesiac / rok začiatku alebo splatnosti").pack(anchor="w", padx=8)

row_pay_btn = ttk.Frame(payment_box)
row_pay_btn.pack(fill=tk.X, padx=8, pady=5)
ttk.Button(row_pay_btn, text="Pridať", command=add_payment).pack(side=tk.LEFT, fill=tk.X, expand=True)
ttk.Button(row_pay_btn, text="Uložiť úpravu", command=update_payment).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

lists_box = ttk.LabelFrame(left, text="Zadané položky")
lists_box.pack(fill=tk.BOTH, pady=5)

ttk.Label(lists_box, text="Príjmy").pack(anchor="w", padx=8)
income_list = tk.Listbox(lists_box, height=4)
income_list.pack(fill=tk.X, padx=8, pady=3)
income_list.bind("<<ListboxSelect>>", on_income_select)

ttk.Button(lists_box, text="Zmazať vybraný príjem", command=delete_selected_income).pack(fill=tk.X, padx=8, pady=3)

ttk.Label(lists_box, text="Platby").pack(anchor="w", padx=8)
payment_list = tk.Listbox(lists_box, height=8)
payment_list.pack(fill=tk.X, padx=8, pady=3)
payment_list.bind("<<ListboxSelect>>", on_payment_select)

ttk.Button(lists_box, text="Zmazať vybranú platbu", command=delete_selected_payment).pack(fill=tk.X, padx=8, pady=3)


expense_box = ttk.LabelFrame(left, text="Výdavok navyše")
expense_box.pack(fill=tk.X, pady=5)

expense_name = ttk.Combobox(
    expense_box,
    values=["Potraviny", "Nafta", "Večera", "Deti", "Lekáreň", "Oblečenie", "Iné"]
)
expense_name.set("Potraviny")
expense_name.pack(fill=tk.X, padx=8, pady=3)

expense_amount = ttk.Entry(expense_box)
expense_amount.insert(0, "50")
expense_amount.pack(fill=tk.X, padx=8, pady=3)

expense_category = ttk.Combobox(
    expense_box,
    values=["jedlo", "auto", "zábava", "deti", "zdravie", "domácnosť", "iné"]
)
expense_category.set("jedlo")
expense_category.pack(fill=tk.X, padx=8, pady=3)

expense_date = ttk.Entry(expense_box)
expense_date.insert(0, __import__("datetime").date.today().isoformat())
expense_date.pack(fill=tk.X, padx=8, pady=3)

ttk.Button(expense_box, text="Pridať výdavok navyše", command=add_expense).pack(fill=tk.X, padx=8, pady=5)

spend_box = ttk.LabelFrame(left, text="Môžem minúť?")
spend_box.pack(fill=tk.X, pady=5)

spend_entry = ttk.Entry(spend_box)
spend_entry.insert(0, "50")
spend_entry.pack(fill=tk.X, padx=8, pady=5)

ttk.Button(spend_box, text="Otestovať výdavok", command=spend_test).pack(fill=tk.X, padx=8, pady=5)

ttk.Button(left, text="Obnoviť prehľad", command=refresh_all).pack(fill=tk.X, pady=5)
ttk.Button(left, text="Reset príjmov a platieb", command=clear_all).pack(fill=tk.X, pady=5)

output = tk.Text(right, wrap=tk.WORD, font=("Monospace", 11))
output.pack(fill=tk.BOTH, expand=True)

preset_changed()
refresh_all()
root.mainloop()
