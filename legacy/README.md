# Legacy Files

This folder contains early BudgetPilot experiments kept for historical
reference only.

They are not part of the supported app path. The supported entry points are:

```bash
python3 budgetpilot.py
python3 budgetpilot_web.py
```

Contents:

- `budgetpilot_gui*.py` — older Tkinter prototypes.
- `add_gui_lists.py` — one-off patch script for an older Tkinter GUI.
- `fix_*.py` — one-off patch scripts from early local iterations.
- `rollback_latest.sh` — old backup restore helper.

Some files in this folder write directly to `~/BudgetPilot` and may not match
the current data model. Do not run them on a live BudgetPilot setup unless
you have read the script and backed up your data.
