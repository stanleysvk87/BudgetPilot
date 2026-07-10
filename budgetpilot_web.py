#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from datetime import date, datetime
from urllib.parse import urlparse
from flask import Flask, abort, request, redirect, render_template_string, send_file

import obligations as ob
import receipts
import payment_events as pe
import envelopes as env
import budgetpilot as bp
import audit_log
from forecast import payment_state, PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED

BASE = Path.home() / "BudgetPilot"
DATA = BASE / "data"
SETTINGS = DATA / "settings.json"
INCOMES = DATA / "incomes.json"
PAYMENTS = DATA / "payments.json"
EXPENSES = DATA / "expenses.json"
SNAPSHOTS = DATA / "snapshots.json"
ENVELOPES = DATA / "envelopes.json"
DEBTS = DATA / "debts.json"
ONETIME = DATA / "onetime.json"
RECEIPTS_DIR = DATA / "receipts"
AUDIT_LOG_PATH = DATA / "audit_log.json"

AUDIT_ACTION_LABEL = {
    "balance_updated": "Stav účtu upravený",
    "payment_paid": "Platba označená ako zaplatená",
    "payment_deferred": "Platba odložená",
    "envelope_amount_changed": "Suma obálky upravená",
    "ocr_expense_saved": "Výdavok z účtenky uložený",
    "expense_added": "Výdavok pridaný",
}


def log_audit(action, detail=""):
    audit_log.log_action(AUDIT_LOG_PATH, action, detail)

def _with_day_and_time(entries):
    # "at" is an ISO datetime string (audit_log.log_action) -- split it once
    # here so the History view can group entries by day without a Jinja
    # groupby-on-a-slice, which isn't supported.
    for e in entries:
        at = e.get("at") or ""
        e["day"] = at[:10] if len(at) >= 10 else at
        e["time"] = at[11:16] if len(at) >= 16 else ""
    return entries

PRIORITY_LABEL = {
    "mandatory": "nevyhnutná",
    "important": "dôležitá",
    "flexible": "flexibilná",
    "optional": "voliteľná",
}

MONTH_NAME_SK = {
    1: "január", 2: "február", 3: "marec", 4: "apríl", 5: "máj", 6: "jún",
    7: "júl", 8: "august", 9: "september", 10: "október", 11: "november", 12: "december",
}

DATA.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)

from balance_first_summary import register_balance_first_summary
register_balance_first_summary(app)

from envelope_editor import register_envelope_editor
register_envelope_editor(app)

from first_run_wizard import register_first_run_wizard
register_first_run_wizard(app)

PAYMENT_TYPES = ["Hypotéka","Nájom","Elektrina","Voda","Plyn","Internet","Paušál","PZP","Havarijná poistka","STK","Olej + filtre","Diaľničná známka","Iné"]
EXPENSE_TYPES = ["Rýchly výdavok","Potraviny","Nafta","Večera","Deti","Lekáreň","Oblečenie","Domácnosť","Iné"]

FREQ_LABEL = {
    "monthly": "mesačne",
    "quarterly": "štvrťročne",
    "yearly": "ročne",
    "custom_months": "vlastné",
    "once": "jednorazovo"
}

STATE_LABEL = {
    PENDING: "Nezaplatené",
    PAID_ME: "Zaplatené z účtu",
    PAID_OTHER: "Zaplatil niekto iný",
    PAID_RESERVE: "Zaplatené z rezervy",
    DEFERRED: "Odložené",
}
STATE_BADGE_CLASS = {
    PENDING: "",
    PAID_ME: "ok",
    PAID_OTHER: "ok",
    PAID_RESERVE: "ok",
    DEFERRED: "warn",
}
# States settable directly from the dropdown; deferred has its own
# "Odložiť o 7 dní" button since it needs a computed deferred_to date.
SELECTABLE_STATES = [PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE]

URGENCY_LABEL_SK = {
    pe.OVERDUE: "Po termíne",
    pe.DUE_TODAY: "Dnes",
    pe.SOON: "Čoskoro",
    pe.LATER: "Neskôr",
}

DEBT_STATE_LABEL = {
    PENDING: "Nesplatené",
    PAID_ME: "Splatené",
    DEFERRED: "Odložené",
    ob.RECEIVED: "Prijaté",
}
# Selectable states per direction — I_owe follows the payment lifecycle,
# owed_to_me only ever resolves to "received" (see obligations.set_debt_state).
DEBT_STATES_BY_DIRECTION = {
    ob.I_OWE: [PENDING, PAID_ME, DEFERRED],
    ob.OWED_TO_ME: [PENDING, ob.RECEIVED],
}
DEBT_DIRECTION_LABEL = {
    ob.I_OWE: "Dlžím ja",
    ob.OWED_TO_ME: "Dlžia mne",
}

def load(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, indent=2, ensure_ascii=False))
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def go_home():
    """Return to whichever view the action was submitted from (e.g. an
    envelope edit on /envelopes redirects back to /envelopes, not the
    dashboard), falling back to / when there's no usable referrer. Only
    ever redirects to a local path — never follows an external referrer."""
    ref = request.referrer
    if ref:
        path = urlparse(ref).path
        if path.startswith("/"):
            return redirect(path)
    return redirect("/")

def run_core(args=None):
    try:
        cmd = [str(BASE / "budgetpilot.py")]
        if args:
            cmd += args
        return subprocess.check_output(cmd, text=True)
    except Exception as e:
        return f"CHYBA:\n{e}"

def parse_dash(core):
    d = {
        "money": "-", "day": "-", "status": "-", "status_class": "ok",
        "balance": "-", "unpaid_total": "-", "shortfall": "-",
        "projected_after_payday": "-", "next_payday": "-",
    }
    for line in core.splitlines():
        if "Suma na účte teraz" in line:
            d["balance"] = line.split(":", 1)[1].strip()
        elif "Nezaplatené do výplaty" in line:
            d["unpaid_total"] = line.split(":", 1)[1].strip()
        elif "Chýba do výplaty" in line:
            d["shortfall"] = line.split(":", 1)[1].strip()
        elif "Odhad po najbližšej výplate" in line:
            d["projected_after_payday"] = line.split(":", 1)[1].strip()
        elif "Ďalšia výplata" in line:
            d["next_payday"] = line.split(":", 1)[1].strip()
        elif "Bezpečne minúť teraz" in line:
            d["money"] = line.split(":", 1)[1].strip()
        elif "Na deň" in line:
            d["day"] = line.split(":", 1)[1].strip()
        elif "Stav" in line:
            d["status"] = line.split(":", 1)[1].strip()

    if "PROBLÉM" in d["status"]:
        d["status_class"] = "bad"
    elif "POZOR" in d["status"]:
        d["status_class"] = "warn"
    else:
        d["status_class"] = "ok"
    return d

def payment_form_from_item(item=None):
    if not item:
        return {"type":"Hypotéka","name":"","amount":"","day":"1","month":"1","year":"2026","frequency":"monthly","every_months":""}
    start = item.get("start", "2026-01-01")
    try:
        y, m, d = start.split("-")
    except Exception:
        y, m, d = "2026", "1", str(item.get("day", 1))
    name = item.get("name", "")
    typ = name if name in PAYMENT_TYPES else "Iné"
    return {
        "type": typ,
        "name": name if typ == "Iné" else "",
        "amount": item.get("amount", ""),
        "day": item.get("day", d),
        "month": int(m),
        "year": int(y),
        "frequency": item.get("frequency", "monthly"),
        "every_months": item.get("every_months", "")
    }

HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BudgetPilot</title>
<style>
:root{--bg:#0f172a;--card:#1f2937;--line:#374151;--text:#e5e7eb;--muted:#9ca3af;--blue:#2563eb;--red:#b91c1c;--green:#22c55e;--orange:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#0f172a,#111827);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.app{display:grid;grid-template-columns:370px 1fr;gap:18px;padding:18px}
.table-scroll{overflow-x:auto}
.sidebar{display:flex;flex-direction:column;gap:14px}
.card{background:rgba(31,41,55,.95);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.25)}
h1{font-size:28px;margin:0 0 6px} h2{font-size:20px;margin:0 0 14px}
label{display:block;margin-top:8px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #4b5563;background:#0b1220;color:var(--text);margin-top:6px}
button{padding:10px 14px;border:0;border-radius:12px;background:var(--blue);color:white;font-weight:700;cursor:pointer}
.danger{background:var(--red)} .secondary{background:#4b5563}
.btn-row{display:flex;gap:8px;margin-top:10px}.btn-row button{flex:1}
.topgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.metric .label{font-size:13px;color:var(--muted)} .metric .value{font-size:32px;font-weight:900;margin-top:4px}
.ok{color:var(--green)} .warn{color:var(--orange)} .bad{color:var(--red)}
.main{display:flex;flex-direction:column;gap:14px}
table{width:100%;border-collapse:collapse} th,td{padding:11px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px} th{color:var(--muted);font-size:13px}
.actions{display:flex;gap:6px;justify-content:flex-end}.actions form{margin:0}
.actions-stack{display:flex;flex-direction:column;gap:6px;align-items:stretch;min-width:160px}.actions-stack form{margin:0}.actions-stack select{margin:0}
.small{font-size:13px;color:var(--muted);line-height:1.35}.inline{display:grid;grid-template-columns:1fr 1fr;gap:8px}
pre{white-space:pre-wrap;background:#020617;border:1px solid var(--line);border-radius:14px;padding:14px;overflow:auto;max-height:380px;font-size:13px}
.badge{display:inline-block;padding:5px 9px;border-radius:999px;font-size:12px;background:#374151}
.badge.ok{background:#14532d} .badge.warn{background:#78350f} .badge.bad{background:rgba(127,29,29,.65);color:#fecaca}

/* Payment/deferred task cards -- accent-colored per state */
.view-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.view-tab{display:inline-flex;align-items:center;gap:6px;padding:9px 13px;border-radius:999px;font-size:13px;font-weight:750;background:rgba(148,163,184,.12);color:#e2e8f0;border:1px solid rgba(148,163,184,.2)}
.view-tab .tab-badge{background:rgba(2,6,23,.4);border-radius:999px;padding:1px 7px;font-size:11px;font-weight:800}
.view-tab.tab-red{border-color:rgba(239,68,68,.5)} .view-tab.tab-red .tab-badge{color:#fca5a5}
.view-tab.tab-orange{border-color:rgba(245,158,11,.5)} .view-tab.tab-orange .tab-badge{color:#fbbf24}
.view-tab.tab-blue{border-color:rgba(37,99,235,.5)} .view-tab.tab-blue .tab-badge{color:#93c5fd}
.view-tab.tab-green{border-color:rgba(34,197,94,.5)} .view-tab.tab-green .tab-badge{color:#86efac}

.task-card-list{display:flex;flex-direction:column;gap:10px}
.task-card{border:1px solid rgba(148,163,184,.18);border-left:4px solid rgba(148,163,184,.4);background:rgba(2,6,23,.4);border-radius:14px;padding:13px 14px}
.task-card.overdue{border-left-color:var(--red);background:rgba(127,29,29,.14)}
.task-card.soon{border-left-color:var(--orange);background:rgba(120,53,15,.14)}
.task-card.pending{border-left-color:#2563eb}
.task-card.deferred{border-left-color:#b45309;background:rgba(120,53,15,.1)}
.task-card.paid{border-left-color:#16a34a}
.task-card-head{display:flex;justify-content:space-between;gap:10px;font-weight:800;font-size:15px}
.task-card-amount{white-space:nowrap}
.task-card-amount.overdue{color:#fca5a5} .task-card-amount.soon{color:#fbbf24} .task-card-amount.paid{color:#86efac}
.task-card-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:space-between;margin-top:5px;font-size:12px;color:var(--muted)}
.task-card-actions{display:flex;gap:8px;margin-top:11px}
.task-card-actions .paid-quick-form,.task-card-actions .defer-widget{flex:1}
.task-card-actions .paid-quick-form button{width:100%;background:#16a34a}
.task-card-actions .defer-widget .defer-toggle{width:100%;background:transparent;border:1px solid rgba(245,158,11,.5);color:#fbbf24}
.task-card-more{margin-top:8px}
.task-card-more summary{cursor:pointer;color:var(--muted);font-size:12px;list-style:none}
a{color:white;text-decoration:none}
.topnav{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px;padding:12px 18px;background:rgba(15,23,42,.97);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.topnav .brand{font-weight:900;margin-right:8px}
.topnav a,.topnav .navlink{color:var(--text);text-decoration:none;padding:8px 10px;border-radius:10px;font-size:14px}
.topnav a:hover{background:var(--line)}
.topnav .navlink.disabled{color:var(--muted);cursor:default}
.summarygrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.summarygrid .metric .value{font-size:26px}
.section{margin-bottom:14px}
.urgency-overdue{color:var(--red);font-weight:700}
.urgency-due_today{color:var(--orange);font-weight:700}
.urgency-soon{color:var(--orange)}
.urgency-later{color:var(--muted)}
details.card summary{cursor:pointer;font-size:20px;font-weight:700}
@media(max-width:1000px){
.app{grid-template-columns:1fr;display:flex;flex-direction:column}
.main{order:1} .sidebar{order:2}
.topgrid{grid-template-columns:1fr} .summarygrid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:600px){
.app{padding:10px} table{min-width:560px}
.topnav{padding:10px 12px;gap:2px 10px} .topnav a,.topnav .navlink{padding:10px 12px;font-size:15px}
.summarygrid{grid-template-columns:1fr}
}

/* BP_APP_SHELL_PATCH_V1 */
/* App-like shell: desktop sidebar menu, mobile drawer, card-first dashboard */
body{background:radial-gradient(circle at top left,#1e3a8a 0,#0f172a 34%,#020617 100%);min-height:100vh}
.menu-toggle{display:none;position:fixed;top:12px;left:12px;z-index:60;border:1px solid rgba(255,255,255,.14);background:rgba(15,23,42,.96);box-shadow:0 10px 30px rgba(0,0,0,.35)}
.drawer-overlay{display:none}
.topnav{
  position:fixed;left:0;top:0;bottom:0;width:250px;z-index:50;
  display:flex;flex-direction:column;align-items:stretch;gap:8px;
  padding:20px 14px;background:rgba(2,6,23,.96);
  border-right:1px solid rgba(148,163,184,.20);border-bottom:0;
  box-shadow:18px 0 45px rgba(0,0,0,.32)
}
.topnav .brand{font-size:22px;margin:0 0 14px;padding:10px 12px}
.topnav a,.topnav .navlink{
  display:block;padding:12px 14px;border-radius:14px;
  background:transparent;border:1px solid transparent
}
.topnav a:hover{background:rgba(37,99,235,.18);border-color:rgba(96,165,250,.25)}
.topnav a.active{background:rgba(37,99,235,.32);border-color:rgba(96,165,250,.4);font-weight:800}
.bottomnav{display:none}
.app{margin-left:250px;padding:20px;display:flex;flex-direction:column;gap:16px}
.main{order:1}
.sidebar{order:2;display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:14px}
.sidebar>.card:first-child{display:none}
.card{border-radius:22px;border-color:rgba(148,163,184,.18);box-shadow:0 18px 50px rgba(0,0,0,.28)}
.summarygrid{grid-template-columns:repeat(4,minmax(0,1fr))}
.summarygrid .card{min-height:120px}
.summarygrid .metric .label{text-transform:uppercase;letter-spacing:.04em;font-size:12px}
.summarygrid .metric .value{font-size:30px}
.section[id="forecast3m"]{order:90}
.actions-stack{min-width:0}
.quick-actions{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.quick-actions form{margin:0}
.quick-actions button{font-size:12px;padding:8px 10px;border-radius:999px;background:#334155}
.quick-actions .pay-main button{background:#14532d}
.quick-actions .pay-other button{background:#164e63}
.quick-actions .pay-reserve button{background:#7c2d12}
.quick-actions .reset button{background:#475569}
.quick-actions .defer button{background:#78350f}
@media(max-width:1100px){
  .summarygrid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .sidebar{grid-template-columns:1fr}
}
@media(max-width:760px){
  body{padding-top:58px}
  .menu-toggle{display:block}
  .drawer-overlay.open{display:block;position:fixed;inset:0;background:rgba(2,6,23,.58);z-index:45}
  .topnav{transform:translateX(-105%);transition:transform .18s ease;width:min(82vw,310px)}
  .topnav.open{transform:translateX(0)}
  .topnav .brand{padding-left:48px}
  .app{margin-left:0;padding:10px}
  .summarygrid{grid-template-columns:1fr;gap:10px}
  .summarygrid .card{min-height:auto;padding:16px}
  .summarygrid .metric .value{font-size:28px}
  .main{gap:10px}
  .card{border-radius:18px;padding:14px}
  h2{font-size:18px}
  .table-scroll{overflow:visible}
  table{min-width:0!important;width:100%;border-collapse:separate;border-spacing:0 10px}
  thead, th{display:none}
  tbody, tr, td{display:block;width:100%}
  tr{background:rgba(15,23,42,.62);border:1px solid rgba(148,163,184,.18);border-radius:16px;padding:10px;margin-bottom:10px}
  td{border:0;padding:6px 4px;font-size:14px}
  td::before{content:attr(data-label);display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}
  td.actions,td.actions-stack{padding-top:10px}
  .actions,.actions-stack{justify-content:flex-start;align-items:stretch}
  .actions form,.actions-stack form{width:100%}
  .actions button,.actions-stack button{width:100%;margin-top:4px}
  .quick-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}
  .quick-actions button{width:100%;font-size:13px;padding:10px 8px}
  .actions-stack>form[action*="/payment/state/"], .actions-stack>form[action*="/onetime/state/"]{display:none}
  .bottomnav{
    display:flex;position:fixed;left:0;right:0;bottom:0;z-index:55;
    background:rgba(2,6,23,.97);border-top:1px solid rgba(148,163,184,.2);
    box-shadow:0 -10px 30px rgba(0,0,0,.35);padding:6px 4px calc(6px + env(safe-area-inset-bottom));
  }
  .bottomnav a{
    flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;
    padding:8px 2px;border-radius:12px;font-size:11px;color:var(--muted);
    min-height:52px;justify-content:center;
  }
  .bottomnav a.active{color:var(--text);background:rgba(37,99,235,.22)}
  .bottomnav a[href="/deferred"].active{background:rgba(180,83,9,.28)}
  .bottomnav a[href="/envelopes"].active{background:rgba(13,148,136,.28)}
  .bottomnav a[href="/receipts"].active{background:rgba(124,58,237,.28)}
  .bottomnav .bn-icon{font-size:19px;line-height:1}
  body{padding-bottom:74px}
  .sidebar{display:flex;flex-direction:column}
}





/* BP_UX_SAFETY_V2 */
.safety-review{
  order:-40;
  margin-bottom:16px;
  background:rgba(15,23,42,.94);
  border:1px solid rgba(148,163,184,.24);
  border-radius:22px;
  padding:16px 18px;
  box-shadow:0 18px 50px rgba(0,0,0,.30)
}
.safety-review h2{margin:0 0 4px;font-size:20px}
.safety-review .hint{color:var(--muted);font-size:13px;margin-bottom:12px;line-height:1.35}
.safety-review-groups{display:flex;flex-direction:column;gap:14px}
.safety-review-group-title{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:800;margin-bottom:8px;cursor:default}
details.safety-review-group summary.safety-review-group-title{cursor:pointer;list-style:none}
details.safety-review-group summary.safety-review-group-title::-webkit-details-marker{display:none}
details.safety-review-group summary.safety-review-group-title::before{content:"▸ ";display:inline-block}
details.safety-review-group[open] summary.safety-review-group-title::before{content:"▾ "}
.safety-review-list{display:flex;flex-direction:column;gap:8px}
.safety-review-row{
  display:grid;
  grid-template-columns:1fr auto auto auto;
  align-items:center;
  gap:10px;
  padding:10px 12px;
  border:1px solid rgba(148,163,184,.16);
  background:rgba(2,6,23,.46);
  border-radius:14px
}
.safety-review-row.overdue{
  border-color:rgba(239,68,68,.78);
  background:rgba(127,29,29,.32)
}
.safety-review-row.due-soon{
  border-color:rgba(245,158,11,.78);
  background:rgba(120,53,15,.28)
}
.safety-review-name{font-weight:850}
.safety-review-sum{font-weight:900;white-space:nowrap}
.safety-review-due{
  font-size:12px;
  color:var(--muted);
  white-space:nowrap;
}
.safety-review-row.overdue .safety-review-due{
  color:#fecaca;
  font-weight:800;
}
.safety-review-row.due-soon .safety-review-due{
  color:#fed7aa;
  font-weight:800;
}
.safety-review-row.deferred{
  border-color:rgba(245,158,11,.4);
  background:rgba(120,53,15,.16);
  opacity:.9;
}
.safety-review-row.paid{
  border-color:rgba(34,197,94,.4);
  background:rgba(20,83,45,.18);
  opacity:.85;
}
.safety-review-row .badge.warn{background:rgba(120,53,15,.6);color:#fed7aa}
.safety-review-row .badge.ok{background:rgba(20,83,45,.6);color:#bbf7d0}
.safety-review-x{
  width:34px;
  height:34px;
  border-radius:999px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  font-weight:900;
  background:rgba(127,29,29,.94);
  color:#fee2e2;
  border:1px solid rgba(255,255,255,.18)
}
.safety-review-actions form{margin:0}
.safety-review-actions button{
  border-radius:999px;
  padding:8px 12px;
  font-size:12px;
  background:#166534
}
.last-update-card{
  order:-41;
  margin-bottom:12px;
  border:1px solid rgba(148,163,184,.20);
  background:rgba(15,23,42,.74);
  border-radius:18px;
  padding:12px 14px;
  color:var(--muted);
  font-size:13px;
}
.last-update-card strong{color:var(--text)}
.metric .label.warning-label{color:#fbbf24!important}
.metric .label.projection-label{color:#93c5fd!important}
@media(max-width:760px){
  .safety-review{border-radius:18px;padding:14px;margin-bottom:10px}
  .safety-review-row{
    grid-template-columns:1fr auto 36px;
    gap:8px
  }
  .safety-review-due{grid-column:1 / -1}
  .safety-review-actions{grid-column:1 / -1}
  .safety-review-actions form{width:100%}
  .safety-review-actions button{width:100%;padding:11px 8px}
}


/* BP_BALANCE_FIRST_V1 */
.balance-first-note{
  order:-50;
  margin-bottom:12px;
  border:1px solid rgba(59,130,246,.30);
  background:rgba(30,64,175,.18);
  border-radius:18px;
  padding:12px 14px;
  color:#dbeafe;
  font-size:13px;
}
.balance-first-note strong{color:#fff}
.hidden-income-card{display:none!important}


/* BP_EDITABLE_ENVELOPES_V1 */
.editable-envelopes{
  order:-70;
  margin-bottom:16px;
  background:rgba(15,23,42,.92);
  border:1px solid rgba(148,163,184,.24);
  border-radius:22px;
  padding:16px 18px;
  box-shadow:0 18px 50px rgba(0,0,0,.28)
}
.editable-envelopes h2{margin:0 0 4px;font-size:20px}
.editable-envelopes .hint{color:var(--muted);font-size:13px;margin-bottom:12px;line-height:1.35}
.envelope-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.envelope-card{border:1px solid rgba(148,163,184,.18);background:rgba(2,6,23,.46);border-radius:16px;padding:14px}
.envelope-card.warn{border-color:rgba(245,158,11,.6)}
.envelope-card.over{border-color:rgba(239,68,68,.75);background:rgba(127,29,29,.22)}
.envelope-card-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-weight:850}
.envelope-card-title{display:flex;align-items:center;gap:9px}
.envelope-card-icon{width:34px;height:34px;border-radius:50%;background:rgba(45,212,191,.16);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.envelope-card.warn .envelope-card-icon{background:rgba(251,191,36,.16)}
.envelope-card.over .envelope-card-icon{background:rgba(239,68,68,.18)}
.envelope-card-name{font-size:16px}
.envelope-card-remaining{font-size:13px;color:#5eead4;white-space:nowrap}
.envelope-card.warn .envelope-card-remaining{color:#fbbf24}
.envelope-card.over .envelope-card-remaining{color:#fca5a5}
.envelope-progress-bar{height:9px;border-radius:999px;background:rgba(2,6,23,.6);overflow:hidden;margin-top:9px}
.envelope-progress-fill{height:100%;background:#2dd4bf;border-radius:999px}
.envelope-progress-fill.warn{background:#fbbf24}
.envelope-progress-fill.over{background:#ef4444}
.envelope-card-sub{margin-top:8px;font-size:12px;color:var(--muted)}
.envelope-card-over{margin-top:6px;font-size:12px;font-weight:800;color:#fca5a5}
.envelope-card-actions{display:flex;gap:8px;margin-top:10px}
.envelope-card-btn{flex:1;text-align:center;padding:9px 10px;border-radius:12px;background:#0f766e;color:white;text-decoration:none;font-size:13px;font-weight:750;border:0;cursor:pointer}
.envelope-card-btn.secondary{background:rgba(148,163,184,.18);color:#e2e8f0}
.defer-widget{display:inline-block}
.defer-form{margin-top:8px;padding:10px 12px;border:1px solid rgba(245,158,11,.4);background:rgba(120,53,15,.16);border-radius:12px;min-width:220px}
.defer-form label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}
.defer-form .defer-date-input{width:100%;padding:9px 10px;border-radius:10px;margin-bottom:8px}
.defer-quick-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
button.tiny.defer-quick{padding:6px 9px;font-size:11px;border-radius:999px;background:rgba(148,163,184,.2);color:#e2e8f0;border:0;cursor:pointer}
.defer-form .btn-row{margin-top:0}

/* Dashboard summary cards -- short overview only, full lists live in their own views */
.summary-card h2{margin-bottom:10px}
.summary-card-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:10px}
.summary-card-head h2{margin-bottom:0}
.summary-card-link{font-size:12px;color:#93c5fd;font-weight:700;white-space:nowrap}
.summary-card .btn-row,.summary-card>a{margin-top:12px;display:block}
.summary-card>a button{width:100%}
.summary-stats{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:6px}
.summary-stats .stat{min-width:70px}
.summary-stats .stat-value{font-size:22px;font-weight:900}
.summary-stats .stat-value.bad{color:var(--red)}
.summary-stats .stat-value.warn{color:var(--orange)}
.summary-stats .stat-value.teal{color:#5eead4}
.summary-stats .stat-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.deferred-mini-list,.deferred-detail-list{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.deferred-mini-row{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:6px 0;border-bottom:1px solid rgba(148,163,184,.12)}
.deferred-mini-row:last-child{border-bottom:0}
.deferred-summary{border-left:4px solid #b45309;background:linear-gradient(160deg,rgba(120,53,15,.16),rgba(31,41,55,.92))}
.envelopes-summary-dashboard{border-left:4px solid #0f766e}
.payments-summary{border-left:4px solid #2563eb}
.activity-summary{border-left:4px solid #64748b}
.deferred-detail-row{border:1px solid rgba(148,163,184,.18);background:rgba(2,6,23,.4);border-radius:14px;padding:12px 14px}
.deferred-detail-row.overdue{border-color:rgba(239,68,68,.7);background:rgba(127,29,29,.22)}
.deferred-detail-head{display:flex;justify-content:space-between;gap:10px;font-weight:800;margin-bottom:4px}
.deferred-detail-row .pay-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.danger-zone{border-color:rgba(239,68,68,.5);background:rgba(127,29,29,.12)}
.danger-zone summary{color:#fca5a5;font-weight:800}
.danger-zone #reset-confirm-input{border-color:rgba(239,68,68,.5)}
.danger-zone button.danger:disabled{opacity:.4;cursor:not-allowed}
.edit-target-flash{animation:bp-edit-flash 2.2s ease-out}
@keyframes bp-edit-flash{
  0%{box-shadow:0 0 0 3px rgba(37,99,235,.9);border-color:rgba(96,165,250,.9)}
  100%{box-shadow:0 0 0 0 rgba(37,99,235,0)}
}
.envelope-edit-row{
  display:grid;
  grid-template-columns:1fr 1fr;
  align-items:end;
  gap:10px;
  padding:10px 0 0;
  margin-top:10px;
  border-top:1px solid rgba(148,163,184,.16);
}
.envelope-edit-row label{
  display:block;
  color:var(--muted);
  font-size:12px;
  margin-bottom:5px
}
.envelope-edit-row input{
  width:100%;
  padding:10px 11px;
  border-radius:12px;
}
.envelope-edit-row button{
  width:100%;
  border-radius:12px;
  padding:10px 11px;
}
@media(max-width:760px){
  .editable-envelopes{border-radius:18px;padding:14px}
  .envelope-grid{grid-template-columns:1fr}
}


/* BP_TOP_REVIEW_DEFER_V1 */
.safety-review-actions,
.unpaid-confirm-actions,
.manual-confirm-actions{
  display:flex;
  gap:6px;
  flex-wrap:wrap;
  justify-content:flex-end;
}
.safety-review-actions form,
.unpaid-confirm-actions form,
.manual-confirm-actions form{
  margin:0;
}
.safety-review-actions form.bp-defer-form button,
.unpaid-confirm-actions form.bp-defer-form button,
.manual-confirm-actions form.bp-defer-form button{
  background:#92400e!important;
}
.safety-review-actions form.bp-paid-form button,
.unpaid-confirm-actions form.bp-paid-form button,
.manual-confirm-actions form.bp-paid-form button{
  background:#166534!important;
}
@media(max-width:760px){
  .safety-review-actions,
  .unpaid-confirm-actions,
  .manual-confirm-actions{
    justify-content:stretch;
  }
  .safety-review-actions form,
  .unpaid-confirm-actions form,
  .manual-confirm-actions form{
    flex:1 1 48%;
  }
  .safety-review-actions button,
  .unpaid-confirm-actions button,
  .manual-confirm-actions button{
    width:100%;
  }
}



/* BP_TOP_REAL_OVERVIEW_V5 */
.bp-hide-old-metrics{display:none!important}
.real-top{
  order:-300;margin-bottom:16px;
  background:linear-gradient(135deg,rgba(15,23,42,.98),rgba(30,64,175,.45));
  border:1px solid rgba(147,197,253,.35);border-radius:24px;
  padding:16px 18px;box-shadow:0 22px 70px rgba(0,0,0,.38)
}
.real-top-head{margin-bottom:2px}
.real-top h2{margin:0;font-size:19px;font-weight:800;color:#dbeafe}
.real-hero{text-align:center;padding:14px 10px 2px;margin-bottom:4px}
.real-hero-value{font-size:46px;font-weight:950;line-height:1;letter-spacing:-.02em}
.real-hero-value.good{color:#86efac}.real-hero-value.warn{color:#fbbf24}.real-hero-value.bad{color:#fca5a5}
.real-hero-caption{margin-top:10px;font-size:14px;font-weight:750;line-height:1.4}
.real-hero-caption.ok{color:#bfdbfe}
.real-hero-caption.bad{color:#fecaca;background:rgba(127,29,29,.4);border:1px solid rgba(248,113,113,.5);border-radius:14px;padding:9px 14px;display:inline-block}
.real-sub-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0 6px}
.real-metric{background:rgba(2,6,23,.43);border:1px solid rgba(148,163,184,.18);border-radius:16px;padding:12px}
.real-label{color:#cbd5e1;font-size:12px;line-height:1.25}
.real-value{margin-top:5px;font-size:21px;font-weight:900;white-space:nowrap}
.real-value.good{color:#86efac}.real-value.warn{color:#fbbf24}.real-value.bad{color:#fecaca}.real-value.teal{color:#5eead4}
.real-updated-line{display:flex;align-items:center;justify-content:center;gap:6px;font-size:12px;color:#94a3b8;margin:6px 0 10px}
.real-refresh-btn{width:22px;height:22px;border-radius:999px;background:rgba(148,163,184,.16);border:0;color:#cbd5e1;cursor:pointer;font-size:12px;display:inline-flex;align-items:center;justify-content:center;padding:0;line-height:1}
.real-refresh-btn.spinning{animation:bp-spin .6s linear}
@keyframes bp-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.real-balance-toggle{text-align:center;margin-bottom:6px}
.real-balance-toggle summary{cursor:pointer;color:#93c5fd;font-size:12px;font-weight:700;list-style:none;display:inline-block}
.real-balance-toggle summary::-webkit-details-marker{display:none}
.real-formula{margin-bottom:6px}
.real-formula summary{cursor:pointer;color:#cbd5e1;font-size:12px;font-weight:700;list-style:none;margin-bottom:8px}
.real-formula summary::-webkit-details-marker{display:none}
.real-formula summary::before{content:"▸ ";display:inline-block}
.real-formula[open] summary::before{content:"▾ "}
.real-calc{display:grid;grid-template-columns:1fr auto;gap:8px 12px;background:rgba(2,6,23,.35);border:1px solid rgba(148,163,184,.16);border-radius:16px;padding:12px}
.real-calc .amount{text-align:right;font-weight:950}
.real-calc .total{border-top:1px solid rgba(148,163,184,.20);padding-top:8px;font-weight:950;font-size:16px}
.real-update{display:grid;grid-template-columns:1fr 170px 120px;gap:8px;align-items:end;margin:8px 0 0}
.real-update label{display:block;color:#cbd5e1;font-size:12px;margin-bottom:5px}
.real-update input{width:100%;padding:10px 11px;border-radius:12px}
.real-update button{width:100%;padding:10px 11px;border-radius:12px}
@media(max-width:1000px){.real-sub-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:650px){.real-top{border-radius:18px;padding:16px}.real-hero-value{font-size:36px}.real-sub-grid{grid-template-columns:1fr}.real-update{grid-template-columns:1fr}}

/* Quick action pills below the hero card -- 2-column on mobile per spec */
.quick-actions-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px}
.qa-btn{display:flex;align-items:center;justify-content:center;gap:6px;padding:13px 8px;border-radius:14px;font-size:13px;font-weight:800;text-decoration:none;text-align:center}
.qa-blue{background:#2563eb;color:white}
.qa-purple{background:#7c3aed;color:white}
.qa-orange{background:rgba(245,158,11,.14);color:#fbbf24;border:1px solid rgba(245,158,11,.4)}
.qa-teal{background:rgba(45,212,191,.14);color:#5eead4;border:1px solid rgba(45,212,191,.4)}
.qa-gray{background:rgba(148,163,184,.14);color:#e2e8f0;border:1px solid rgba(148,163,184,.25)}
@media(min-width:700px){.quick-actions-grid{grid-template-columns:repeat(3,1fr)}}

/* BP_OCR_CANDIDATES_V1: OCR amount candidates in the receipt review card */
.candidate-list{display:flex;flex-direction:column;gap:6px;margin:8px 0}
.candidate{display:flex;align-items:center;gap:8px;font-size:13px;padding:7px 10px;border:1px solid #334155;border-radius:10px;cursor:pointer}
.candidate input{width:auto;margin:0}
.candidate-text{flex:1}
.candidate.not-recommended{color:#94a3b8;border-style:dashed}
.candidate-tag{font-size:11px;font-weight:800;padding:3px 8px;border-radius:999px;background:#7c3aed;color:white;white-space:nowrap}
.candidate-tag.not-recommended{background:transparent;border:1px solid #475569;color:#94a3b8}
.receipt-thumb{display:block;width:100%;max-height:260px;object-fit:contain;background:#020617;border:1px solid rgba(124,58,237,.35);border-radius:14px;margin:10px 0}

/* History timeline */
.timeline{display:flex;flex-direction:column;gap:18px}
.timeline-day-label{font-size:12px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(148,163,184,.14)}
.timeline-list{display:flex;flex-direction:column;gap:6px}
.timeline-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;padding:8px 10px;border-radius:10px;background:rgba(2,6,23,.35);font-size:13px}
.timeline-time{color:var(--muted);font-variant-numeric:tabular-nums;flex-shrink:0}
.timeline-action{font-weight:750;flex-shrink:0}
.timeline-detail{color:var(--muted);overflow-wrap:anywhere}

</style>
</head>
<body>
{% macro paid_button(payment_id, cycle_key) %}
<form method="post" action="/payment/state/by-id" class="paid-quick-form">
<input type="hidden" name="payment_id" value="{{payment_id}}">
<input type="hidden" name="cycle_key" value="{{cycle_key}}">
<input type="hidden" name="state" value="paid_me">
<button class="secondary">✓ Zaplatené</button>
</form>
{% endmacro %}
{% macro state_form(payment_id, cycle_key, states, labels) %}
<form method="post" action="/payment/state/by-id">
<input type="hidden" name="payment_id" value="{{payment_id}}">
<input type="hidden" name="cycle_key" value="{{cycle_key}}">
<select name="state">{% for s in states %}<option value="{{s}}">{{labels.get(s,s)}}</option>{% endfor %}</select>
<button class="secondary">Nastaviť</button>
</form>
{% endmacro %}
{% macro defer_widget(payment_id, cycle_key, btn_label) %}
<div class="defer-widget">
<button type="button" class="secondary defer-toggle">{{btn_label}}</button>
<form method="post" action="/payment/defer/by-id" class="defer-form" hidden>
<input type="hidden" name="payment_id" value="{{payment_id}}">
<input type="hidden" name="cycle_key" value="{{cycle_key}}">
<label>Odložiť do dátumu</label>
<input type="date" name="deferred_to" class="defer-date-input" required>
<div class="defer-quick-row">
<button type="button" class="tiny defer-quick" data-quick="7d">+7 dní</button>
<button type="button" class="tiny defer-quick" data-quick="next_month">ďalší mesiac</button>
<button type="button" class="tiny defer-quick" data-quick="end_month">koniec mesiaca</button>
<button type="button" class="tiny defer-quick" data-quick="today">Vrátiť medzi aktuálne</button>
</div>
<div class="btn-row">
<button type="submit" class="secondary">Potvrdiť odklad</button>
<button type="button" class="secondary defer-cancel">Zrušiť</button>
</div>
</form>
</div>
{% endmacro %}
{% macro unpaid_rows(items, accent) %}
<div class="task-card-list">
{% for p in items %}
<div class="task-card {{accent}}" data-payment-id="{{p.get('id','')}}" data-cycle-key="{{p.get('origin_cycle_key', cycle_key)}}">
<div class="task-card-head">
<span class="task-card-name">{{p.name}}{% if p.get('carryover_label') %}<br><span class="small">{{p.carryover_label}}</span>{% endif %}</span>
<span class="task-card-amount {{accent}}">{{p.amount}} €</span>
</div>
<div class="task-card-meta">
<span>Splatné {{p.due_date}}</span>
{% if p.urgency == 'overdue' %}<span class="badge bad">po splatnosti</span>
{% elif p.urgency in ('due_today','soon') %}<span class="badge warn">čoskoro</span>
{% endif %}
</div>
<div class="task-card-actions">
{{ paid_button(p.get('id',''), p.get('origin_cycle_key', cycle_key)) }}
{{ defer_widget(p.get('id',''), p.get('origin_cycle_key', cycle_key), '↷ Odložiť') }}
</div>
<details class="task-card-more"><summary>Iný stav (priorita: {{p.get('priority','-')}})</summary>
{{ state_form(p.get('id',''), p.get('origin_cycle_key', cycle_key), selectable_states, state_label) }}
</details>
</div>
{% endfor %}
</div>
{% endmacro %}
{% macro deferred_rows(items) %}
<div class="task-card-list">
{% for p in items %}
<div class="task-card deferred" data-payment-id="{{p.get('id','')}}" data-cycle-key="{{p.get('origin_cycle_key', cycle_key)}}">
<div class="task-card-head">
<span class="task-card-name">{{p.name}}</span>
<span class="task-card-amount deferred">{{p.amount}} €</span>
</div>
<div class="task-card-meta">
<span>Odložené do {{p.get('deferred_to','-')}} · pôvodne {{p.get('origin_cycle_key','-')}}</span>
{% if p.get('days_left') is not none %}
{% if p.days_left < 0 %}<span class="badge bad">po termíne</span>
{% elif p.days_left <= 7 %}<span class="badge warn">o {{p.days_left}} {% if p.days_left == 1 %}deň{% elif p.days_left < 5 %}dni{% else %}dní{% endif %}</span>
{% else %}<span class="badge">o {{p.days_left}} dní</span>
{% endif %}
{% endif %}
</div>
{% if p.get('note') %}<div class="small">Poznámka: {{p.note}}</div>{% endif %}
<div class="task-card-actions">
{{ paid_button(p.get('id',''), p.get('origin_cycle_key', cycle_key)) }}
{{ defer_widget(p.get('id',''), p.get('origin_cycle_key', cycle_key), 'Zmeniť dátum') }}
</div>
</div>
{% endfor %}
</div>
{% endmacro %}
<script>
window.BP_ACTIVE_VIEW = "{{active_view}}";
window.BP_EDIT_TARGET = "{% if edit_payment is not none %}edit-form-payment{% elif edit_income is not none %}edit-form-income{% elif edit_expense is not none %}edit-form-expense{% endif %}";
</script>
<nav class="topnav" id="appDrawer">
<span class="brand">BudgetPilot</span>
<a href="/" class="{% if active_view=='dashboard' %}active{% endif %}">Prehľad</a>
<a href="/payments" class="{% if active_view=='payments' %}active{% endif %}">Platby</a>
<a href="/deferred" class="{% if active_view=='deferred' %}active{% endif %}">Odložené</a>
<a href="/envelopes" class="{% if active_view=='envelopes' %}active{% endif %}">Obálky</a>
<a href="/expenses" class="{% if active_view=='expenses' %}active{% endif %}">Výdavky</a>
<a href="/receipts" class="{% if active_view=='receipts' %}active{% endif %}">OCR</a>
<a href="/history" class="{% if active_view=='history' %}active{% endif %}">História</a>
<a href="/settings" class="{% if active_view=='settings' %}active{% endif %}">Nastavenia</a>
</nav>
<nav class="bottomnav">
<a href="/" class="{% if active_view=='dashboard' %}active{% endif %}"><span class="bn-icon">🏠</span>Prehľad</a>
<a href="/payments" class="{% if active_view=='payments' %}active{% endif %}"><span class="bn-icon">🧾</span>Platby</a>
<a href="/deferred" class="{% if active_view=='deferred' %}active{% endif %}"><span class="bn-icon">↷</span>Odložené</a>
<a href="/envelopes" class="{% if active_view=='envelopes' %}active{% endif %}"><span class="bn-icon">✉</span>Obálky</a>
<a href="/receipts" class="{% if active_view=='receipts' %}active{% endif %}"><span class="bn-icon">📷</span>OCR</a>
</nav>
<div class="app">

<aside class="sidebar">
<div class="card">
<h1>BudgetPilot</h1>
<div class="small">Hrubá pravda o mesiaci. Bez AI, bez blbostí.</div>
</div>

{% if setup_needed and active_view == 'dashboard' %}
<div class="card" style="border-color:var(--orange)">
<h2>⚠️ Dokonči nastavenie</h2>
<div class="small">Chýba deň výplaty alebo reálny zostatok k dnešnému dňu.</div>
<div class="btn-row"><a href="/setup"><button type="button">Otvoriť nastavenie</button></a></div>
</div>
{% endif %}

{% if active_view == 'settings' %}
<div class="card">
<h2>Účet + rezerva</h2>
<form method="post" action="/settings">
<label>Suma na účte teraz</label>
<input name="account_balance" value="{{settings.get('account_balance',0)}}">
<label><input type="checkbox" name="use_reserve" {% if settings.get('use_reserve') %}checked{% endif %} style="width:auto"> Mám reálnu rezervu bokom</label>
<label>Rezerva bokom</label>
<input name="safe_min" value="{{settings.get('safe_min',0)}}">
<div class="small">Rezerva sa neráta medzi použiteľné peniaze. Zapni iba keď ju máš naozaj bokom.</div>
<div class="btn-row"><button>Uložiť</button></div>
</form>
</div>

<div class="card" id="edit-form-income">
<h2>{% if edit_income is not none %}Upraviť príjem{% else %}Príjem{% endif %}</h2>
<form method="post" action="{% if edit_income is not none %}/income/update/{{edit_income}}{% else %}/income/add{% endif %}">
<label>Názov</label><input name="name" value="{{income_form.get('name','Výplata netto')}}">
<label>Suma</label><input name="amount" value="{{income_form.get('amount','2000')}}">
<label>Deň v mesiaci</label><input name="day" value="{{income_form.get('day','15')}}">
<div class="btn-row">
<button>{% if edit_income is not none %}Uložiť úpravu{% else %}Pridať príjem{% endif %}</button>
{% if edit_income is not none %}<a href="/settings"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>
{% endif %}

{% if active_view == 'payments' %}
<div class="card" id="edit-form-payment">
<h2>{% if edit_payment is not none %}Upraviť platbu{% else %}Pravidelná platba{% endif %}</h2>
<form method="post" action="{% if edit_payment is not none %}/payment/update/{{edit_payment}}{% else %}/payment/add{% endif %}">
<label>Typ</label>
<select name="type">{% for t in payment_types %}<option {% if payment_form.type==t %}selected{% endif %}>{{t}}</option>{% endfor %}</select>
<label>Názov pri „Iné“</label><input name="name" value="{{payment_form.name}}" placeholder="napr. škôlka, leasing, daň">
<label>Suma</label><input name="amount" value="{{payment_form.amount}}" placeholder="napr. 820">
<div class="inline">
<div><label>Deň</label><input name="day" value="{{payment_form.day}}"></div>
<div><label>Mesiac štartu</label><input name="month" value="{{payment_form.month}}"></div>
</div>
<label>Rok štartu</label><input name="year" value="{{payment_form.year}}">
<label>Opakovanie</label>
<select name="frequency">
{% for f in ["monthly","quarterly","yearly","custom_months","once"] %}
<option value="{{f}}" {% if payment_form.frequency==f %}selected{% endif %}>{{freq_label.get(f,f)}}</option>
{% endfor %}
</select>
<label>Ak vlastné: každých X mesiacov</label><input name="every_months" value="{{payment_form.every_months}}" placeholder="napr. 24">
<div class="btn-row">
<button>{% if edit_payment is not none %}Uložiť úpravu{% else %}Pridať platbu{% endif %}</button>
{% if edit_payment is not none %}<a href="/payments"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>

<div class="card">
<h2>Jednorazová platba</h2>
<form method="post" action="/onetime/add">
<label>Názov</label><input name="name" placeholder="napr. servis auta">
<label>Suma</label><input name="amount" placeholder="napr. 180">
<label>Termín splatnosti</label><input name="due_date" value="{{today}}">
<label>Priorita</label>
<select name="priority">{% for p, label in priority_label.items() %}<option value="{{p}}">{{label}}</option>{% endfor %}</select>
<div class="btn-row"><button>Pridať jednorazovú platbu</button></div>
</form>
</div>

<div class="card">
<h2>Dlh</h2>
<form method="post" action="/debt/add">
<label>Názov / komu-od koho</label><input name="name" placeholder="napr. Peter, pôžička na auto">
<label>Suma</label><input name="amount" placeholder="napr. 300">
<label>Smer</label>
<select name="direction">
{% for d, label in debt_direction_label.items() %}<option value="{{d}}">{{label}}</option>{% endfor %}
</select>
<label>Termín splatnosti</label><input name="due_date" value="{{today}}">
<label>Poznámka</label><input name="note" placeholder="voliteľné">
<div class="btn-row"><button>Pridať dlh</button></div>
</form>
</div>
{% endif %}

{% if active_view == 'expenses' %}
<div class="card" id="expense-quick">
<h2>Rýchly výdavok</h2>
<form method="post" action="/expense/add">
<input type="hidden" name="name" value="Rýchly výdavok">
<label>Suma</label><input name="amount" placeholder="napr. 50">
<input type="hidden" name="date" value="{{today}}">
<div class="btn-row"><button>Pridať</button></div>
</form>
</div>

<div class="card" id="edit-form-expense">
<h2>{% if edit_expense is not none %}Upraviť výdavok{% else %}Detailný výdavok{% endif %}</h2>
<form method="post" action="{% if edit_expense is not none %}/expense/update/{{edit_expense}}{% else %}/expense/add{% endif %}">
<label>Typ (obálka)</label>
<select name="name">{% for t in expense_types %}<option {% if expense_form.name==t %}selected{% endif %}>{{t}}</option>{% endfor %}</select>
<label>Suma</label><input name="amount" value="{{expense_form.amount}}">
<label>Poznámka / obchod (voliteľné)</label><input name="merchant" value="{{expense_form.get('merchant','')}}" placeholder="napr. Lidl">
<label>Dátum</label><input name="date" value="{{expense_form.date}}">
<div class="btn-row">
<button>{% if edit_expense is not none %}Uložiť úpravu{% else %}Pridať výdavok{% endif %}</button>
{% if edit_expense is not none %}<a href="/expenses"><button type="button" class="secondary">Zrušiť</button></a>{% endif %}
</div>
</form>
</div>
{% endif %}

{% if active_view == 'receipts' %}
<div class="card">
<h2>Účtenka (foto)</h2>
<form method="post" action="/receipt/upload" enctype="multipart/form-data">
<label>Fotka účtenky</label>
<input type="file" name="image" accept="image/*" capture="environment" required>
<div class="small">Rozpozná sumu/dátum ako odhad — vždy si to pred uložením skontroluješ a potvrdíš.</div>
<div class="btn-row"><button>Nahrať a rozpoznať</button></div>
</form>
</div>

{% if receipt_review %}
<div class="card" id="receipt-review" style="border-color:#7c3aed">
<h2>📷 Potvrdiť účtenku</h2>
<div class="small">Odhad z OCR — over si sumu a dátum, priradí sa kategória, a až potom sa uloží ako výdavok.</div>
<img class="receipt-thumb" src="/receipt/image/{{receipt_review.receipt_id}}" alt="Fotka účtenky">
<form method="post" action="/receipt/confirm">
<input type="hidden" name="receipt_id" value="{{receipt_review.receipt_id}}">
<input type="hidden" name="image_path" value="{{receipt_review.image_path}}">
{% if receipt_review.candidates %}
<label>Nájdené sumy na účtenke</label>
<div class="candidate-list">
{% for c in receipt_review.candidates %}
<label class="candidate {% if c.not_recommended %}not-recommended{% endif %}">
<input type="radio" name="_candidate_pick" onclick="document.getElementById('receipt-amount').value='{{'%.2f'|format(c.amount)}}'">
<span class="candidate-text">{% if not c.not_recommended and c.amount == receipt_review.amount %}Odporúčané: {% endif %}{{c.label}}: {{"%.2f"|format(c.amount)}} €</span>
<span class="candidate-tag {% if c.not_recommended %}not-recommended{% endif %}">{% if c.not_recommended %}Neodporúčané{% else %}Použiť{% endif %}</span>
</label>
{% endfor %}
</div>
{% endif %}
<label>Vybraná suma</label><input id="receipt-amount" name="amount" value="{{receipt_review.amount or ''}}" placeholder="skontroluj sumu">
<label>Obálka</label>
<select name="name">{% for t in expense_types %}<option {% if t=='Iné' %}selected{% endif %}>{{t}}</option>{% endfor %}</select>
<label>Poznámka (voliteľné, aj obchod)</label><input name="merchant" value="{{receipt_review.merchant or ''}}" placeholder="napr. Lidl">
<label>Dátum</label><input name="date" value="{{receipt_review.date or today}}">
<div class="btn-row">
<button>Uložiť výdavok</button>
<a href="/receipts"><button type="button" class="secondary">Zahodiť</button></a>
</div>
</form>
</div>
{% endif %}
{% endif %}

{% if active_view == 'envelopes' %}
<div class="card">
<h2>Obálka (mesačný limit)</h2>
<form method="post" action="/envelope/add">
<label>Kategória</label>
<select name="category">{% for t in expense_types %}<option>{{t}}</option>{% endfor %}</select>
<label>Mesačný limit</label><input name="monthly_limit" placeholder="napr. 200">
<div class="small">Ak už na túto kategóriu obálka existuje, uloženie iba prepíše jej limit.</div>
<div class="btn-row"><button>Uložiť obálku</button></div>
</form>
</div>
{% endif %}
</aside>

<main class="main" id="overview">
<div class="summarygrid">
<div class="card metric"><div class="label">Zostatok na účte</div><div class="value">{{summary.balance}}</div></div>
<div class="card metric"><div class="label">Nezaplatené pred výplatou</div><div class="value">{{summary.unpaid_total}}</div></div>
<div class="card metric"><div class="label">Bezpečne minúť teraz (pred výplatou)</div><div class="value {{dash.status_class}}">{{summary.safe_to_spend}}</div></div>
<div class="card metric"><div class="label">Na deň do výplaty</div><div class="value">{{summary.daily_safe_to_spend}}</div></div>
{% if summary.shortfall != '-' %}
<div class="card metric"><div class="label">Chýba do výplaty</div><div class="value bad">{{summary.shortfall}}</div></div>
{% endif %}
<div class="card metric"><div class="label">Odhad po najbližšej výplate (vrátane budúceho príjmu)</div><div class="value">{{summary.projected_after_payday}}</div></div>
<div class="card metric"><div class="label">Ďalšia výplata</div><div class="value">{{summary.next_payday}}</div></div>
</div>

<div class="card section" id="forecast3m">
<h2>3-mesačný výhľad</h2>
<div class="small">Plánovaný príjem/platby za celý mesiac — nie to isté ako "bezpečne minúť teraz". Nezahŕňa dlhy ani rezervu.</div>
<div class="table-scroll">
<table><tr><th>Mesiac</th><th>Plánovaný príjem</th><th>Plánované platby</th><th>Plán mesiaca</th><th>Stav</th></tr>
{% for m in forecast_months %}
<tr>
<td>{{m.label}}</td>
<td>{{"%.2f"|format(m.income_total)}} €</td>
<td>{{"%.2f"|format(m.payment_total)}} €</td>
<td class="{% if m.planned_month_balance < 0 %}bad{% else %}ok{% endif %}">{{"%.2f"|format(m.planned_month_balance)}} €</td>
<td>{{m.status}}</td>
</tr>
{% endfor %}
</table>
</div>
</div>

{% if active_view == 'dashboard' %}
<div class="card summary-card payments-summary">
<div class="summary-card-head"><h2>🧾 Platby</h2><a class="summary-card-link" href="/payments">Zobraziť všetky →</a></div>
<div class="summary-stats">
<div class="stat"><div class="stat-value">{{unpaid|length}}</div><div class="stat-label">nezaplatené</div></div>
<div class="stat"><div class="stat-value {% if unpaid_overdue|length %}bad{% endif %}">{{unpaid_overdue|length}}</div><div class="stat-label">po splatnosti</div></div>
<div class="stat"><div class="stat-value {% if unpaid_soon|length %}warn{% endif %}">{{unpaid_soon|length}}</div><div class="stat-label">čoskoro</div></div>
</div>
<div class="small">Spolu nezaplatené {{summary.unpaid_total}}</div>
<a href="/payments"><button type="button">Otvoriť platby</button></a>
</div>

<div class="card summary-card deferred-summary">
<div class="summary-card-head"><h2>↷ Odložené platby</h2><a class="summary-card-link" href="/deferred">Zobraziť všetky →</a></div>
{% if deferred %}
<div class="summary-stats">
<div class="stat"><div class="stat-value warn">{{"%.2f"|format(deferred|sum(attribute='amount'))}} €</div><div class="stat-label">odložené</div></div>
<div class="stat"><div class="stat-value">{{deferred|length}}</div><div class="stat-label">počet</div></div>
</div>
{% set next_deferred = deferred|sort(attribute='deferred_to')|first %}
{% if next_deferred %}<div class="small">Najbližšie: {{next_deferred.name}} — {{next_deferred.deferred_to}}</div>{% endif %}
<div class="deferred-mini-list">
{% for p in (deferred|sort(attribute='deferred_to'))[:3] %}
<div class="deferred-mini-row"><span>{{p.name}}</span><span>{{p.amount}} € · {{p.deferred_to}}</span></div>
{% endfor %}
</div>
{% else %}<div class="small">Žiadne odložené platby.</div>{% endif %}
<a href="/deferred"><button type="button">Otvoriť odložené</button></a>
</div>

<div class="card summary-card envelopes-summary-dashboard">
<div class="summary-card-head"><h2>✉ Obálky</h2><a class="summary-card-link" href="/envelopes">Zobraziť všetky →</a></div>
<div class="summary-stats">
<div class="stat"><div class="stat-value">{{"%.2f"|format(envelope_totals.total_limit)}} €</div><div class="stat-label">plán</div></div>
<div class="stat"><div class="stat-value">{{"%.2f"|format(envelope_totals.total_spent)}} €</div><div class="stat-label">minuté</div></div>
<div class="stat"><div class="stat-value teal">{{"%.2f"|format(envelope_totals.total_remaining)}} €</div><div class="stat-label">ostáva</div></div>
</div>
{% for r in envelope_rows[:3] %}
<div class="deferred-mini-row"><span>{{r.category}}</span><span>{{"%.2f"|format(r.remaining)}} € ostáva</span></div>
{% endfor %}
<a href="/envelopes"><button type="button">Spravovať obálky</button></a>
</div>

<div class="card summary-card activity-summary">
<div class="summary-card-head"><h2>🕘 Nedávna aktivita</h2><a class="summary-card-link" href="/history">Zobraziť všetky →</a></div>
{% if audit_entries %}
{% for a in audit_entries[:5] %}
<div class="deferred-mini-row"><span>{{audit_action_label.get(a.action, a.action)}}</span><span class="small">{{a.at}}</span></div>
{% endfor %}
{% else %}<div class="small">Zatiaľ žiadna aktivita.</div>{% endif %}
<a href="/history"><button type="button">Celá história</button></a>
</div>
{% endif %}

{% if active_view == 'payments' %}
<div class="view-tabs">
<a href="#po-splatnosti" class="view-tab tab-red">Po splatnosti <span class="tab-badge">{{unpaid_overdue|length}}</span></a>
<a href="#coskoro" class="view-tab tab-orange">Čoskoro <span class="tab-badge">{{unpaid_soon|length}}</span></a>
<a href="#caka" class="view-tab tab-blue">Čaká <span class="tab-badge">{{unpaid_pending|length}}</span></a>
<a href="#zaplatene" class="view-tab tab-green">Zaplatené <span class="tab-badge">{{paid|length}}</span></a>
</div>

<div class="card section" id="po-splatnosti">
<h2>Po splatnosti ({{unpaid_overdue|length}})</h2>
{% if unpaid_overdue %}{{ unpaid_rows(unpaid_overdue, 'overdue') }}{% else %}<div class="small">Nič po splatnosti. ✅</div>{% endif %}
</div>

<div class="card section" id="coskoro">
<h2>Čoskoro (do 3 dní) ({{unpaid_soon|length}})</h2>
{% if unpaid_soon %}{{ unpaid_rows(unpaid_soon, 'soon') }}{% else %}<div class="small">Nič v najbližších dňoch.</div>{% endif %}
</div>

<div class="card section" id="caka">
<h2>Čaká na potvrdenie ({{unpaid_pending|length}})</h2>
{% if unpaid_pending %}{{ unpaid_rows(unpaid_pending, 'pending') }}{% else %}<div class="small">Nič nečaká na zaplatenie. ✅</div>{% endif %}
</div>

<details class="card section" id="zaplatene" open>
<summary>Zaplatené ({{paid|length}})</summary>
{% if paid %}
<div class="task-card-list">
{% for p in paid %}
<div class="task-card paid">
<div class="task-card-head">
<span class="task-card-name">{{p.name}}</span>
<span class="task-card-amount paid">{{p.amount}} €</span>
</div>
<div class="task-card-meta"><span class="badge {{state_badge_class.get(p.state,'')}}">{{state_label.get(p.state, p.state)}}</span></div>
</div>
{% endfor %}
</div>
{% else %}<div class="small">Zatiaľ nič zaplatené v tomto cykle.</div>{% endif %}
</details>

<div class="card">
<h2>Môžem minúť?</h2>
<form method="get" action="/payments">
<div class="inline"><input name="test" placeholder="napr. 50" value="{{test_amount}}"><button>Otestovať</button></div>
</form>
{% if test_result %}<pre>{{test_result}}</pre>{% endif %}
</div>

<div class="card">
<h2>Platby (všetky, vrátane šablón)</h2>
<div class="small">Stav platí pre aktuálny cyklus ({{cycle_key}}). Úprava platby mení iba šablónu, nie stav v tomto cykle.</div>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th>Frekvencia</th><th>Stav</th><th></th></tr>
{% for x in payments %}
{% set rx = payments_resolved[loop.index0] %}
<tr>
<td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('day')}}</td>
<td>{{freq_label.get(x.get('frequency'), x.get('frequency'))}}{% if x.get('frequency')=='custom_months' %} / {{x.get('every_months')}} mes.{% endif %}</td>
<td><span class="badge {{state_badge_class.get(rx.state,'')}}">{{state_label.get(rx.state, rx.state)}}</span>{% if rx.state=='deferred' and rx.get('deferred_to') %}<br><span class="small">do {{rx.deferred_to}}</span>{% endif %}</td>
<td class="actions-stack">
<form method="post" action="/payment/state/{{loop.index0}}">
<select name="state">
{% for s in selectable_states %}<option value="{{s}}" {% if rx.state==s %}selected{% endif %}>{{state_label.get(s,s)}}</option>{% endfor %}
</select>
<button class="secondary">Nastaviť</button>
</form>
{{ defer_widget(x.get('id',''), cycle_key, '↷ Odložiť') }}
<form method="get" action="/edit/payment/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/payment/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>

<div class="card section">
<h2>Jednorazové platby</h2>
<div class="small">Platí, iba kým nastane jej termín v tomto mesiaci. Ráta sa do bezpečne minúť rovnako ako pravidelná platba.</div>
{% if onetime_resolved %}
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Termín</th><th>Priorita</th><th>Stav</th><th></th></tr>
{% for x in onetime_resolved %}
<tr>
<td>{{x.name}}</td><td>{{x.amount}} €</td><td>{{x.due_date}}</td><td>{{priority_label.get(x.get('priority'), x.get('priority','-'))}}</td>
<td><span class="badge {{state_badge_class.get(x.state,'')}}">{{state_label.get(x.state, x.state)}}</span>{% if x.state=='deferred' and x.get('deferred_to') %}<br><span class="small">do {{x.deferred_to}}</span>{% endif %}</td>
<td class="actions-stack">
<form method="post" action="/onetime/state/{{x._index}}">
<select name="state">
{% for s in selectable_states %}<option value="{{s}}" {% if x.state==s %}selected{% endif %}>{{state_label.get(s,s)}}</option>{% endfor %}
</select>
<button class="secondary">Nastaviť</button>
</form>
<form method="post" action="/onetime/defer/{{x._index}}"><button class="secondary">Odložiť o 7 dní</button></form>
<form method="post" action="/onetime/delete/{{x._index}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
{% else %}<div class="small">Zatiaľ žiadna jednorazová platba tento mesiac.</div>{% endif %}
</div>

<div class="card section">
<h2>Dlhy</h2>
<div class="small">Dlžím ja: znižuje bezpečne minúť, keď je nesplatené a v termíne. Dlžia mne: len sledovanie, nezvyšuje bezpečne minúť, kým to reálne nepríde na účet.</div>
{% if debts %}
<div class="table-scroll">
<table><tr><th>Smer</th><th>Názov</th><th>Suma</th><th>Termín</th><th>Stav</th><th></th></tr>
{% for d in debts %}
<tr>
<td>{{debt_direction_label.get(d.direction, d.direction)}}</td>
<td>{{d.name}}{% if d.get('note') %}<br><span class="small">{{d.note}}</span>{% endif %}</td>
<td>{{"%.2f"|format(d.amount)}} €</td>
<td>{{d.get('due_date','-')}}</td>
<td><span class="badge {% if d.state in ('paid_me','received') %}ok{% elif d.state=='deferred' %}warn{% endif %}">{{debt_state_label.get(d.state, d.state)}}</span></td>
<td class="actions-stack">
<form method="post" action="/debt/state/{{loop.index0}}">
<select name="state">
{% for s in debt_states_by_direction.get(d.direction, []) %}<option value="{{s}}" {% if d.state==s %}selected{% endif %}>{{debt_state_label.get(s,s)}}</option>{% endfor %}
</select>
<button class="secondary">Nastaviť</button>
</form>
<form method="post" action="/debt/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
{% else %}<div class="small">Zatiaľ žiadny dlh.</div>{% endif %}
</div>
{% endif %}

{% if active_view == 'deferred' %}
<div class="card summary-card">
<div class="summary-card-head"><h2>Odložené platby ({{deferred|length}})</h2></div>
<div class="summary-stats">
<div class="stat"><span class="stat-value warn">{{deferred|length}}</span><span class="stat-label">odložených</span></div>
<div class="stat"><span class="stat-value">{{"%.2f"|format(deferred|sum(attribute='amount'))}} €</span><span class="stat-label">spolu</span></div>
{% if deferred_overdue %}<div class="stat"><span class="stat-value bad">{{deferred_overdue|length}}</span><span class="stat-label">po termíne</span></div>{% endif %}
</div>
<div class="small">Odložená platba nikdy nezmizne — po dosiahnutí dátumu sa automaticky vráti medzi nezaplatené.</div>
</div>

{% if deferred %}
<div class="view-tabs">
<a href="#d-po-terminie" class="view-tab tab-red">Po termíne <span class="tab-badge">{{deferred_overdue|length}}</span></a>
<a href="#d-coskoro" class="view-tab tab-orange">Čoskoro <span class="tab-badge">{{deferred_soon|length}}</span></a>
<a href="#d-neskor" class="view-tab tab-blue">Neskôr <span class="tab-badge">{{deferred_later|length}}</span></a>
</div>

<div class="card section" id="d-po-terminie">
<h2>Po termíne</h2>
{% if deferred_overdue %}{{ deferred_rows(deferred_overdue|sort(attribute='deferred_to')) }}{% else %}<div class="small">Nič po termíne. ✅</div>{% endif %}
</div>

<div class="card section" id="d-coskoro">
<h2>Čoskoro (do 7 dní)</h2>
{% if deferred_soon %}{{ deferred_rows(deferred_soon|sort(attribute='deferred_to')) }}{% else %}<div class="small">Nič v najbližších 7 dňoch.</div>{% endif %}
</div>

<div class="card section" id="d-neskor">
<h2>Neskôr</h2>
{% if deferred_later %}{{ deferred_rows(deferred_later|sort(attribute='deferred_to')) }}{% else %}<div class="small">Nič ďalšie odložené.</div>{% endif %}
</div>
{% else %}
<div class="card section"><div class="small">Žiadne odložené platby. ✅</div></div>
{% endif %}
{% endif %}

{% if active_view == 'expenses' %}
<div class="card">
<h2>Výdavky navyše</h2>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Dátum</th><th></th></tr>
{% for x in expenses %}
<tr><td>{{x.get('name')}}{% if x.get('source')=='ocr' %} <span class="badge">OCR{% if x.get('merchant') %}: {{x.merchant}}{% endif %}</span>{% endif %}</td><td>{{x.get('amount')}} €</td><td>{{x.get('date')}}</td>
<td class="actions">
<form method="get" action="/edit/expense/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/expense/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>
{% endif %}

{% if active_view == 'envelopes' %}
<details class="card section">
<summary>Obálky — správa (pridať novú / zmazať)</summary>
{% if envelope_rows %}
<div class="table-scroll">
<table><tr><th>Kategória</th><th>Limit</th><th>Minuté</th><th>Zostáva</th><th>Priemer/mesiac</th><th></th></tr>
{% for r in envelope_rows %}
<tr>
<td>{{r.category}}</td>
<td>{{"%.2f"|format(r.monthly_limit)}} €</td>
<td>{{"%.2f"|format(r.spent)}} €</td>
<td class="{% if r.over_budget %}bad{% else %}ok{% endif %}">{{"%.2f"|format(r.remaining)}} €</td>
<td class="small">{{"%.2f"|format(r.avg_3m)}} €</td>
<td class="actions">
<form method="post" action="/envelope/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td>
</tr>
{% endfor %}
<tr><td><strong>Spolu</strong></td><td><strong>{{"%.2f"|format(envelope_totals.total_limit)}} €</strong></td>
<td><strong>{{"%.2f"|format(envelope_totals.total_spent)}} €</strong></td>
<td class="{% if envelope_totals.total_remaining < 0 %}bad{% else %}ok{% endif %}"><strong>{{"%.2f"|format(envelope_totals.total_remaining)}} €</strong></td>
<td></td><td></td></tr>
</table>
</div>
{% else %}<div class="small">Zatiaľ žiadna obálka. Pridaj limit pre kategóriu vľavo.</div>{% endif %}
</details>
{% endif %}

{% if active_view == 'settings' %}
<div class="card">
<h2>Príjmy</h2>
<div class="table-scroll">
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th></th></tr>
{% for x in incomes %}
<tr><td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('day')}}</td>
<td class="actions">
<form method="get" action="/edit/income/{{loop.index0}}"><button class="secondary">Upraviť</button></form>
<form method="post" action="/income/delete/{{loop.index0}}"><button class="danger">Zmazať</button></form>
</td></tr>
{% endfor %}
</table>
</div>
</div>

<details class="card danger-zone">
<summary>⚠️ Nebezpečná zóna — vymazať všetko</summary>
<p class="small">
Zmaže úplne všetky dáta (platby, výdavky, obálky, dlhy, históriu, účtenky, nastavenia) a spustí sa
odznova prvotný sprievodca. Pred zmazaním sa <strong>automaticky uloží záloha</strong> so značkou dátumu a
času do <code>backups/</code> na serveri — dá sa z nej v prípade potreby obnoviť ručne. Táto akcia sa
z appky vrátiť nedá.
</p>
{% if request.args.get('reset_error') %}
<div class="small" style="color:var(--red);font-weight:700">Kód sa nezhodoval, nič sa nezmazalo. Skús to znova.</div>
{% endif %}
<form method="post" action="/settings/reset" id="reset-form">
<label>Na potvrdenie napíš presne: {{ reset_confirm_code }}</label>
<input type="text" name="confirm_code" id="reset-confirm-input" autocomplete="off" placeholder="{{ reset_confirm_code }}">
<div class="btn-row"><button type="submit" class="danger" id="reset-submit-btn" data-code="{{ reset_confirm_code }}" disabled>Vymazať všetko a začať odznova</button></div>
</form>
</details>
{% endif %}

{% if active_view == 'history' %}
<div class="card">
<h2>História zmien ({{audit_entries|length}})</h2>
{% if audit_entries %}
<div class="timeline">
{% for day, day_entries in audit_entries|groupby('day')|reverse %}
<div class="timeline-day">
<div class="timeline-day-label">{{day}}</div>
<div class="timeline-list">
{% for a in day_entries %}
<div class="timeline-row">
<span class="timeline-time">{{a.time}}</span>
<span class="timeline-action">{{audit_action_label.get(a.action, a.action)}}</span>
<span class="timeline-detail">{{a.detail}}</span>
</div>
{% endfor %}
</div>
</div>
{% endfor %}
</div>
{% else %}<div class="small">Zatiaľ žiadna aktivita.</div>{% endif %}
</div>

<details class="card">
<summary>Technický výstup</summary>
<pre>{{core}}</pre>
</details>
{% endif %}
</main>
</div>

<script>
/* BP_APP_SHELL_PATCH_V1 */
(function(){
  function ready(fn){ if(document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function(){
    const body = document.body;
    const nav = document.querySelector(".topnav");
    if(nav && !document.querySelector(".menu-toggle")){
      nav.id = "appDrawer";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "menu-toggle";
      btn.setAttribute("aria-label", "Otvoriť menu");
      btn.textContent = "☰";
      const overlay = document.createElement("div");
      overlay.className = "drawer-overlay";
      document.body.insertBefore(overlay, document.body.firstChild);
      document.body.insertBefore(btn, document.body.firstChild);
      function close(){ nav.classList.remove("open"); overlay.classList.remove("open"); }
      function toggle(){ nav.classList.toggle("open"); overlay.classList.toggle("open"); }
      btn.addEventListener("click", toggle);
      overlay.addEventListener("click", close);
      nav.querySelectorAll("a").forEach(a => a.addEventListener("click", close));
    }

    // Add labels to responsive table cards from header cells.
    document.querySelectorAll("table").forEach(function(table){
      const labels = Array.from(table.querySelectorAll("tr:first-child th")).map(th => th.textContent.trim());
      table.querySelectorAll("tr").forEach(function(row, idx){
        if(idx === 0) return;
        row.querySelectorAll("td").forEach(function(td, i){
          if(labels[i] && !td.hasAttribute("data-label")) td.setAttribute("data-label", labels[i]);
        });
      });
    });

    // Replace payment dropdown-only workflow with tap-friendly direct buttons.
    document.querySelectorAll('.actions-stack form[action*="/payment/state/"]').forEach(function(form){
      if(form.parentElement.querySelector(".quick-actions")) return;
      const action = form.getAttribute("action");
      const quick = document.createElement("div");
      quick.className = "quick-actions";
      const items = [
        ["paid_me", "Z účtu", "pay-main"],
        ["paid_other", "Iný", "pay-other"],
        ["paid_reserve", "Rezerva", "pay-reserve"],
        ["pending", "Nezaplatené", "reset"]
      ];
      items.forEach(function(it){
        const f = document.createElement("form");
        f.method = "post";
        f.action = action;
        f.className = it[2];
        f.innerHTML = '<input type="hidden" name="state" value="'+it[0]+'"><button type="submit">'+it[1]+'</button>';
        quick.appendChild(f);
      });
      const defer = form.parentElement.querySelector('form[action*="/payment/defer/"]');
      if(defer){
        const df = defer.cloneNode(true);
        df.className = "defer";
        const b = df.querySelector("button");
        if(b) b.textContent = "Odložiť";
        quick.appendChild(df);
        defer.style.display = "none";
      }
      form.parentElement.insertBefore(quick, form.parentElement.firstChild);
    });
  });
})();
</script>





<script>
/* BP_UX_SAFETY_V2 */
(function(){
  function ready(fn){
    if(document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function norm(s){ return (s || "").trim().toLowerCase(); }

  function sectionByExactHeading(text){
    const headings = Array.from(document.querySelectorAll("h2"));
    const h = headings.find(x => norm(x.textContent) === norm(text));
    return h ? (h.closest(".card, .section") || h.parentElement) : null;
  }

  function sectionByHeadingPrefix(prefix){
    const heads = Array.from(document.querySelectorAll("h2, summary"));
    const h = heads.find(x => norm(x.textContent).indexOf(norm(prefix)) === 0);
    return h ? (h.closest(".card, .section") || h.parentElement) : null;
  }

  function todayIso(){
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function relabelCards(){
    document.querySelectorAll(".metric .label, .label").forEach(function(el){
      const txt = (el.textContent || "").trim();

      if(txt.toLowerCase().includes("bezpečne minúť")){
        el.textContent = "Odhadovaný zostatok po zadaných platbách";
        el.classList.add("warning-label");
      }

      if(txt.toLowerCase().includes("na deň do výplaty")){
        el.textContent = "Denný odhad po zadaných platbách";
      }

      if(txt.toLowerCase().includes("odhad po najbližšej výplate")){
        el.textContent = "Odhad po najbližšej výplate";
        el.classList.add("projection-label");
      }
    });
  }

  function addLastUpdate(){
    if(document.querySelector(".last-update-card")) return;

    const card = document.createElement("div");
    card.className = "last-update-card";
    card.innerHTML =
      '<strong>Posledná aktualizácia:</strong> ' +
      'stav účtu a platby sú manuálne zadávané. ' +
      'Ak čísla nesedia, najprv uprav aktuálny stav účtu.';

    const main = document.querySelector(".main") || document.querySelector(".app") || document.body;
    const first = main.firstElementChild;
    if(first) main.insertBefore(card, first);
    else main.appendChild(card);
  }

  function buildRow(item, groupClass){
    const r = document.createElement("div");
    r.className = "safety-review-row" + (groupClass ? " " + groupClass : "");
    r.innerHTML =
      '<div class="safety-review-name"></div>' +
      '<div class="safety-review-sum"></div>' +
      '<div class="safety-review-x" title="Nezaplatené">✕</div>' +
      '<div class="safety-review-due"></div>' +
      '<div class="safety-review-actions"></div>';
    r.querySelector(".safety-review-name").textContent = item.name + (item.note ? " — " + item.note : "");
    r.querySelector(".safety-review-sum").textContent = item.sum;
    r.querySelector(".safety-review-due").textContent = item.dueText || "";
    if(item.badge){
      const b = document.createElement("span");
      b.className = "badge " + (item.badgeClass || "");
      b.textContent = item.badge;
      r.querySelector(".safety-review-x").replaceWith(b);
    }
    if(item.payForm){
      r.querySelector(".safety-review-actions").appendChild(item.payForm.cloneNode(true));
    }
    if(item.deferWidget){
      r.querySelector(".safety-review-actions").appendChild(item.deferWidget.cloneNode(true));
    }
    return r;
  }

  function addGroup(list, title, items, groupClass, collapsedByDefault){
    if(!items.length) return;
    const wrap = collapsedByDefault ? document.createElement("details") : document.createElement("div");
    wrap.className = "safety-review-group";
    const heading = collapsedByDefault ? document.createElement("summary") : document.createElement("div");
    heading.className = "safety-review-group-title";
    heading.textContent = title + " (" + items.length + ")";
    wrap.appendChild(heading);
    const body = document.createElement("div");
    body.className = "safety-review-list";
    items.forEach(function(item){ body.appendChild(buildRow(item, groupClass)); });
    wrap.appendChild(body);
    list.appendChild(wrap);
  }

  function addUnpaidReview(){
    if(document.querySelector(".safety-review")) return;

    const unpaidSection = sectionByExactHeading("Nezaplatené / treba zaplatiť");
    const deferredSection = sectionByExactHeading("Odložené");
    const paidSection = sectionByHeadingPrefix("Zaplatené");
    if(!unpaidSection) return;

    const now = todayIso();
    const overdue = [], soon = [], pending = [];

    function scrapeActions(row){
      return {
        payForm: row.querySelector(".paid-quick-form"),
        deferWidget: row.querySelector(".defer-widget"),
      };
    }

    function nameAndNote(cell){
      const noteEl = cell.querySelector(".small");
      const note = noteEl ? noteEl.textContent.trim() : "";
      const clone = cell.cloneNode(true);
      const noteClone = clone.querySelector(".small");
      if(noteClone) noteClone.remove();
      return {name: clone.textContent.trim(), note: note};
    }

    Array.from(unpaidSection.querySelectorAll("tbody tr")).forEach(function(row){
      const cells = Array.from(row.querySelectorAll("td"));
      if(cells.length < 3) return;
      const parsed = nameAndNote(cells[0]);
      const name = parsed.name, note = parsed.note;
      const sum = (cells[1].innerText || cells[1].textContent || "").trim();
      const due = (cells[2].innerText || cells[2].textContent || "").trim();
      if(!name || !sum) return;

      const actions = scrapeActions(row);

      const isOverdue = due && due < now;
      const daysUntil = due ? Math.round((new Date(due) - new Date(now)) / 86400000) : null;
      const isSoon = !isOverdue && daysUntil !== null && daysUntil >= 0 && daysUntil <= 3;
      const dueText = due ? (isOverdue ? "Po splatnosti: " + due : "Termín: " + due) : "Termín nezadaný";
      const item = {name:name, note:note, sum:sum, dueText:dueText, payForm:actions.payForm, deferWidget:actions.deferWidget, due:due};

      if(isOverdue) overdue.push(item);
      else if(isSoon) soon.push(item);
      else pending.push(item);
    });

    [overdue, soon, pending].forEach(function(arr){
      arr.sort(function(a,b){ return (a.due||"").localeCompare(b.due||""); });
    });

    const deferred = [];
    if(deferredSection){
      Array.from(deferredSection.querySelectorAll("tbody tr")).forEach(function(row){
        const cells = Array.from(row.querySelectorAll("td"));
        if(cells.length < 3) return;
        const name = (cells[0].innerText || cells[0].textContent || "").trim();
        const sum = (cells[1].innerText || cells[1].textContent || "").trim();
        const to = (cells[2].innerText || cells[2].textContent || "").trim();
        if(!name || !sum) return;
        const actions = scrapeActions(row);
        deferred.push({
          name:name, sum:sum, dueText: "", badge: to || "Odložené", badgeClass:"warn",
          payForm: actions.payForm, deferWidget: actions.deferWidget,
        });
      });
    }

    const paid = [];
    if(paidSection){
      Array.from(paidSection.querySelectorAll("tbody tr")).forEach(function(row){
        const cells = Array.from(row.querySelectorAll("td"));
        if(cells.length < 3) return;
        const name = (cells[0].innerText || cells[0].textContent || "").trim();
        const sum = (cells[1].innerText || cells[1].textContent || "").trim();
        const stateEl = cells[2].querySelector(".badge");
        const stateText = (stateEl ? stateEl.textContent : cells[2].textContent || "").trim();
        if(!name || !sum) return;
        paid.push({name:name, sum:sum, dueText:"", badge: stateText || "Zaplatené", badgeClass:"ok"});
      });
    }

    if(!overdue.length && !soon.length && !pending.length && !deferred.length && !paid.length) return;

    const card = document.createElement("section");
    card.className = "safety-review";
    card.id = "payment-review";
    card.innerHTML =
      '<h2>Platby</h2>' +
      '<div class="hint">' +
        'Dátum splatnosti nikdy neoznačí platbu automaticky — iba manuálne potvrdenie. ' +
        (overdue.length ? '<strong style="color:#fecaca">Po splatnosti: '+overdue.length+'</strong>' : '') +
      '</div>' +
      '<div class="safety-review-groups"></div>';

    const groups = card.querySelector(".safety-review-groups");
    addGroup(groups, "Po splatnosti", overdue, "overdue", false);
    addGroup(groups, "Splatné čoskoro", soon, "due-soon", false);
    addGroup(groups, "Čaká na potvrdenie", pending, "", false);
    addGroup(groups, "Odložené", deferred, "deferred", true);
    addGroup(groups, "Zaplatené", paid, "paid", true);

    const main = document.querySelector(".main") || document.querySelector(".app") || document.body;
    const summary = document.querySelector(".summarygrid");

    if(summary && summary.parentElement){
      summary.parentElement.insertBefore(card, summary);
    } else {
      main.insertBefore(card, main.firstChild);
    }
  }

  function markOverdueRows(){
    const unpaidSection = sectionByExactHeading("Nezaplatené / treba zaplatiť");
    if(!unpaidSection) return;

    const now = todayIso();

    unpaidSection.querySelectorAll("tbody tr").forEach(function(row){
      const cells = Array.from(row.querySelectorAll("td"));
      if(cells.length < 3) return;

      const due = (cells[2].innerText || cells[2].textContent || "").trim();
      if(due && due < now){
        row.classList.add("overdue");
        row.style.borderColor = "rgba(239,68,68,.75)";
        row.style.background = "rgba(127,29,29,.22)";
      }
    });
  }

  ready(function(){
    relabelCards();
    addLastUpdate();
    addUnpaidReview();
    markOverdueRows();
  });
})();
</script>


<script>
/* BP_BALANCE_FIRST_V1 */
(function(){
  function ready(fn){ if(document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  function txt(el){ return (el.textContent || "").trim().toLowerCase(); }

  ready(function(){
    // Hide cards/sections that are about income/payday/projection.
    document.querySelectorAll(".card,.section").forEach(function(card){
      const t = txt(card);
      if(
        t.includes("príjem") ||
        t.includes("výplata") ||
        t.includes("najbližšej výplate") ||
        t.includes("ďalšia výplata")
      ){
        // Do not hide payment cards that only mention "do výplaty" in old labels.
        if(!t.includes("nezaplatené / treba zaplatiť") && !t.includes("platby")){
          card.classList.add("hidden-income-card");
        }
      }
    });

    // Relabel old labels defensively.
    document.querySelectorAll(".metric .label, .label, h2, h3").forEach(function(el){
      let v = el.textContent || "";
      v = v.replace(/Bezpečne minúť teraz \(pred výplatou\)/gi, "Odhadovaný zostatok po zadaných platbách");
      v = v.replace(/Bezpečne minúť/gi, "Odhadovaný zostatok");
      v = v.replace(/Na deň do výplaty/gi, "Denný orientačný zostatok");
      v = v.replace(/Nezaplatené do výplaty/gi, "Nezaplatené zadané platby");
      v = v.replace(/Chýba do výplaty/gi, "Chýba po zadaných platbách");
      v = v.replace(/Odhad po najbližšej výplate.*$/gi, "Voliteľný budúci príjem");
      el.textContent = v;
    });

    // Add explanation banner near top.
    if(!document.querySelector(".balance-first-note")){
      const note = document.createElement("div");
      note.className = "balance-first-note";
      note.innerHTML =
        '<strong>Balance-first režim:</strong> výplata sa nepočíta automaticky. ' +
        'Zdroj pravdy je aktuálny stav účtu, ktorý ručne zadáš. ' +
        'Odhad = aktuálny stav účtu mínus nezaplatené zadané platby.';

      const main = document.querySelector(".main") || document.querySelector(".app") || document.body;
      main.insertBefore(note, main.firstElementChild || null);
    }
  });
})();
</script>


<script>
/* BP_EDITABLE_ENVELOPES_V1 */
(function(){
  function ready(fn){
    if(document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function eur(v){
    return Number(v || 0).toLocaleString("sk-SK", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }) + " €";
  }

  function envelopeIcon(name){
    const n = (name || "").toLowerCase();
    if(/strava|potravin|jedlo|food/.test(n)) return "🛒";
    if(/nafta|palivo|fuel|benzin/.test(n)) return "⛽";
    if(/byv|domac|najom|hypotek/.test(n)) return "🏠";
    if(/zabav|volny|hobby/.test(n)) return "🎮";
    if(/oblec|shop/.test(n)) return "👕";
    if(/zdrav|lekar|liek/.test(n)) return "💊";
    return "💶";
  }

  function addCard(summary){
    if(document.querySelector(".editable-envelopes")) return;

    const envelopes = summary.envelope_items || [];
    if(!envelopes.length) return;

    const total = envelopes.reduce(function(sum, e){
      return sum + Number(e.budget ?? e.amount ?? 0);
    }, 0);

    const card = document.createElement("section");
    card.className = "editable-envelopes";
    card.id = "envelopes";
    card.innerHTML =
      '<h2>Obálky</h2>' +
      '<div class="hint">Mesačné rozpočty po kategóriách. Zostávajúca suma sa odpočítava v reálnom odhade. Plán spolu: <strong>'+eur(total)+'</strong></div>' +
      '<div class="envelope-grid"></div>';

    const grid = card.querySelector(".envelope-grid");

    envelopes.forEach(function(e){
      const budget = Number(e.budget ?? e.amount ?? 0);
      const spent = Number(e.spent || 0);
      const remaining = Number(e.remaining || 0);
      const over = Number(e.over || 0);
      const pct = budget > 0 ? Math.min((spent / budget) * 100, 100) : 0;
      const nearlyExhausted = !over && budget > 0 && (remaining / budget) <= 0.15;
      const state = over > 0 ? "over" : nearlyExhausted ? "warn" : "";

      const envCard = document.createElement("div");
      envCard.className = "envelope-card" + (state ? " " + state : "");
      envCard.innerHTML =
        '<div class="envelope-card-head">' +
          '<span class="envelope-card-title"><span class="envelope-card-icon">'+envelopeIcon(e.name)+'</span>' +
          '<span class="envelope-card-name">'+(e.name||"Obálka")+'</span></span>' +
          '<span class="envelope-card-remaining">'+eur(remaining)+' ostáva</span>' +
        '</div>' +
        '<div class="envelope-progress-bar"><div class="envelope-progress-fill'+(state?" "+state:"")+'" style="width:'+pct+'%"></div></div>' +
        '<div class="envelope-card-sub">'+eur(budget)+' plán · '+eur(spent)+' minuté</div>' +
        (over > 0 ? '<div class="envelope-card-over">Prekročené o '+eur(over)+'</div>' : '') +
        '<div class="envelope-card-actions">' +
          '<a class="envelope-card-btn" href="#expense-quick">+ Výdavok</a>' +
          '<button type="button" class="envelope-card-btn secondary envelope-toggle-edit">Upraviť</button>' +
        '</div>' +
        '<form class="envelope-edit-row" method="post" action="/api/envelopes/update" hidden>' +
          '<input type="hidden" name="id">' +
          '<div><label>Názov</label><input name="name"></div>' +
          '<div><label>Mesačná suma</label><input name="amount" inputmode="decimal" type="number" step="0.01" min="0"></div>' +
          '<div><button type="submit">Uložiť</button></div>' +
        '</form>';

      const editForm = envCard.querySelector(".envelope-edit-row");
      editForm.querySelector('input[name="id"]').value = e.id || "";
      editForm.querySelector('input[name="name"]').value = e.name || "";
      editForm.querySelector('input[name="amount"]').value = budget;

      envCard.querySelector(".envelope-toggle-edit").addEventListener("click", function(){
        editForm.hidden = !editForm.hidden;
      });

      grid.appendChild(envCard);
    });

    const main = document.querySelector(".main") || document.querySelector(".app") || document.body;

    const afterSummary = document.querySelector(".envelope-summary");
    if(afterSummary && afterSummary.parentElement){
      afterSummary.parentElement.insertBefore(card, afterSummary.nextSibling);
    } else {
      main.insertBefore(card, main.firstElementChild || null);
    }
  }

  ready(function(){
    // Full envelope-grid cards are a /envelopes-only detail view now; the
    // dashboard shows a short summary instead (server-rendered).
    if(window.BP_ACTIVE_VIEW !== "envelopes") return;
    fetch("/api/balance-first-summary", {cache:"no-store"})
      .then(function(r){ return r.json(); })
      .then(addCard)
      .catch(function(err){ console.error("envelope editor failed", err); });
  });
})();
</script>


<script>
/* BP_TOP_REVIEW_DEFER_V1 */
(function(){
  function ready(fn){
    if(document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function cleanText(x){
    return (x || "").replace(/\s+/g, " ").trim();
  }

  function keyFromNameSum(name, sum){
    return cleanText(name).toLowerCase() + "||" + cleanText(sum).replace(/\s/g, "");
  }

  function findUnpaidSection(){
    const headings = Array.from(document.querySelectorAll("h2"));
    const h = headings.find(function(x){
      return cleanText(x.textContent).toLowerCase() === "nezaplatené / treba zaplatiť";
    });
    return h ? (h.closest(".card, .section") || h.parentElement) : null;
  }

  function isPaidForm(form){
    if(!form) return false;
    if(form.querySelector('input[name="state"][value="paid_me"]')) return true;
    if(form.querySelector('input[name="state"][value="paid"]')) return true;
    const t = cleanText(form.textContent).toLowerCase();
    return t.includes("z účtu") || t.includes("zaplaten");
  }

  function isDeferForm(form){
    if(!form) return false;
    if(form.querySelector('input[name="state"][value="deferred"]')) return true;
    if(form.querySelector('select[name*="defer"]')) return true;
    if(form.querySelector('input[name*="defer"]')) return true;
    const t = cleanText(form.textContent).toLowerCase();
    return t.includes("odložiť") || t.includes("odloz") || t.includes("defer");
  }

  function buildOriginalFormMap(){
    const map = new Map();
    const section = findUnpaidSection();
    if(!section) return map;

    Array.from(section.querySelectorAll("tbody tr")).forEach(function(row){
      const cells = Array.from(row.querySelectorAll("td"));
      if(cells.length < 2) return;

      const name = cleanText(cells[0].innerText || cells[0].textContent);
      const sum = cleanText(cells[1].innerText || cells[1].textContent);
      if(!name || !sum) return;

      const forms = Array.from(row.querySelectorAll("form"));
      const paidForm = forms.find(isPaidForm);
      const deferForm = forms.find(isDeferForm);

      map.set(keyFromNameSum(name, sum), {
        paidForm: paidForm || null,
        deferForm: deferForm || null
      });
    });

    return map;
  }

  function patchTopRows(){
    const map = buildOriginalFormMap();
    if(!map.size) return;

    const rows = Array.from(document.querySelectorAll(
      ".safety-review-row, .unpaid-confirm-row, .manual-confirm-row"
    ));

    rows.forEach(function(row){
      if(row.dataset.deferPatched === "1") return;

      const nameEl = row.querySelector(".safety-review-name, .unpaid-confirm-name, .manual-confirm-name");
      const sumEl = row.querySelector(".safety-review-sum, .unpaid-confirm-sum, .manual-confirm-sum");
      const actions = row.querySelector(".safety-review-actions, .unpaid-confirm-actions, .manual-confirm-actions");

      if(!nameEl || !sumEl || !actions) return;

      const key = keyFromNameSum(nameEl.textContent, sumEl.textContent);
      const original = map.get(key);
      if(!original) return;

      // Existing top panel usually already has paid form, but normalize its label/class.
      const existingForms = Array.from(actions.querySelectorAll("form"));
      existingForms.forEach(function(f){
        if(isPaidForm(f)){
          f.classList.add("bp-paid-form");
          const b = f.querySelector("button");
          if(b) b.textContent = "✓ Zaplatené";
        }
      });

      if(original.deferForm && !actions.querySelector(".bp-defer-form")){
        const deferClone = original.deferForm.cloneNode(true);
        deferClone.classList.add("bp-defer-form");

        const button = deferClone.querySelector("button");
        if(button){
          button.textContent = "↷ Odložiť";
          button.title = "Odložiť platbu";
        }

        actions.appendChild(deferClone);
      }

      row.dataset.deferPatched = "1";
    });
  }

  // patchTopRows() is no longer called: BP_UX_SAFETY_V2's addUnpaidReview()
  // now builds the .safety-review-row actions (paid button + defer widget)
  // directly, correctly, including for carried-over deferred items. Calling
  // patchTopRows() here too would append a second, stale defer action onto
  // rows it already owns.
})();
</script>



<script>
/* BP_TOP_REAL_OVERVIEW_V5 */
(function(){
  function ready(fn){ if(document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  function eur(v){ return Number(v || 0).toLocaleString("sk-SK",{minimumFractionDigits:2,maximumFractionDigits:2})+" €"; }
  function cls(v){ const n=Number(v||0); if(n<0)return"bad"; if(n<100)return"warn"; return"good"; }
  function envCls(data, remainingEnv){
    const over = Number(data.envelopes_over_total||0) > 0;
    const total = Number(data.envelopes_total||0);
    if(over) return "warn";
    if(total > 0 && (remainingEnv/total) <= 0.15) return "warn";
    return "teal";
  }
  function formatUpdated(iso){
    const d = new Date(iso);
    if(isNaN(d.getTime())) return iso;
    const now = new Date();
    const pad = function(n){ return String(n).padStart(2,"0"); };
    const time = pad(d.getHours()) + ":" + pad(d.getMinutes());
    const sameDay = d.toDateString() === now.toDateString();
    if(sameDay) return "dnes " + time;
    return pad(d.getDate()) + "." + pad(d.getMonth()+1) + ". " + time;
  }

  function hideOldMetricCards(){
    document.querySelectorAll(".topgrid,.summarygrid,.envelope-summary,.fin-overview").forEach(function(el){
      el.classList.add("bp-hide-old-metrics");
    });
  }

  function render(data){
    hideOldMetricCards();
    if(document.querySelector(".real-top")) return;

    const remainingEnv = Number(data.envelopes_remaining_total ?? data.envelopes_total ?? 0);
    const finalValue = Number(data.estimated_after_payments_and_envelopes || 0);
    const missing = Number(data.missing_after_everything || 0);
    const envState = envCls(data, remainingEnv);

    const caption = finalValue < 0
      ? "Chýba " + eur(missing) + ", ak chceš pokryť všetky nezaplatené platby aj zostávajúce obálky."
      : "Po platbách a obálkach ostáva " + eur(finalValue) + ".";

    const updatedText = data.last_manual_review
      ? "Aktualizované: " + formatUpdated(data.last_manual_review)
      : "Stav účtu ešte nebol zadaný";

    const card = document.createElement("section");
    card.className = "real-top";
    card.innerHTML =
      '<div class="real-top-head"><h2>Reálny mesačný prehľad</h2></div>' +
      '<div class="real-hero">' +
        '<div class="real-hero-value '+cls(finalValue)+'">'+eur(finalValue)+'</div>' +
        '<div class="real-hero-caption '+(finalValue < 0 ? 'bad' : 'ok')+'">'+caption+'</div>' +
      '</div>' +
      '<div class="real-sub-grid">' +
        '<div class="real-metric"><div class="real-label">Účet</div><div class="real-value">'+eur(data.current_balance)+'</div></div>' +
        '<div class="real-metric"><div class="real-label">Nezaplatené</div><div class="real-value bad">-'+eur(data.unpaid_payments_total)+'</div></div>' +
        '<div class="real-metric"><div class="real-label">Obálky ostáva</div><div class="real-value '+envState+'">'+eur(remainingEnv)+'</div></div>' +
      '</div>' +
      '<div class="real-updated-line">' +
        '<button type="button" class="real-refresh-btn" title="Obnoviť">↻</button>' +
        '<span>'+updatedText+'</span>' +
      '</div>' +
      '<details class="real-balance-toggle" id="balance-update-field">' +
        '<summary>✎ Upraviť stav účtu</summary>' +
        '<form class="real-update" method="post" action="/api/balance/update">' +
          '<div><label>Nový stav účtu</label><input name="account_balance" inputmode="decimal" type="number" step="0.01" value="'+Number(data.current_balance||0)+'"></div>' +
          '<div><button type="submit">Uložiť stav</button></div>' +
        '</form>' +
      '</details>' +
      '<details class="real-formula"><summary>Vzorec výpočtu</summary>' +
      '<div class="real-calc">' +
        '<div>Aktuálny stav účtu</div><div class="amount">'+eur(data.current_balance)+'</div>' +
        '<div>- nezaplatené platby</div><div class="amount bad">-'+eur(data.unpaid_payments_total)+'</div>' +
        '<div>- zostávajúce obálky</div><div class="amount warn">-'+eur(remainingEnv)+'</div>' +
        '<div class="total">= reálny odhad</div><div class="amount total '+cls(finalValue)+'">'+eur(finalValue)+'</div>' +
      '</div></details>';

    const main=document.querySelector(".main") || document.querySelector(".app") || document.body;
    main.insertBefore(card, main.firstElementChild || null);

    const quick = document.createElement("div");
    quick.className = "quick-actions-grid";
    quick.innerHTML =
      '<a class="qa-btn qa-blue" href="/expenses#expense-quick">+ Výdavok</a>' +
      '<a class="qa-btn qa-purple" href="/receipts">📷 OCR bloček</a>' +
      '<a class="qa-btn qa-blue" href="/payments">✓ Platby</a>' +
      '<a class="qa-btn qa-orange" href="/deferred">↷ Odložené</a>' +
      '<a class="qa-btn qa-teal" href="/envelopes">✉ Obálky</a>' +
      '<a class="qa-btn qa-gray" href="#balance-update-field">✎ Stav účtu</a>';
    card.insertAdjacentElement("afterend", quick);

    const refreshBtn = card.querySelector(".real-refresh-btn");
    if(refreshBtn){
      refreshBtn.addEventListener("click", function(){
        refreshBtn.classList.add("spinning");
        setTimeout(function(){ window.location.reload(); }, 250);
      });
    }

    const balanceBtn = quick.querySelector(".qa-gray");
    if(balanceBtn){
      balanceBtn.addEventListener("click", function(e){
        const details = document.getElementById("balance-update-field");
        if(details){
          e.preventDefault();
          details.open = true;
          details.scrollIntoView({behavior:"smooth", block:"start"});
        }
      });
    }
  }

  ready(function(){
    hideOldMetricCards();
    setTimeout(hideOldMetricCards,500);
    setTimeout(hideOldMetricCards,1500);
    // The hero is a dashboard-only overview now; detail views (/payments,
    // /envelopes, ...) stay lean per the app-views layout.
    if(window.BP_ACTIVE_VIEW !== "dashboard") return;
    fetch("/api/balance-first-summary",{cache:"no-store"}).then(r=>r.json()).then(render).catch(console.error);
  });
})();
</script>

<script>
/* BP_DEFER_DATE_REQUIRED_V1: require a target date for every "Odložiť"
   action instead of a silent one-click +7-days. Event-delegated on
   document so it also covers .defer-widget instances that other
   patches (BP_UX_SAFETY_V2) clone into the payment-review card. */
(function(){
  function pad(n){ return String(n).padStart(2, "0"); }
  function iso(d){ return d.getFullYear() + "-" + pad(d.getMonth()+1) + "-" + pad(d.getDate()); }
  function endOfMonth(d){ return new Date(d.getFullYear(), d.getMonth()+1, 0); }

  document.addEventListener("click", function(e){
    const toggle = e.target.closest(".defer-toggle");
    if(toggle){
      const form = toggle.parentElement.querySelector(".defer-form");
      if(form) form.hidden = !form.hidden;
      return;
    }
    const cancel = e.target.closest(".defer-cancel");
    if(cancel){
      const form = cancel.closest(".defer-form");
      if(form) form.hidden = true;
      return;
    }
    const quick = e.target.closest(".defer-quick");
    if(quick){
      const form = quick.closest(".defer-form");
      const input = form ? form.querySelector(".defer-date-input") : null;
      if(!input) return;
      const today = new Date();
      let target = null;
      if(quick.dataset.quick === "7d"){
        target = new Date(today);
        target.setDate(target.getDate() + 7);
      } else if(quick.dataset.quick === "next_month"){
        target = new Date(today.getFullYear(), today.getMonth() + 1, today.getDate());
      } else if(quick.dataset.quick === "end_month"){
        target = endOfMonth(today);
      } else if(quick.dataset.quick === "today"){
        target = today;
      }
      if(target) input.value = iso(target);
      return;
    }
  });

  document.addEventListener("submit", function(e){
    const form = e.target.closest(".defer-form");
    if(!form) return;
    const input = form.querySelector(".defer-date-input");
    if(!input || !input.value){
      e.preventDefault();
      if(input) input.reportValidity();
    }
  });
})();
</script>

<script>
/* BP_EDIT_FORM_SCROLL_V1: the edit form for an income/payment/expense
   lives in the sidebar, which on mobile renders BELOW all the main
   content (.sidebar{order:2}) -- clicking "Upraviť" otherwise looks
   like nothing happened. Scroll it into view and flash a highlight so
   it's obvious where to look, on both desktop and mobile. */
(function(){
  function ready(fn){ if(document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function(){
    var id = window.BP_EDIT_TARGET;
    if(!id) return;
    var el = document.getElementById(id);
    if(!el) return;
    el.scrollIntoView({behavior:"smooth", block:"start"});
    el.classList.add("edit-target-flash");
    setTimeout(function(){ el.classList.remove("edit-target-flash"); }, 2200);
  });
})();
</script>

<script>
/* BP_FULL_RESET_CONFIRM_V1: "Vymazať všetko" only submits once the typed
   text exactly matches the required code -- this is a UX convenience
   only, the server independently re-checks the same code and rejects
   anything else (never trust client-side-only gating for something this
   destructive). A native confirm() is a second speed bump. */
(function(){
  function ready(fn){ if(document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function(){
    var form = document.getElementById("reset-form");
    var input = document.getElementById("reset-confirm-input");
    var btn = document.getElementById("reset-submit-btn");
    if(!form || !input || !btn) return;
    var required = (btn.dataset.code || "").toUpperCase();
    input.addEventListener("input", function(){
      btn.disabled = input.value.trim().toUpperCase() !== required;
    });
    form.addEventListener("submit", function(e){
      if(!window.confirm("Naozaj vymazať úplne všetko? Dá sa to vrátiť len ručne zo zálohy na serveri.")){
        e.preventDefault();
      }
    });
  });
})();
</script>

</body>
</html>
"""

def resolve_payments_for_cycle(payments, today):
    """Each template resolved to its due date for `today`'s month, plus the
    effective state/deferred_to for the current cycle. Same length/order as
    `payments`, so `loop.index0` still lines up for the management table
    and the per-payment action routes (/payment/state/<i>, /payment/defer/<i>)."""
    cycle_key = pe.get_current_cycle_key(today)
    events = pe.load_payment_events()
    resolved = []
    for idx, p in enumerate(payments):
        item = dict(p)
        item["due_date"] = ob.recurring_due_date(p, today.year, today.month)
        item["_index"] = idx
        resolved.append(item)
    return pe.apply_payment_events(resolved, events, cycle_key), cycle_key

def resolve_onetime_for_cycle(onetime, today):
    """One-time obligations due in `today`'s month, resolved to their
    effective state for the current cycle. `_index` preserves the position
    in the full onetime.json list (which may hold obligations due in other
    months too), so the per-item action routes edit the right entry."""
    cycle_key = pe.get_current_cycle_key(today)
    events = pe.load_payment_events()
    resolved = []
    for idx, item in enumerate(onetime):
        if ob.onetime_due_in_month(item, today.year, today.month):
            resolved_item = dict(item)
            resolved_item["due_date"] = date.fromisoformat(item["due_date"])
            resolved_item["_index"] = idx
            resolved.append(resolved_item)
    return pe.apply_payment_events(resolved, events, cycle_key)

def three_month_forecast(today, months=3):
    """Planned income/payments/balance for the current month plus the next
    `months - 1`, reusing budgetpilot.calc_month() — the same per-month
    computation the CLI's `simulate()` already prints, just not previously
    surfaced on the web dashboard. Only the current month's figures include
    debts (calc_month() only merges debts into the is_current_month branch,
    same limitation simulate() already has for future months)."""
    result = []
    year, month = today.year, today.month
    for _ in range(months):
        r = bp.calc_month(year, month)
        result.append({
            "label": f"{MONTH_NAME_SK.get(month, month)} {year}",
            "income_total": r["income_total"],
            "payment_total": r["payment_total"],
            "planned_month_balance": r["planned_month_balance"],
            "status": r["status"],
        })
        year, month = bp.next_month(year, month)
    return result

def render_page(edit_income=None, edit_payment=None, edit_expense=None, active_view="dashboard"):
    settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})
    incomes = load(INCOMES, [])
    payments = load(PAYMENTS, [])
    expenses = load(EXPENSES, [])
    setup_needed = ob.needs_setup(settings, payments)
    core = run_core()
    test_amount = request.args.get("test", "")
    test_result = run_core(["spend", test_amount]) if test_amount else ""

    today = date.today()
    payments_resolved, cycle_key = resolve_payments_for_cycle(payments, today)
    active_resolved = [
        p for p in payments_resolved
        if ob.is_recurring_active(payments[p["_index"]], today.year, today.month)
    ]
    # Deferred items are resolved separately below (resolve_deferred_carryovers),
    # since the naive per-cycle state here can't tell whether a deferred_to
    # date has actually arrived — exclude them here so they aren't double
    # counted between the two paths.
    groups = pe.group_payments_by_status(
        [p for p in active_resolved if p.get("state") != DEFERRED], today
    )

    # A deferred payment must never silently disappear once its target date
    # arrives — it re-promotes itself into this cycle's unpaid list instead
    # of staying bucketed as "deferred" (docs/balance_first_rules.md rules
    # 2-4). This is independent of, and additional to, that same payment's
    # own natural occurrence this cycle (rule 5: a recurring payment
    # carried over from an earlier month does not merge with or hide this
    # month's own fresh obligation).
    all_events = pe.load_payment_events()
    unpaid_carryovers, still_deferred = pe.resolve_deferred_carryovers(
        payments, all_events, cycle_key, today
    )
    groups["unpaid"] = sorted(
        groups["unpaid"] + unpaid_carryovers,
        key=lambda p: (pe.URGENCY_ORDER.get(p["urgency"], 9), p.get("due_date") or date.max),
    )
    groups["deferred"] = still_deferred

    # Split for the /payments view's three sections (dashboard requirements/
    # docs/navigation_layout.md) -- display-only grouping, never changes
    # what counts as unpaid.
    unpaid_overdue = [p for p in groups["unpaid"] if p["urgency"] == pe.OVERDUE]
    unpaid_soon = [p for p in groups["unpaid"] if p["urgency"] in (pe.DUE_TODAY, pe.SOON)]
    unpaid_pending = [p for p in groups["unpaid"] if p["urgency"] == pe.LATER]

    for p in groups["deferred"]:
        deferred_to_raw = p.get("deferred_to")
        p["days_left"] = (date.fromisoformat(deferred_to_raw) - today).days if deferred_to_raw else None

    # Split for the /deferred view's tabs -- same display-only grouping
    # pattern as unpaid_overdue/soon/pending above, never changes what
    # counts as deferred.
    deferred_overdue = [p for p in groups["deferred"] if p.get("days_left") is not None and p["days_left"] < 0]
    deferred_soon = [p for p in groups["deferred"] if p.get("days_left") is not None and 0 <= p["days_left"] <= 7]
    deferred_later = [p for p in groups["deferred"] if p.get("days_left") is None or p["days_left"] > 7]

    debts = load(DEBTS, [])

    onetime = load(ONETIME, [])
    onetime_resolved = resolve_onetime_for_cycle(onetime, today)

    forecast_months = three_month_forecast(today)

    envelope_defs = load(ENVELOPES, [])
    expenses_this_month = env.expenses_in_month(expenses, today.year, today.month)
    envelope_totals = env.envelopes_summary(envelope_defs, expenses_this_month)
    envelope_rows = [
        {**row, "avg_3m": env.average_monthly_spend(expenses, row["category"], 3, today)}
        for row in envelope_totals["rows"]
    ]

    dash = parse_dash(core)
    summary = {
        "balance": dash["balance"],
        "unpaid_total": dash["unpaid_total"],
        "shortfall": dash["shortfall"],
        "safe_to_spend": dash["money"],
        "daily_safe_to_spend": dash["day"],
        "projected_after_payday": dash["projected_after_payday"],
        "next_payday": dash["next_payday"] if dash["next_payday"] != "-" else (
            f"deň {settings.get('payday_day')}" if settings.get("payday_day") else "-"
        ),
    }

    income_form = {"name":"Výplata netto","amount":"2000","day":"15"}
    payment_form = payment_form_from_item(None)
    expense_form = {"name":"Potraviny","amount":"","date":date.today().isoformat()}

    if edit_income is not None and edit_income < len(incomes):
        income_form = incomes[edit_income]
    if edit_payment is not None and edit_payment < len(payments):
        payment_form = payment_form_from_item(payments[edit_payment])
    if edit_expense is not None and edit_expense < len(expenses):
        expense_form = expenses[edit_expense]

    receipt_review = None
    review_id = request.args.get("review_receipt")
    if review_id:
        review_path = RECEIPTS_DIR / f"{review_id}.review.json"
        if review_path.exists():
            stored = load(review_path, {})
            receipt_review = {
                "receipt_id": review_id,
                "image_path": stored.get("image_path", ""),
                "amount": stored.get("amount"),
                "date": stored.get("date") or today.isoformat(),
                "merchant": stored.get("merchant"),
                "candidates": stored.get("candidates", []),
            }

    return render_template_string(
        HTML,
        active_view=active_view,
        settings=settings, incomes=incomes, payments=payments, expenses=expenses,
        core=core, dash=dash, summary=summary, today=today.isoformat(),
        payments_resolved=payments_resolved, cycle_key=cycle_key,
        unpaid=groups["unpaid"], deferred=groups["deferred"], paid=groups["paid"],
        unpaid_overdue=unpaid_overdue, unpaid_soon=unpaid_soon, unpaid_pending=unpaid_pending,
        deferred_overdue=deferred_overdue, deferred_soon=deferred_soon, deferred_later=deferred_later,
        urgency_label_sk=URGENCY_LABEL_SK,
        payment_types=PAYMENT_TYPES, expense_types=EXPENSE_TYPES, freq_label=FREQ_LABEL,
        test_result=test_result, test_amount=test_amount,
        edit_income=edit_income, edit_payment=edit_payment, edit_expense=edit_expense,
        income_form=income_form, payment_form=payment_form, expense_form=expense_form,
        setup_needed=setup_needed,
        state_label=STATE_LABEL,
        state_badge_class=STATE_BADGE_CLASS, selectable_states=SELECTABLE_STATES,
        envelope_rows=envelope_rows, envelope_totals=envelope_totals,
        debts=debts, debt_state_label=DEBT_STATE_LABEL,
        debt_states_by_direction=DEBT_STATES_BY_DIRECTION,
        debt_direction_label=DEBT_DIRECTION_LABEL,
        onetime_resolved=onetime_resolved, priority_label=PRIORITY_LABEL,
        receipt_review=receipt_review,
        forecast_months=forecast_months,
        audit_entries=_with_day_and_time(list(reversed(audit_log.load_audit_log(AUDIT_LOG_PATH)))[:30]),
        audit_action_label=AUDIT_ACTION_LABEL,
        reset_confirm_code=RESET_CONFIRM_CODE,
    )

@app.route("/")
def index():
    return render_page(active_view="dashboard")

@app.route("/payments")
def payments_view():
    return render_page(active_view="payments")

@app.route("/deferred")
def deferred_view():
    return render_page(active_view="deferred")

@app.route("/envelopes")
def envelopes_view():
    return render_page(active_view="envelopes")

@app.route("/expenses")
def expenses_view():
    return render_page(active_view="expenses")

@app.route("/history")
def history_view():
    return render_page(active_view="history")

@app.route("/settings", methods=["GET"])
def settings_view():
    return render_page(active_view="settings")

@app.route("/receipts")
def receipts_view():
    return render_page(active_view="receipts")

@app.route("/edit/income/<int:i>")
def edit_income(i):
    return render_page(edit_income=i, active_view="settings")

@app.route("/edit/payment/<int:i>")
def edit_payment(i):
    return render_page(edit_payment=i, active_view="payments")

@app.route("/edit/expense/<int:i>")
def edit_expense(i):
    return render_page(edit_expense=i, active_view="expenses")

@app.post("/settings")
def settings_save():
    settings = load(SETTINGS, {"account_balance":0,"use_reserve":False,"safe_min":0})
    updates = {
        "account_balance": float(request.form.get("account_balance",0) or 0),
        "use_reserve": bool(request.form.get("use_reserve")),
        "safe_min": float(request.form.get("safe_min",0) or 0),
    }
    save(SETTINGS, ob.merge_settings(settings, updates))
    return go_home()

RESET_CONFIRM_CODE = "ZMAZAT"
RESET_DATA_FILES = [
    "settings.json", "incomes.json", "payments.json", "payment_events.json",
    "expenses.json", "envelopes.json", "debts.json", "onetime.json",
    "one_time_obligations.json", "snapshots.json", "receipts.json",
]

@app.post("/settings/reset")
def settings_reset():
    """Wipe every data file and start over from the first-run wizard.

    Guarded twice: the confirmation text must match exactly (server-side,
    never trusting the client-side JS gate alone), and nothing is deleted
    without a full backup succeeding first — backups/<timestamp>-full-reset/
    gets a complete copy of data/ (including receipt photos) before
    anything in the live data/ dir is touched.
    """
    code = (request.form.get("confirm_code") or "").strip().upper()
    if code != RESET_CONFIRM_CODE:
        return redirect("/settings?reset_error=1")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = BASE / "backups" / f"{ts}-full-reset"
    shutil.copytree(DATA, backup_dir / "data")

    for name in RESET_DATA_FILES:
        save(DATA / name, {} if name == "settings.json" else [])

    if RECEIPTS_DIR.exists():
        for f in RECEIPTS_DIR.iterdir():
            if f.is_file():
                f.unlink()

    save(AUDIT_LOG_PATH, [{
        "at": datetime.now().isoformat(timespec="seconds"),
        "action": "full_reset",
        "detail": f"backup: {backup_dir.name}",
    }])

    return redirect("/")

@app.post("/income/add")
def income_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(INCOMES, [])
        data.append({"name":request.form.get("name","Výplata"),"amount":float(amount),"day":int(request.form.get("day",1) or 1),"frequency":"monthly","start":"2026-01-01"})
        save(INCOMES, data)
    return go_home()

@app.post("/income/update/<int:i>")
def income_update(i):
    data = load(INCOMES, [])
    if i < len(data):
        data[i].update({"name":request.form.get("name","Výplata"),"amount":float(request.form.get("amount",0) or 0),"day":int(request.form.get("day",1) or 1)})
    save(INCOMES, data)
    return go_home()

@app.post("/income/delete/<int:i>")
def income_delete(i):
    data = load(INCOMES, [])
    if i < len(data): data.pop(i)
    save(INCOMES, data)
    return go_home()

def make_payment_from_form():
    """Fields the main-dashboard payment form actually submits. Used both
    to build a new payment and as the update dict when editing one — it
    must NOT include metadata (id, priority, flexibility, active, state,
    ...) the form doesn't expose, or an edit would clobber it."""
    typ = request.form.get("type","Iné")
    name = request.form.get("name","").strip() if typ == "Iné" else typ
    if not name: name = "Iné"
    day = int(request.form.get("day",1) or 1)
    month = int(request.form.get("month",1) or 1)
    year = int(request.form.get("year",2026) or 2026)
    freq = request.form.get("frequency","monthly")
    start = f"{year:04d}-{month:02d}-{day:02d}"
    item = {
        "name": name,
        "amount": float(request.form.get("amount",0) or 0),
        "day": day,
        "due_day": day,
        "frequency": freq,
        "start": start,
        "start_month": start[:7],
    }
    if freq == "custom_months":
        item["every_months"] = int(request.form.get("every_months",1) or 1)
    return item

@app.post("/payment/add")
def payment_add():
    amount = request.form.get("amount","").strip()
    if amount:
        data = load(PAYMENTS, [])
        item = ob.ensure_recurring_compatible(make_payment_from_form(), new_id=uuid.uuid4().hex[:8])
        data.append(item)
        save(PAYMENTS, data)
    return go_home()

@app.post("/payment/update/<int:i>")
def payment_update(i):
    data = load(PAYMENTS, [])
    if i < len(data):
        data[i] = ob.merge_payment_fields(data[i], make_payment_from_form())
    save(PAYMENTS, data)
    return go_home()

@app.post("/payment/state/<int:i>")
def payment_set_state(i):
    data = load(PAYMENTS, [])
    new_state = request.form.get("state", PENDING)
    if i < len(data) and new_state in SELECTABLE_STATES and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.set_payment_event(events, data[i]["id"], cycle_key, new_state)
        pe.save_payment_events(events)
        if new_state == PAID_ME:
            log_audit("payment_paid", f"{data[i].get('name')} {data[i].get('amount')} €")
    return go_home()

@app.post("/payment/defer/<int:i>")
def payment_defer(i):
    data = load(PAYMENTS, [])
    if i < len(data) and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.defer_payment_event(events, data[i]["id"], cycle_key, today)
        pe.save_payment_events(events)
        log_audit("payment_deferred", f"{data[i].get('name')} {data[i].get('amount')} €")
    return go_home()

@app.post("/payment/state/by-id")
def payment_set_state_by_id():
    """Identity-based counterpart to /payment/state/<i>: targets an
    explicit (payment_id, cycle_key) pair instead of an array index, so
    it also works for carried-over deferred items (see
    payment_events.resolve_deferred_carryovers), which live under their
    own origin cycle_key rather than the page's current one."""
    payment_id = request.form.get("payment_id", "").strip()
    cycle_key = request.form.get("cycle_key", "").strip()
    new_state = request.form.get("state", PENDING)
    if payment_id and cycle_key and new_state in SELECTABLE_STATES:
        events = pe.load_payment_events()
        events = pe.set_payment_event(events, payment_id, cycle_key, new_state)
        pe.save_payment_events(events)
        if new_state == PAID_ME:
            data = load(PAYMENTS, [])
            template = next((p for p in data if p.get("id") == payment_id), None)
            label = template.get("name") if template else payment_id
            log_audit("payment_paid", f"{label}")
    return go_home()

@app.post("/payment/defer/by-id")
def payment_defer_by_id():
    """Requires an explicit deferred_to date — replaces the old
    one-click +7-days /payment/defer/<i> for all UI defer actions (see
    docs/balance_first_rules.md: a deferred payment must always carry a
    concrete target date, never disappear on a silent auto-schedule).
    Empty or invalid dates are rejected (no-op), matching the "empty
    defer date must not save" / "invalid dates rejected" rules — past
    dates ARE accepted, since resolve_deferred_carryovers() will then
    correctly show the item as overdue-unpaid rather than hiding it.
    """
    payment_id = request.form.get("payment_id", "").strip()
    cycle_key = request.form.get("cycle_key", "").strip()
    deferred_to_raw = request.form.get("deferred_to", "").strip()
    note = request.form.get("note", "").strip()
    if not (payment_id and cycle_key and deferred_to_raw):
        return go_home()
    try:
        deferred_to = date.fromisoformat(deferred_to_raw)
    except ValueError:
        return go_home()
    events = pe.load_payment_events()
    events = pe.defer_payment_to_date(events, payment_id, cycle_key, deferred_to, note=note or None)
    pe.save_payment_events(events)
    data = load(PAYMENTS, [])
    template = next((p for p in data if p.get("id") == payment_id), None)
    label = template.get("name") if template else payment_id
    log_audit("payment_deferred", f"{label} -> {deferred_to.isoformat()}")
    return go_home()

@app.post("/payment/delete/<int:i>")
def payment_delete(i):
    data = load(PAYMENTS, [])
    if i < len(data): data.pop(i)
    save(PAYMENTS, data)
    return go_home()

@app.post("/expense/add")
def expense_add():
    amount = request.form.get("amount","").strip()
    if amount:
        name = request.form.get("name","Výdavok")
        merchant = request.form.get("merchant", "").strip()
        item = {
            "name": name,
            "amount": float(amount),
            "date": request.form.get("date", date.today().isoformat()),
            "source": receipts.SOURCE_MANUAL,
        }
        if merchant:
            item["merchant"] = merchant
        data = load(EXPENSES, [])
        data.append(item)
        save(EXPENSES, data)
        log_audit("expense_added", f"{name} {amount} €")
    return go_home()

@app.post("/expense/update/<int:i>")
def expense_update(i):
    data = load(EXPENSES, [])
    if i < len(data):
        updates = {
            "name": request.form.get("name","Výdavok"),
            "amount": float(request.form.get("amount",0) or 0),
            "date": request.form.get("date", date.today().isoformat()),
        }
        data[i] = {**data[i], **updates}
    save(EXPENSES, data)
    return go_home()

@app.post("/expense/delete/<int:i>")
def expense_delete(i):
    data = load(EXPENSES, [])
    if i < len(data): data.pop(i)
    save(EXPENSES, data)
    return go_home()

@app.post("/envelope/add")
def envelope_add():
    category = request.form.get("category", "").strip()
    limit_raw = request.form.get("monthly_limit", "").strip()
    if category and limit_raw:
        data = load(ENVELOPES, [])
        limit = float(limit_raw)
        for e in data:
            if e.get("category") == category:
                e["monthly_limit"] = limit
                break
        else:
            data.append({"category": category, "monthly_limit": limit})
        save(ENVELOPES, data)
    return go_home()

@app.post("/envelope/delete/<int:i>")
def envelope_delete(i):
    data = load(ENVELOPES, [])
    if i < len(data): data.pop(i)
    save(ENVELOPES, data)
    return go_home()

@app.post("/debt/add")
def debt_add():
    amount = request.form.get("amount", "").strip()
    name = request.form.get("name", "").strip()
    direction = request.form.get("direction", ob.I_OWE)
    if amount and name and direction in DEBT_STATES_BY_DIRECTION:
        data = load(DEBTS, [])
        data.append({
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "amount": float(amount),
            "direction": direction,
            "due_date": request.form.get("due_date", date.today().isoformat()),
            "state": PENDING,
            "note": request.form.get("note", "").strip(),
        })
        save(DEBTS, data)
    return go_home()

@app.post("/debt/state/<int:i>")
def debt_set_state(i):
    data = load(DEBTS, [])
    new_state = request.form.get("state", PENDING)
    if i < len(data):
        try:
            data[i] = ob.set_debt_state(data[i], new_state)
            save(DEBTS, data)
        except ValueError:
            pass
    return go_home()

@app.post("/debt/delete/<int:i>")
def debt_delete(i):
    data = load(DEBTS, [])
    if i < len(data): data.pop(i)
    save(DEBTS, data)
    return go_home()

@app.post("/onetime/add")
def onetime_add():
    amount = request.form.get("amount", "").strip()
    name = request.form.get("name", "").strip()
    due_date_raw = request.form.get("due_date", "").strip()
    if amount and name and due_date_raw:
        data = load(ONETIME, [])
        data.append({
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "amount": float(amount),
            "due_date": due_date_raw,
            "priority": request.form.get("priority", "mandatory"),
            "flexibility": "hard_due",
        })
        save(ONETIME, data)
    return go_home()

@app.post("/onetime/state/<int:i>")
def onetime_set_state(i):
    data = load(ONETIME, [])
    new_state = request.form.get("state", PENDING)
    if i < len(data) and new_state in SELECTABLE_STATES and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.set_payment_event(events, data[i]["id"], cycle_key, new_state)
        pe.save_payment_events(events)
    return go_home()

@app.post("/onetime/defer/<int:i>")
def onetime_defer(i):
    data = load(ONETIME, [])
    if i < len(data) and data[i].get("id"):
        today = date.today()
        cycle_key = pe.get_current_cycle_key(today)
        events = pe.load_payment_events()
        events = pe.defer_payment_event(events, data[i]["id"], cycle_key, today)
        pe.save_payment_events(events)
    return go_home()

@app.post("/onetime/delete/<int:i>")
def onetime_delete(i):
    data = load(ONETIME, [])
    if i < len(data): data.pop(i)
    save(ONETIME, data)
    return go_home()

@app.get("/receipt/image/<receipt_id>")
def receipt_image(receipt_id):
    # receipt_id is always our own uuid4().hex[:12] -- reject anything else
    # up front rather than letting a crafted id walk the receipts dir.
    if not re.fullmatch(r"[0-9a-f]{12}", receipt_id):
        abort(404)
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"):
        candidate = RECEIPTS_DIR / f"{receipt_id}{ext}"
        if candidate.exists():
            return send_file(candidate)
    abort(404)

@app.post("/receipt/upload")
def receipt_upload():
    file = request.files.get("image")
    if not file or not file.filename:
        return go_home()

    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    receipt_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix or ".jpg"
    image_path = RECEIPTS_DIR / f"{receipt_id}{ext}"
    file.save(image_path)

    result = receipts.parse_receipt(image_path)
    # Stashed server-side (not round-tripped through the URL) so the full
    # candidate list — arbitrarily many amounts with labels — survives the
    # redirect into the mandatory review form without a huge query string.
    review_path = RECEIPTS_DIR / f"{receipt_id}.review.json"
    save(review_path, {
        "amount": result.get("amount"),
        "date": result.get("date"),
        "merchant": result.get("merchant"),
        "candidates": result.get("amount_candidates", []),
        "image_path": str(image_path),
    })
    return redirect(f"/receipts?review_receipt={receipt_id}#receipt-review")

@app.post("/receipt/confirm")
def receipt_confirm():
    amount = request.form.get("amount", "").strip()
    if not amount:
        return go_home()
    # receipt_result only carries what the review form actually round-tripped
    # (merchant, image_path) — create_expense_from_receipt_result() only
    # ever uses `confirmed` for the values that matter (amount/date/name).
    receipt_result = {
        "merchant": request.form.get("merchant") or None,
        "image_path": request.form.get("image_path") or None,
    }
    confirmed = {
        "name": request.form.get("name", "Iné"),
        "amount": float(amount),
        "date": request.form.get("date", date.today().isoformat()),
    }
    receipt_id = request.form.get("receipt_id") or None
    expense = receipts.create_expense_from_receipt_result(
        receipt_result, confirmed, receipt_id=receipt_id
    )
    data = load(EXPENSES, [])
    data.append(expense)
    save(EXPENSES, data)
    log_audit("ocr_expense_saved", f"{confirmed['name']} {confirmed['amount']:.2f} €")

    if receipt_id:
        (RECEIPTS_DIR / f"{receipt_id}.review.json").unlink(missing_ok=True)
    return go_home()

SETUP_HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BudgetPilot — nastavenie</title>
<style>
:root{--bg:#0f172a;--card:#1f2937;--line:#374151;--text:#e5e7eb;--muted:#9ca3af;--blue:#2563eb;--red:#b91c1c;--green:#22c55e;--orange:#f59e0b}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#0f172a,#111827);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:18px}
.wrap{max-width:520px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.card{background:rgba(31,41,55,.95);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.25)}
h1{font-size:26px;margin:0 0 6px} h2{font-size:19px;margin:0 0 12px}
label{display:block;margin-top:8px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #4b5563;background:#0b1220;color:var(--text);margin-top:6px}
button{padding:10px 14px;border:0;border-radius:12px;background:var(--blue);color:white;font-weight:700;cursor:pointer}
.danger{background:var(--red)} .secondary{background:#4b5563}
.btn-row{display:flex;gap:8px;margin-top:10px}.btn-row button{flex:1}
.small{font-size:13px;color:var(--muted);line-height:1.35}
table{width:100%;border-collapse:collapse} th,td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:13px} th{color:var(--muted)}
.actions{display:flex;gap:6px;justify-content:flex-end}.actions form{margin:0}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;background:#374151}
.badge.ok{background:#14532d}
a{color:white;text-decoration:none}
</style>
</head>
<body>
<div class="wrap">

<div class="card">
<h1>Nastavenie</h1>
<div class="small">Toto vyplníš raz na začiatku a potom vždy, keď príde výplata.</div>
</div>

<div class="card">
<h2>Deň výplaty a reálny zostatok</h2>
<form method="post" action="/setup/balance">
<label>Deň výplaty v mesiaci</label>
<input name="payday_day" value="{{settings.get('payday_day','')}}" placeholder="napr. 15">
<label>Reálny zostatok na účte teraz</label>
<input name="real_balance" value="{{settings.get('real_balance', settings.get('account_balance', ''))}}" placeholder="napr. 850">
<label>Rezerva bokom (voliteľné)</label>
<input name="reserve_amount" value="{{settings.get('reserve_amount', settings.get('safe_min', 0))}}">
<div class="small">Tento zostatok je od teraz zdroj pravdy pre nový cyklus — prepíše predchádzajúce odhady.</div>
<div class="btn-row"><button>Uložiť</button></div>
</form>
</div>

<div class="card">
<h2>Pridať pravidelnú platbu</h2>
<form method="post" action="/setup/recurring">
<label>Názov</label><input name="name" placeholder="napr. škôlka">
<label>Suma</label><input name="amount" placeholder="napr. 120">
<label>Deň splatnosti v mesiaci</label><input name="due_day" placeholder="napr. 5">
<label>Priorita</label>
<select name="priority">
<option value="mandatory">nevyhnutná</option>
<option value="important">dôležitá</option>
<option value="flexible">flexibilná</option>
<option value="optional">voliteľná</option>
</select>
<label>Flexibilita</label>
<select name="flexibility">
<option value="hard_due">musí byť v termíne</option>
<option value="can_defer">dá sa posunúť</option>
<option value="optional">voliteľná</option>
</select>
<div class="btn-row"><button>Pridať platbu</button></div>
</form>
</div>

<div class="card">
<h2>Pravidelné platby</h2>
<table><tr><th>Názov</th><th>Suma</th><th>Deň</th><th>Stav</th><th></th></tr>
{% for x in recurring %}
<tr>
<td>{{x.get('name')}}</td><td>{{x.get('amount')}} €</td><td>{{x.get('due_day', x.get('day'))}}</td>
<td>{% if x.get('active', True) %}<span class="badge ok">aktívna</span>{% else %}<span class="badge">zrušená</span>{% endif %}</td>
<td class="actions">
{% if x.get('id') %}
<form method="post" action="/setup/recurring/toggle/{{x.get('id')}}"><button class="secondary">{% if x.get('active', True) %}Zrušiť{% else %}Obnoviť{% endif %}</button></form>
{% endif %}
</td>
</tr>
{% endfor %}
</table>
<div class="small">Pravidelné platby sa objavujú v prehľade každý mesiac automaticky, kým ich nezrušíš.</div>
</div>

<div class="card">
<a href="/"><button type="button" class="secondary">Späť na prehľad</button></a>
</div>

</div>
</body>
</html>
"""

@app.route("/setup")
def setup_page():
    settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})
    recurring = load(PAYMENTS, [])
    return render_template_string(SETUP_HTML, settings=settings, recurring=recurring)

@app.post("/setup/balance")
def setup_balance():
    settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})
    real_balance = float(request.form.get("real_balance", 0) or 0)
    reserve_amount = float(request.form.get("reserve_amount", 0) or 0)
    payday_raw = request.form.get("payday_day", "").strip()

    settings["real_balance"] = real_balance
    settings["reserve_amount"] = reserve_amount
    settings["account_balance"] = real_balance
    settings["safe_min"] = reserve_amount
    settings["use_reserve"] = reserve_amount > 0
    if payday_raw:
        settings["payday_day"] = int(payday_raw)
    save(SETTINGS, settings)

    snapshots = load(SNAPSHOTS, [])
    snapshots.append(ob.new_cycle_snapshot(real_balance, reserve_amount))
    save(SNAPSHOTS, snapshots)

    return redirect("/setup")

@app.post("/setup/recurring")
def setup_recurring_add():
    amount = request.form.get("amount", "").strip()
    name = request.form.get("name", "").strip()
    if amount and name:
        data = load(PAYMENTS, [])
        due_day = int(request.form.get("due_day", 1) or 1)
        today_iso = date.today().isoformat()
        data.append({
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "amount": float(amount),
            "day": due_day,
            "due_day": due_day,
            "frequency": "monthly",
            "start": today_iso,
            "start_month": today_iso[:7],
            "priority": request.form.get("priority", "mandatory"),
            "flexibility": request.form.get("flexibility", "hard_due"),
            "active": True,
            "paid": False,
        })
        save(PAYMENTS, data)
    return redirect("/setup")

@app.post("/setup/recurring/toggle/<item_id>")
def setup_recurring_toggle(item_id):
    data = load(PAYMENTS, [])
    for item in data:
        if item.get("id") == item_id:
            item["active"] = not item.get("active", True)
            break
    save(PAYMENTS, data)
    return redirect("/setup")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=False)
