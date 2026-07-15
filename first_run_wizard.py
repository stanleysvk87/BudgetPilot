#!/usr/bin/env python3
"""First-run setup wizard for BudgetPilot.

Balance-first model:
- current account balance is the source of truth
- salary/income is optional and not required
- recurring payments are required for a useful forecast
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path

from flask import redirect, render_template_string, request
from paths import app_base, data_dir
import json_store


BASE = app_base()
DATA = data_dir()


def _read_json(path: Path, default):
    return json_store.read_json(path, default)


def _write_json(path: Path, value) -> None:
    json_store.atomic_write_json(path, value)


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


def _resolve_path(value, default: Path) -> Path:
    if callable(value):
        value = value()
    return Path(value) if value is not None else default


def _needs_first_run(settings_path=None, payments_path=None) -> bool:
    settings = _read_json(_resolve_path(settings_path, DATA / "settings.json"), {})
    payments = _read_json(_resolve_path(payments_path, DATA / "payments.json"), [])

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
.paygrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;align-items:end;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(148,163,184,.14)}
.paygrid.optional-row{display:none}
.show-all-payments .paygrid.optional-row{display:grid}
label{display:block;color:var(--muted);font-size:13px;margin:0 0 6px}
input,select{
  width:100%; padding:12px 13px; border-radius:13px; border:1px solid var(--line);
  background:#020617; color:var(--text); font-size:15px
}
button{
  width:100%; padding:15px 18px; border:0; border-radius:16px;
  color:white; background:var(--blue); font-weight:800; font-size:16px
}
.secondary-btn{background:#334155}
.mini-status{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0 2px}
.mini-status div{border:1px solid rgba(148,163,184,.18);border-radius:16px;padding:12px;background:rgba(2,6,23,.34)}
.mini-status strong{display:block;font-size:18px}
.mini-status span{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.hint{font-size:13px;color:var(--muted)}
.warn{color:#fbbf24}
.language-switch{position:fixed;top:14px;right:14px;display:flex;gap:6px;z-index:2}
.language-switch a{color:#e5e7eb;text-decoration:none;border:1px solid rgba(148,163,184,.35);
border-radius:999px;padding:7px 10px;font-size:12px;font-weight:800;background:rgba(15,23,42,.86)}
.language-switch a.active{background:#2563eb;border-color:#93c5fd}
@media(max-width:760px){
  .wrap{padding:12px}
  h1{font-size:26px}
  .grid,.paygrid,.mini-status{grid-template-columns:1fr}
  .card,.hero{border-radius:18px;padding:15px}
}
</style>
</head>
<body>
<div class="language-switch" aria-label="Language">
  <a href="/language/sk?next=/setup/full" class="{% if current_language() == 'sk' %}active{% endif %}">SK</a>
  <a href="/language/en?next=/setup/full" class="{% if current_language() == 'en' %}active{% endif %}">EN</a>
</div>
<div class="wrap">
  <div class="hero">
    <h1>BudgetPilot - prvé nastavenie</h1>
    <p>
      Začni aktuálnym stavom účtu a najväčšími pravidelnými platbami.
      Ostatné vieš doplniť neskôr, keď bude základný prehľad sedieť.
    </p>
    <div class="mini-status" aria-label="Kroky nastavenia">
      <div><strong>1</strong><span>stav účtu</span></div>
      <div><strong>2</strong><span>hlavné platby</span></div>
      <div><strong>3</strong><span>uložiť prehľad</span></div>
    </div>
  </div>

  <form method="post">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
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
        Stačí zadať najväčšie pravidelné platby. Každá bude nezaplatená,
        kým ju ručne nepotvrdíš.
      </p>

      {% for i in range(1, 13) %}
      <div class="paygrid{% if i > 3 %} optional-row{% endif %}">
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
          <label>Mesiac štartu</label>
          <input name="pay_month_{{ i }}" type="number" min="1" max="12" placeholder="{{ current_month_num }}">
        </div>
        <div>
          <label>Opakovanie</label>
          <select name="pay_frequency_{{ i }}">
            <option value="monthly">mesačne</option>
            <option value="quarterly">štvrťročne</option>
            <option value="yearly">ročne</option>
            <option value="custom_months">vlastné (každých X mes.)</option>
            <option value="once">jednorazovo</option>
          </select>
        </div>
        <div>
          <label>Ak vlastné: každých X mes.</label>
          <input name="pay_every_months_{{ i }}" type="number" min="2" max="60" placeholder="napr. 24">
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
      <button type="button" class="secondary-btn" id="show-more-payments">Pridať ďalšie platby</button>
    </div>

    <button type="submit">Uložiť nastavenie</button>
  </form>
</div>
<script>
document.addEventListener("DOMContentLoaded", function(){
  var btn = document.getElementById("show-more-payments");
  if(!btn) return;
  btn.addEventListener("click", function(){
    document.body.classList.add("show-all-payments");
    btn.hidden = true;
  });
});
</script>
</body>
</html>
"""


def register_first_run_wizard(app, data_path=None, settings_path=None, payments_path=None):
    @app.before_request
    def _first_run_gate():
        if request.endpoint in {
            "first_run_setup", "auth_setup", "auth_login", "logout", "logout_get",
            "settings_restore", "set_language", "static",
        }:
            return None
        if request.path.startswith("/static"):
            return None
        if _needs_first_run(settings_path=settings_path, payments_path=payments_path):
            return redirect("/setup/full")
        return None

    @app.route("/setup/full", methods=["GET", "POST"], endpoint="first_run_setup")
    def first_run_setup():
        if request.method == "GET":
            return render_template_string(SETUP_HTML, range=range, current_month_num=date.today().month)

        today = date.today()
        now = datetime.now().isoformat(timespec="seconds")
        data_root = _resolve_path(data_path, DATA)

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
            frequency = request.form.get(f"pay_frequency_{i}") or "monthly"
            if frequency not in {"monthly", "quarterly", "yearly", "custom_months", "once"}:
                frequency = "monthly"

            start_month_num = _to_int(request.form.get(f"pay_month_{i}"), today.month)
            start_month_num = max(1, min(12, start_month_num))
            start = f"{today.year:04d}-{start_month_num:02d}-{day:02d}"

            item = {
                "id": "payment-" + uuid.uuid4().hex[:8],
                "name": name,
                "amount": amount,
                "day": day,
                "due_day": day,
                "frequency": frequency,
                "start": start,
                "start_month": start[:7],
                "priority": priority,
                "flexibility": flexibility,
                "active": True,
            }
            if frequency == "custom_months":
                item["every_months"] = max(2, _to_int(request.form.get(f"pay_every_months_{i}"), 2))

            payments.append(item)

        _write_json(data_root / "settings.json", settings)
        _write_json(data_root / "incomes.json", [])
        _write_json(data_root / "payments.json", payments)
        _write_json(data_root / "payment_events.json", [])
        _write_json(data_root / "expenses.json", [])
        _write_json(data_root / "snapshots.json", [{
            "date": today.isoformat(),
            "real_balance": balance,
            "reserve_amount": reserve,
            "note": "first_run_balance_first_setup",
        }])

        for optional_name in ["envelopes.json", "debts.json", "one_time_obligations.json", "receipts.json"]:
            path = data_root / optional_name
            if not path.exists():
                _write_json(path, [])

        return redirect("/?v=balance-first-setup")
