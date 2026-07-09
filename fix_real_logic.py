from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = f.read_text()

old = "real_available = account_balance + future_income - future_required"
new = "real_available = account_balance - payment_total - expense_total + income_total"

code = code.replace(old, new)

f.write_text(code)
print("✔ FIXED: real_available = realita mesiaca")
