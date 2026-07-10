from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = f.read_text()

code = code.replace(
    'print(f"Voľné pred výdavkom:    {r[\'real_available\']:.2f} €")',
    'SAFE_MIN = 500\n    usable_before = r["real_available"] - SAFE_MIN\n    print(f"Použiteľné peniaze:     {usable_before:.2f} €")'
)

f.write_text(code)
print("✔ output opravený")
