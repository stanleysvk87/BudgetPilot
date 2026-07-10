#!/usr/bin/env bash
set -e
cd ~/BudgetPilot

BP=$(ls -1t backups/budgetpilot.py.*.bak 2>/dev/null | head -1 || true)
WEB=$(ls -1t backups/budgetpilot_web.py.*.bak 2>/dev/null | head -1 || true)
DATA=$(ls -1td backups/data.*.bak 2>/dev/null | head -1 || true)

[ -n "$BP" ] && cp "$BP" budgetpilot.py
[ -n "$WEB" ] && cp "$WEB" budgetpilot_web.py
[ -n "$DATA" ] && rm -rf data && cp -a "$DATA" data

echo "Rollback hotový."
