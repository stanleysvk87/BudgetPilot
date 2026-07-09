from pathlib import Path

file = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = file.read_text()

old = "if year == TODAY.year and month == TODAY.month:"
new = "if True:"

code = code.replace(old, new)

file.write_text(code)
print("✔ FIXED: počítajú sa všetky platby (nie len budúce)")
