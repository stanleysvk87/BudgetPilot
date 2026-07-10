#!/usr/bin/env python3
"""First-run setup wizard for BudgetPilot.

Balance-first model:
- current account balance is the source of truth
- salary/income is optional and not required
- recurring payments are required for a useful forecast
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import redirect, render_template_string, request


BASE = Path(__file__).resolve().parent
DATA = BASE / "data"


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _to_float(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", ".").strip() or default)
    except Exception:
        return float(default)


def _to_int(value, default=1) -> int:
    try:
        n = int(float(str(value).replace(",", ".").strip() or default))
        return max(1, min(31, n))
    except Exception:
        return int(default)


def _needs_first_run() -> bool:
    settings = _read_json(DATA / "settings.json", {})
    payments = _read_json(DATA / "payments.json", [])

    if not isinstance(settings, dict):
        settings = {}
    if not isinstance(payments, list):
        payments = []

    has_balance = "account_balance" in settings or "real_balance" in settings
    has_payments = len(payments) > 0

    # Income/payday is intentionally not required.
    return not (has_balance and has_payments)


SETUP_HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BudgetPilot - prvé nastavenie</title>
<style>
:root{
  --bg:#020617; --panel:#111827; --card:#1f2937; --line:#334155;
  --text:#e5e7eb; --muted:#94a3b8; --blue:#2563eb; --green:#16a34a;
}
*{box-sizing:border-box}
body{
  margin:0; min-height:100vh; color:var(--text);
  font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:radial-gradient(circle at top left,#1e3a8a 0,#0f172a 38%,#020617 100%);
}
.wrap{max-width:980px;margin:0 auto;padding:22px}
.hero,.card{
  background:rgba(15,23,42,.84); border:1px solid rgba(148,163,184,.2);
  border-radius:24px; padding:20px; margin-bottom:16px;
  box-shadow:0 22px 70px rgba(0,0,0,.30)
}
h1{margin:0 0 8px;font-size:32px}
h2{margin:0 0 14px;font-size:21px}
p{color:var(--muted);line-height:1.45}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.paygrid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:8px;align-items:end;margin-bottom:8px}
label{display:block;color:var(--muted);font-size:13px;margin:0 0 6px}
input,select{
  width:100%; padding:12px 13px; border-radius:13px; border:1px solid var(--line);
  background:#020617; color:var(--text); font-size:15px
}
button{
  width:100%; padding:15px 18px; border:0; border-radius:16px;
  color:white; background:var(--blue); font-weight:800; font-size:16px
}
.hint{font-size:13px;color:var(--muted)}
.warn{color:#fbbf24}
@media(max-width:760px){
  .wrap{padding:12px}
  h1{font-size:26px}
  .grid,.paygrid{grid-template-columns:1fr}
  .card,.hero{border-radius:18px;padding:15px}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>BudgetPilot - prvé nastavenie</h1>
    <p>
      Základ je aktuálny stav účtu, ktorý zadáš ručne. Výplata sa nepočíta automaticky,
      pretože môže mať inú sumu aj dátum. Appka počíta odhad zo zadaného zostatku
      mínus nezaplatené platby.
    </p>
  </div>

  <form method="post">
    <div class="card">
      <h2>1. Aktuálny stav</h2>
      <div class="grid">
        <div>
          <label>Aktuálny stav účtu</label>
          <input name="account_balance" inputmode="decimal" placeholder="napr. 2520" required>
        </div>
        <div>
          <label>Rezerva bokom, voliteľné</label>
          <input name="reserve_amount" inputmode="decimal" placeholder="napr. 300" value="0">
        </div>
      </div>
      <p class="hint">
        Tento stav účtu je zdroj pravdy. Po výplate alebo po väčšej zmene ho ručne prepíš.
      </p>
    </div>

    <div class="card">
      <h2>2. Trvalé platby</h2>
      <p class="hint">
        Zadaj všetko, čo sa platí pravidelne. Platba bude nezaplatená, kým ju ručne nepotvrdíš.
        Dátum splatnosti nikdy neznamená automaticky zaplatené.
      </p>

      {% for i in range(1, 13) %}
      <div class="paygrid">
        <div>
          <label>Platba {{ i }} - názov</label>
          <input name="pay_name_{{ i }}" placeholder="napr. hypotéka, elektrina, internet">
        </div>
        <div>
          <label>Suma</label>
          <input name="pay_amount_{{ i }}" inputmode="decimal" placeholder="0">
        </div>
        <div>
          <label>Deň splatnosti</label>
          <input name="pay_day_{{ i }}" type="number" min="1" max="31" placeholder="20">
        </div>
        <div>
          <label>Priorita</label>
          <select name="pay_priority_{{ i }}">
            <option value="mandatory">nutné</option>
            <option value="important">dôležité</option>
            <option value="flexible">dá sa posunúť</option>
            <option value="optional">voliteľné</option>
          </select>
        </div>
        <div>
          <label>Flexibilita</label>
          <select name="pay_flexibility_{{ i }}">
            <option value="hard_due">pevný termín</option>
            <option value="can_defer">dá sa odložiť</option>
            <option value="optional">voliteľné</option>
          </select>
        </div>
      </div>
      {% endfor %}
    </div>

    <button type="submit">Uložiť nastavenie</button>
  </form>
</div>
</body>
</html>
"""


def register_first_run_wizard(app):
    @app.before_request
    def _first_run_gate():
        if request.endpoint in {"first_run_setup", "static"}:
            return None
        if request.path.startswith("/static"):
            return None
        if _needs_first_run():
            return redirect("/setup/full")
        return None

    @app.route("/setup/full", methods=["GET", "POST"], endpoint="first_run_setup")
    def first_run_setup():
        if request.method == "GET":
            return render_template_string(SETUP_HTML, range=range)

        today = date.today()
        now = datetime.now().isoformat(timespec="seconds")
        current_month = f"{today.year:04d}-{today.month:02d}"
        current_start_date = f"{current_month}-01"

        balance = _to_float(request.form.get("account_balance"), 0)
        reserve = _to_float(request.form.get("reserve_amount"), 0)

        settings = {
            "account_balance": balance,
            "real_balance": balance,
            "use_reserve": reserve > 0,
            "reserve_amount": reserve,
            "safe_min": reserve if reserve > 0 else 0,
            "payday_day": today.day,
            "setup_complete": True,
            "setup_date": today.isoformat(),
            "last_manual_review": now,
            "manual_confirmation_required": True,
            "balance_first": True,
            "income_required": False,
            "data_profile": "real_runtime",
        }

        payments = []
        for i in range(1, 13):
            name = (request.form.get(f"pay_name_{i}") or "").strip()
            amount = _to_float(request.form.get(f"pay_amount_{i}"), 0)
            day = _to_int(request.form.get(f"pay_day_{i}"), today.day)

            if not name or amount <= 0:
                continue

            priority = request.form.get(f"pay_priority_{i}") or "mandatory"
            flexibility = request.form.get(f"pay_flexibility_{i}") or "hard_due"

            payments.append({
                "id": "payment-" + uuid.uuid4().hex[:8],
                "name": name,
                "amount": amount,
                "day": day,
                "due_day": day,
                "frequency": "monthly",
                "start": current_start_date,
                "start_month": current_month,
                "priority": priority,
                "flexibility": flexibility,
                "active": True,
            })

        _write_json(DATA / "settings.json", settings)
        _write_json(DATA / "incomes.json", [])
        _write_json(DATA / "payments.json", payments)
        _write_json(DATA / "payment_events.json", [])
        _write_json(DATA / "expenses.json", [])
        _write_json(DATA / "snapshots.json", [{
            "date": today.isoformat(),
            "real_balance": balance,
            "reserve_amount": reserve,
            "note": "first_run_balance_first_setup",
        }])

        for optional_name in ["envelopes.json", "debts.json", "one_time_obligations.json", "receipts.json"]:
            path = DATA / optional_name
            if not path.exists():
                _write_json(path, [])

        return redirect("/?v=balance-first-setup")
