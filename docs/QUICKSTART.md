# Quickstart

The minimal steps to get BudgetPilot running locally.

```bash
git clone <this-repo>
cd BudgetPilot
pip install flask
python3 budgetpilot_web.py
```

Open `http://localhost:8765` in your browser. That's it — BudgetPilot ships
with a first-run setup flow for entering your own balance and recurring
payments.

To try the fake demo data instead:

```bash
mkdir -p data
cp data.example/*.json data/
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

First thing to do with your own numbers: open the dashboard, follow the
"first-run setup" banner (or go straight to `http://localhost:8765/setup`)
to enter your real account balance, payday day of month, and recurring
bills. See [USAGE.md](USAGE.md) for what each field means.

For install details (Python version, virtualenv, troubleshooting), see
[INSTALL.md](INSTALL.md).
