from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = f.read_text()

# vlož safe minimum
code = code.replace(
    "daily_limit = real_available / days_to_income",
    "SAFE_MIN = 500\n        usable = real_available - SAFE_MIN\n        daily_limit = usable / days_to_income if usable > 0 else 0"
)

f.write_text(code)
print("✔ pridaný safety buffer")
