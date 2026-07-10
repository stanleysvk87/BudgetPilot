from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = f.read_text()

old = "after = r[\"real_available\"] - amount"
new = """SAFE_MIN = 500
    usable_before = r["real_available"] - SAFE_MIN
    after = usable_before - amount"""

code = code.replace(old, new)

old2 = 'per_day = after / r["days_to_income"]'
new2 = 'per_day = after / r["days_to_income"] if after > 0 else 0'

code = code.replace(old2, new2)

f.write_text(code)
print("✔ spend používa safety buffer")
