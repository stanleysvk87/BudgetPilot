from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot_gui.py"
code = f.read_text()

insert_after = '''def clear_all():
    if not messagebox.askyesno("Reset", "Naozaj vymazať príjmy a platby?"):
        return
    save(INCOMES, [])
    save(PAYMENTS, [])
    refresh_output()
'''

extra = r'''
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

def delete_selected_income():
    sel = income_list.curselection()
    if not sel:
        return
    idx = sel[0]
    data = load(INCOMES, [])
    if idx < len(data):
        removed = data.pop(idx)
        save(INCOMES, data)
        refresh_all()
        messagebox.showinfo("Zmazané", f"Zmazané: {removed.get('name')}")

def delete_selected_payment():
    sel = payment_list.curselection()
    if not sel:
        return
    idx = sel[0]
    data = load(PAYMENTS, [])
    if idx < len(data):
        removed = data.pop(idx)
        save(PAYMENTS, data)
        refresh_all()
        messagebox.showinfo("Zmazané", f"Zmazané: {removed.get('name')}")
'''

code = code.replace(insert_after, insert_after + extra)

code = code.replace('refresh_output()', 'refresh_all()', 1)
code = code.replace('refresh_output()', 'refresh_all()', 1)
code = code.replace('refresh_output()', 'refresh_all()', 1)
code = code.replace('refresh_output()', 'refresh_all()', 1)

panel = r'''
lists_box = ttk.LabelFrame(left, text="Zadané položky")
lists_box.pack(fill=tk.BOTH, pady=5)

ttk.Label(lists_box, text="Príjmy").pack(anchor="w", padx=8)
income_list = tk.Listbox(lists_box, height=4)
income_list.pack(fill=tk.X, padx=8, pady=3)
ttk.Button(lists_box, text="Zmazať vybraný príjem", command=delete_selected_income).pack(fill=tk.X, padx=8, pady=3)

ttk.Label(lists_box, text="Platby").pack(anchor="w", padx=8)
payment_list = tk.Listbox(lists_box, height=8)
payment_list.pack(fill=tk.X, padx=8, pady=3)
ttk.Button(lists_box, text="Zmazať vybranú platbu", command=delete_selected_payment).pack(fill=tk.X, padx=8, pady=3)
'''

code = code.replace(
    'ttk.Button(left, text="Obnoviť prehľad", command=refresh_output).pack(fill=tk.X, pady=5)',
    panel + '\nttk.Button(left, text="Obnoviť prehľad", command=refresh_all).pack(fill=tk.X, pady=5)'
)

code = code.replace('preset_changed()\nrefresh_output()', 'preset_changed()\nrefresh_all()')

f.write_text(code)
print("OK - pridaný zoznam a mazanie")
