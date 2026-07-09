from pathlib import Path

f = Path.home() / "BudgetPilot" / "budgetpilot.py"
code = f.read_text()

old = """    if after < 0:
        print("Verdikt: PROBLÉM")
    elif per_day is not None and per_day < 15:
        print("Verdikt: POZOR")
    elif after < 100:
        print("Verdikt: POZOR")
    else:
        print("Verdikt: OK")"""

new = """    if after < 0:
        print("Verdikt: ❌ Nedávaj to. Chýbajú peniaze.")
    elif per_day is not None and per_day < 15:
        print("Verdikt: ⚠️ Radšej nie. Pôjdeš na doraz.")
    elif per_day is not None and per_day < 30:
        print("Verdikt: 🤏 Môžeš, ale nepreháňaj.")
    else:
        print("Verdikt: ✅ Kľudne.")"""

code = code.replace(old, new)

f.write_text(code)
print("✔ realistický verdict hotový")
