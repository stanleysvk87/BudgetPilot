# Quickstart

The minimal steps to get BudgetPilot running locally.

```bash
git clone https://github.com/stanleysvk87/BudgetPilot.git
cd BudgetPilot
pip install -r requirements.txt
python3 budgetpilot_web.py
```

Open `http://localhost:8765` in your browser. That's it — BudgetPilot ships
with a first-run local administrator setup followed by the financial setup
flow for entering your own balance and recurring payments.

To try the fake demo data instead:

```bash
python3 scripts/load_demo_data.py
python3 budgetpilot_web.py
```

To use the CLI instead of (or alongside) the web UI:

```bash
python3 budgetpilot.py
```

To check whether a purchase fits your safe-to-spend amount:

```bash
python3 budgetpilot.py spend 20
```

First thing to do with your own numbers: create the local administrator,
then follow the financial setup flow to enter your real account balance,
payday day of month, and recurring bills. See [USAGE.md](USAGE.md) for what
each field means.

For install details (Python version, virtualenv, troubleshooting), see
[INSTALL.md](INSTALL.md).
