#!/usr/bin/env python3
import hmac
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from datetime import date, datetime
from urllib.parse import urlparse
from flask import Flask, abort, jsonify, request, redirect, render_template, send_file, Response

import obligations as ob
import receipts
import payment_events as pe
import envelopes as env
import budgetpilot as bp
import audit_log
import balance_first_summary as bfs
from forecast import payment_state, PENDING, PAID_ME, PAID_OTHER, PAID_RESERVE, DEFERRED
from paths import app_base, data_dir

BASE = app_base()
DATA = data_dir()
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
ALLOWED_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_UPLOAD_BYTES = 16 * 1024 * 1024

AUDIT_ACTION_LABEL = {
    "balance_updated": "Stav účtu upravený",
    "payment_paid": "Platba označená ako zaplatená",
    "payment_deferred": "Platba odložená",
    "envelope_amount_changed": "Suma obálky upravená",
    "ocr_expense_saved": "Výdavok z účtenky uložený",
    "expense_added": "Výdavok pridaný",
    "full_reset": "Aplikácia vyčistená",
    "backup_restored": "Záloha obnovená",
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
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

def _auth_password():
    return os.environ.get("BUDGETPILOT_PASSWORD", "").strip()

def _auth_username():
    return os.environ.get("BUDGETPILOT_USER", "saldo").strip() or "saldo"

def _auth_enabled():
    return bool(_auth_password())

@app.before_request
def require_basic_auth():
    password = _auth_password()
    if not password:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.username or "", _auth_username()) and hmac.compare_digest(auth.password or "", password):
        return None
    return Response(
        "Vyžaduje sa prihlásenie.\n",
        401,
        {"WWW-Authenticate": 'Basic realm="Saldo", charset="UTF-8"'},
    )

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'",
    )
    return response

bfs.DATA = DATA
from balance_first_summary import register_balance_first_summary
register_balance_first_summary(app)

from envelope_editor import register_envelope_editor
register_envelope_editor(app)

from first_run_wizard import register_first_run_wizard
register_first_run_wizard(
    app,
    data_path=lambda: DATA,
    settings_path=lambda: SETTINGS,
    payments_path=lambda: PAYMENTS,
)

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
        save(path, default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()

def _payment_amount_and_label(payment_id):
    for path in (PAYMENTS, ONETIME):
        for item in load(path, []):
            if item.get("id") == payment_id:
                return float(item.get("amount", 0) or 0), (item.get("name") or payment_id)
    return 0.0, payment_id

def _shift_main_balance(delta):
    if not delta:
        return None
    settings = load(SETTINGS, {"account_balance": 0, "real_balance": 0})
    current = float(settings.get("account_balance", settings.get("real_balance", 0)) or 0)
    updated = round(current + delta, 2)
    settings["account_balance"] = updated
    settings["real_balance"] = updated
    settings["last_manual_review"] = datetime.now().isoformat(timespec="seconds")
    save(SETTINGS, settings)
    return updated

def _set_payment_state_event(payment_id, cycle_key, new_state, amount=None):
    """Set a cycle-scoped payment state and keep main-account balance in
    sync for web "paid from account" actions.

    The forecast treats paid_me as already reflected in the current bank
    balance. In the UI, users normally click "Zaplatené" at the moment
    they pay, so the app must subtract that payment from the stored manual
    balance once, and only once.
    """
    events = pe.load_payment_events()
    existing = pe.get_payment_event(events, payment_id, cycle_key)
    previous_state = existing.get("state", PENDING) if existing else PENDING
    adjusted_before = bool(existing and existing.get("main_balance_adjusted"))
    previous_delta = float(existing.get("main_balance_delta", 0) or 0) if existing else 0.0

    if amount is None:
        amount, _ = _payment_amount_and_label(payment_id)
    amount = float(amount or 0)

    balance_delta, should_mark_adjusted, stored_delta = _event_balance_delta(existing, new_state, amount)

    events = pe.set_payment_event(events, payment_id, cycle_key, new_state)
    event = pe.get_payment_event(events, payment_id, cycle_key)
    if event and should_mark_adjusted:
        event["main_balance_adjusted"] = True
        event["main_balance_delta"] = round(stored_delta, 2)

    _shift_main_balance(balance_delta)
    pe.save_payment_events(events)
    return balance_delta

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

def eur(value):
    return f"{float(value or 0):.2f} €"

def value_class(value):
    value = float(value or 0)
    if value < 0:
        return "bad"
    if value == 0:
        return "warn"
    return "ok"

def _event_balance_delta(existing, new_state, amount):
    previous_state = existing.get("state", PENDING) if existing else PENDING
    adjusted_before = bool(existing and existing.get("main_balance_adjusted"))
    previous_delta = float(existing.get("main_balance_delta", 0) or 0) if existing else 0.0

    if new_state == PAID_ME and not adjusted_before and amount > 0:
        return -amount, True, -amount
    if new_state != PAID_ME and previous_state == PAID_ME and adjusted_before:
        return (-previous_delta if previous_delta else amount), False, 0.0
    return 0.0, adjusted_before, previous_delta

def _event_holdback_category(state, event, cycle_key):
    if state == PAID_ME:
        return None if bool(event and event.get("main_balance_adjusted")) else "unsettled"
    if state == PENDING:
        return "unpaid" if cycle_key == pe.get_current_cycle_key(date.today()) else None
    if state == DEFERRED:
        deferred_to = str(event.get("deferred_to") if event else "" or "")
        if len(deferred_to) >= 7 and deferred_to[:7] <= pe.get_current_cycle_key(date.today()):
            return "unpaid"
    return None

def _cleanup_payment_events(payment_id):
    events = pe.load_payment_events()
    kept = [e for e in events if e.get("payment_id") != payment_id]
    if len(kept) != len(events):
        pe.save_payment_events(kept)

def _item_for_action_path(action_path, form):
    path = urlparse(action_path).path
    match = re.fullmatch(r"/(payment|onetime)/(state|delete)/(\d+)", path)
    if match:
        kind, action, raw_i = match.groups()
        data_path = PAYMENTS if kind == "payment" else ONETIME
        data = load(data_path, [])
        i = int(raw_i)
        if i >= len(data) or not data[i].get("id"):
            return None
        item = data[i]
        return {
            "kind": kind,
            "action": action,
            "payment_id": item.get("id"),
            "cycle_key": pe.get_current_cycle_key(date.today()),
            "state": form.get("state", PENDING),
            "amount": float(item.get("amount", 0) or 0),
            "label": item.get("name") or item.get("id"),
        }

    if path == "/payment/state/by-id":
        payment_id = form.get("payment_id", "").strip()
        if not payment_id:
            return None
        amount, label = _payment_amount_and_label(payment_id)
        return {
            "kind": "payment",
            "action": "state",
            "payment_id": payment_id,
            "cycle_key": form.get("cycle_key", "").strip() or pe.get_current_cycle_key(date.today()),
            "state": form.get("state", PENDING),
            "amount": amount,
            "label": label,
        }

    return None

def _payment_action_impact(action_path, form):
    target = _item_for_action_path(action_path, form)
    if not target or target["amount"] <= 0:
        return None

    before = bfs.build_balance_first_summary()
    amount = float(target["amount"])
    events = pe.load_payment_events()
    event = pe.get_payment_event(events, target["payment_id"], target["cycle_key"])
    current_state = event.get("state", PENDING) if event else PENDING
    before_category = _event_holdback_category(current_state, event, target["cycle_key"])

    balance_delta = 0.0
    after_category = None
    action_label = "Zmazať platbu" if target["action"] == "delete" else "Zmeniť stav platby"

    if target["action"] == "state":
        new_state = target["state"]
        if new_state not in SELECTABLE_STATES:
            return None
        balance_delta, adjusted_after, stored_delta = _event_balance_delta(event, new_state, amount)
        simulated_event = {"state": new_state}
        if adjusted_after:
            simulated_event["main_balance_adjusted"] = True
            simulated_event["main_balance_delta"] = stored_delta
        after_category = _event_holdback_category(new_state, simulated_event, target["cycle_key"])
        action_label = f"Nastaviť: {STATE_LABEL.get(new_state, new_state)}"

    before_holdback = amount if before_category in {"unpaid", "unsettled"} else 0.0
    after_holdback = amount if after_category in {"unpaid", "unsettled"} else 0.0

    after_balance = round(before["current_balance"] + balance_delta, 2)
    after_unpaid = round(
        before["unpaid_payments_total"]
        - (amount if before_category == "unpaid" else 0.0)
        + (amount if after_category == "unpaid" else 0.0),
        2,
    )
    after_unsettled = round(
        before.get("unsettled_paid_total", 0.0)
        - (amount if before_category == "unsettled" else 0.0)
        + (amount if after_category == "unsettled" else 0.0),
        2,
    )
    after_estimate = round(
        before["estimated_after_payments_and_envelopes"] + balance_delta + before_holdback - after_holdback,
        2,
    )

    return {
        "label": target["label"],
        "action_label": action_label,
        "before": {
            "current_balance": before["current_balance"],
            "unpaid_payments_total": before["unpaid_payments_total"],
            "unsettled_paid_total": before.get("unsettled_paid_total", 0.0),
            "estimated_after_payments_and_envelopes": before["estimated_after_payments_and_envelopes"],
        },
        "after": {
            "current_balance": after_balance,
            "unpaid_payments_total": after_unpaid,
            "unsettled_paid_total": after_unsettled,
            "estimated_after_payments_and_envelopes": after_estimate,
        },
    }

def _impact_message(impact):
    before = impact["before"]
    after = impact["after"]
    return "\n".join([
        f"{impact['action_label']}: {impact['label']}",
        "",
        f"Stav účtu: {eur(before['current_balance'])} -> {eur(after['current_balance'])}",
        f"Ešte treba zaplatiť: {eur(before['unpaid_payments_total'])} -> {eur(after['unpaid_payments_total'])}",
        f"Zaplatené mimo zostatku: {eur(before['unsettled_paid_total'])} -> {eur(after['unsettled_paid_total'])}",
        f"Reálne k dispozícii: {eur(before['estimated_after_payments_and_envelopes'])} -> {eur(after['estimated_after_payments_and_envelopes'])}",
        "",
        "Pokračovať?",
    ])

def _debug_balance_context():
    summary = bfs.build_balance_first_summary()
    payments = load(PAYMENTS, [])
    onetime = load(ONETIME, [])
    settings = load(SETTINGS, {})
    events = pe.load_payment_events()
    known_ids = {
        item.get("id")
        for item in payments + onetime
        if isinstance(item, dict) and item.get("id")
    }
    orphan_events = [
        e for e in events
        if isinstance(e, dict) and e.get("payment_id") not in known_ids
    ]
    invalid_payments = [
        item for item in payments + onetime
        if isinstance(item, dict) and float(item.get("amount", 0) or 0) <= 0
    ]
    return {
        "summary": summary,
        "settings": settings,
        "payments": payments,
        "onetime": onetime,
        "events": events,
        "orphan_events": orphan_events,
        "invalid_payments": invalid_payments,
    }

def _build_problem_reports(ctx):
    summary = ctx["summary"]
    problems = []

    def add(severity, title, problem, impact, suggestion, action_href=None, action_label=None, details=None):
        problems.append({
            "severity": severity,
            "title": title,
            "problem": problem,
            "impact": impact,
            "suggestion": suggestion,
            "action_href": action_href,
            "action_label": action_label,
            "details": details or [],
        })

    if summary.get("missing_after_everything", 0) > 0:
        add(
            "critical",
            "Reálny odhad je v mínuse",
            f"Po otvorených platbách a obálkach chýba {eur(summary['missing_after_everything'])}.",
            "Ak nič nezmeníš, plán v aktuálnom cykle nevychádza.",
            "Najprv vyrieš platby po splatnosti alebo čoskoro splatné. Potom skontroluj obálky a aktuálny stav účtu.",
            "/payments",
            "Otvoriť platby",
        )

    overdue_items = [p for p in summary.get("unpaid_payment_items", []) if p.get("overdue")]
    if overdue_items:
        add(
            "critical",
            "Platby po splatnosti",
            f"{len(overdue_items)} platba/platby majú termín v minulosti.",
            "Tieto položky môžu skresľovať dostupné peniaze a vyžadujú rozhodnutie.",
            "Označ ich ako zaplatené, ak už odišli z účtu, alebo ich odlož na konkrétny dátum.",
            "/payments#payment-inbox",
            "Riešiť v inboxe",
            [f"{p.get('name')} · {eur(p.get('amount'))} · {p.get('due_date')}" for p in overdue_items[:5]],
        )

    unsettled = summary.get("unsettled_paid_items", [])
    if unsettled:
        add(
            "warning",
            "Zaplatené mimo zostatku",
            f"{len(unsettled)} zaplatená platba ešte nie je premietnutá v uloženom stave účtu.",
            f"Pre istotu sa v odhade drží bokom {eur(summary.get('unsettled_paid_total'))}.",
            "Ak platba odišla z hlavného účtu, zúčtuj ju v platbách alebo uprav aktuálny stav účtu podľa banky.",
            "/payments#zaplatene",
            "Skontrolovať zaplatené",
            [f"{p.get('name')} · {eur(p.get('amount'))}" for p in unsettled[:5]],
        )

    over_envelopes = [e for e in summary.get("envelope_items", []) if float(e.get("over", 0) or 0) > 0]
    if over_envelopes:
        add(
            "warning",
            "Prekročené obálky",
            f"{len(over_envelopes)} obálka/obálky sú nad limitom.",
            f"Prekročenie spolu: {eur(summary.get('envelopes_over_total'))}.",
            "Navýš limit obálky, presuň výdavok do správnej kategórie alebo zníž plán na zvyšok mesiaca.",
            "/envelopes",
            "Otvoriť obálky",
            [f"{e.get('name')} · prekročené o {eur(e.get('over'))}" for e in over_envelopes[:5]],
        )

    if ctx.get("orphan_events"):
        add(
            "warning",
            "Stavy bez existujúcej platby",
            f"{len(ctx['orphan_events'])} payment event odkazuje na platbu, ktorá už neexistuje.",
            "Historický stav môže miasť diagnostiku a budúce výpočty.",
            "Ak nejde o zámer, vyčisti staré záznamy v payment_events.json alebo obnov chýbajúcu platbu zo zálohy.",
            "/debug/balance",
            "Otvoriť diagnostiku",
            [str(e.get("payment_id")) for e in ctx["orphan_events"][:8]],
        )

    if ctx.get("invalid_payments"):
        add(
            "warning",
            "Platby s neplatnou sumou",
            f"{len(ctx['invalid_payments'])} platba má nulovú alebo zápornú sumu.",
            "Takáto položka sa nezapočíta do odhadu, aj keď môže vyzerať ako aktívna platba.",
            "Uprav sumu alebo položku zmaž v správe platieb.",
            "/payments",
            "Upraviť platby",
            [f"{p.get('name') or p.get('id')} · {p.get('amount')}" for p in ctx["invalid_payments"][:8]],
        )

    if not summary.get("last_manual_review") and float(summary.get("current_balance", 0) or 0) == 0:
        add(
            "info",
            "Chýba ručná kontrola účtu",
            "Stav účtu je 0 € a aplikácia nemá uloženú poslednú manuálnu kontrolu.",
            "Reálny odhad nemusí sedieť s bankou.",
            "Zadaj aktuálny stav účtu podľa banky.",
            "/#balance-update-field",
            "Upraviť stav účtu",
        )

    if not problems:
        add(
            "ok",
            "Nenašiel som žiadny konkrétny problém",
            "Dáta neobsahujú po splatnosti, záporný odhad, orphan eventy ani neplatné sumy.",
            "Stále sa oplatí porovnať stav účtu s bankou.",
            "Pokračuj v bežnej kontrole platieb a výdavkov.",
            "/",
            "Späť na prehľad",
        )

    severity_order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    return sorted(problems, key=lambda p: severity_order.get(p["severity"], 9))

BACKUP_NAME_RE = re.compile(r"^\d{8}-\d{6}-(full-reset|pre-restore)(-[a-f0-9]{6})?$")

def _backup_root():
    return BASE / "backups"

def _dir_size(path):
    total = 0
    if not path.exists():
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total

def _format_bytes(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"

def _create_data_backup(reason):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = _backup_root() / f"{ts}-{reason}"
    if backup_dir.exists():
        backup_dir = backup_dir.with_name(f"{backup_dir.name}-{uuid.uuid4().hex[:6]}")
    shutil.copytree(DATA, backup_dir / "data")
    return backup_dir

def _list_backups(limit=6):
    root = _backup_root()
    if not root.exists():
        return []
    rows = []
    for item in root.iterdir():
        if not item.is_dir() or not BACKUP_NAME_RE.fullmatch(item.name):
            continue
        data_path = item / "data"
        if not data_path.is_dir():
            continue
        try:
            created = datetime.strptime(item.name[:15], "%Y%m%d-%H%M%S")
            created_label = created.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            created_label = item.name[:15]
        rows.append({
            "name": item.name,
            "kind": "Pred obnovou" if "pre-restore" in item.name else "Pred resetom",
            "created": created_label,
            "size": _format_bytes(_dir_size(data_path)),
        })
    rows.sort(key=lambda b: b["name"], reverse=True)
    return rows[:limit]

def _resolve_backup_dir(name):
    name = (name or "").strip()
    if not BACKUP_NAME_RE.fullmatch(name):
        return None
    root = _backup_root().resolve()
    candidate = (_backup_root() / name).resolve()
    if candidate.parent != root:
        return None
    if not (candidate / "data").is_dir():
        return None
    return candidate

def _restore_backup(name):
    backup_dir = _resolve_backup_dir(name)
    if not backup_dir:
        return None
    pre_restore = _create_data_backup("pre-restore")
    tmp_restore = DATA.with_name(f".{DATA.name}.restore.{uuid.uuid4().hex}")
    shutil.copytree(backup_dir / "data", tmp_restore)
    if DATA.exists():
        shutil.rmtree(DATA)
    tmp_restore.replace(DATA)
    return backup_dir, pre_restore

def _build_system_status(problem_reports, backups, setup_needed, settings):
    rows = []

    active_problem_count = len([p for p in problem_reports if p.get("severity") != "ok"])
    rows.append({
        "state": "ok" if active_problem_count == 0 else "warn",
        "label": "Diagnostika dát",
        "detail": "Bez aktívnych problémov." if active_problem_count == 0 else f"{active_problem_count} vecí vyžaduje kontrolu.",
        "action_href": "/problems",
        "action_label": "Otvoriť",
    })

    last_review = settings.get("last_manual_review")
    rows.append({
        "state": "ok" if last_review else "warn",
        "label": "Stav účtu",
        "detail": f"Posledná kontrola: {last_review[:16].replace('T', ' ')}" if last_review else "Zadaj stav účtu podľa banky.",
        "action_href": "/#balance-update-field",
        "action_label": "Upraviť",
    })

    rows.append({
        "state": "ok" if backups else "warn",
        "label": "Záloha",
        "detail": f"Posledná záloha: {backups[0]['created']}" if backups else "Zatiaľ nie je dostupná žiadna záloha.",
        "action_href": "#backups",
        "action_label": "Zobraziť",
    })

    rows.append({
        "state": "warn" if setup_needed else "ok",
        "label": "Prvé nastavenie",
        "detail": "Chýba základné nastavenie." if setup_needed else "Základné dáta sú pripravené.",
        "action_href": "/setup" if setup_needed else "/manage",
        "action_label": "Dokončiť" if setup_needed else "OK",
    })

    rows.append({
        "state": "ok" if _auth_enabled() else "warn",
        "label": "Prístup",
        "detail": "Web UI je chránené heslom." if _auth_enabled() else "Heslo nie je nastavené. Kto sa dostane na port 8765, vidí dáta.",
        "action_href": "/manage#system-status",
        "action_label": "Skontrolované" if _auth_enabled() else "Nastaviť env",
    })

    state_order = {"bad": 0, "warn": 1, "ok": 2}
    overall = min((r["state"] for r in rows), key=lambda s: state_order.get(s, 9))
    return {
        "overall": overall,
        "overall_label": {
            "ok": "Stabilné",
            "warn": "Vyžaduje kontrolu",
            "bad": "Problém",
        }.get(overall, "Neznáme"),
        "rows": rows,
    }

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

APP_TEMPLATE = "app.html"

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
    view_meta = {
        "dashboard": (
            "Prehľad",
            "Reálny zostatok, otvorené platby, obálky a posledná aktivita na jednom mieste.",
        ),
        "payments": (
            "Platby",
            "Pracovný zoznam povinností: zaplatiť, odložiť, upraviť alebo zmeniť stav.",
        ),
        "deferred": (
            "Odložené",
            "Platby s novým termínom, rozdelené podľa toho, kedy sa majú vrátiť do pozornosti.",
        ),
        "envelopes": (
            "Obálky",
            "Mesačné limity a priebeh míňania podľa kategórií.",
        ),
        "expenses": (
            "Výdavky",
            "Rýchle ručné výdavky a ich história za aktuálne dáta.",
        ),
        "receipts": (
            "OCR bloček",
            "Nahraj účtenku, skontroluj rozpoznanú sumu a ulož ju ako výdavok.",
        ),
        "history": (
            "História",
            "Časová os zmien v zostatku, platbách, výdavkoch a obálkach.",
        ),
        "manage": (
            "Správa",
            "Nastavenia, platobné šablóny, dlhy, história a diagnostika na jednom mieste.",
        ),
        "settings": (
            "Nastavenia",
            "Účet, rezerva, príjem a diagnostika dát aplikácie.",
        ),
    }
    view_title, view_subtitle = view_meta.get(active_view, view_meta["dashboard"])
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
    balance_summary = bfs.build_balance_first_summary()
    final_available = balance_summary["estimated_after_payments_and_envelopes"]
    summary = {
        "balance": eur(balance_summary["current_balance"]),
        "unpaid_total": eur(balance_summary["unpaid_payments_total"]),
        "shortfall": eur(balance_summary["missing_after_everything"]) if balance_summary["missing_after_everything"] else "-",
        "safe_to_spend": eur(final_available),
        "daily_safe_to_spend": dash["day"],
        "projected_after_payday": dash["projected_after_payday"],
        "next_payday": dash["next_payday"] if dash["next_payday"] != "-" else (
            f"deň {settings.get('payday_day')}" if settings.get("payday_day") else "-"
        ),
    }
    dash["status_class"] = value_class(final_available)

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

    problem_reports = _build_problem_reports(_debug_balance_context())
    backups = _list_backups()
    system_status = _build_system_status(problem_reports, backups, setup_needed, settings)

    return render_template(
        APP_TEMPLATE,
        active_view=active_view,
        view_title=view_title, view_subtitle=view_subtitle,
        balance_summary=balance_summary, eur=eur,
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
        system_status=system_status,
        problem_reports=problem_reports,
        backups=backups,
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
    return render_page(active_view="manage")

@app.route("/manage")
def manage_view():
    return render_page(active_view="manage")

@app.route("/settings", methods=["GET"])
def settings_view():
    return render_page(active_view="manage")

@app.route("/receipts")
def receipts_view():
    return render_page(active_view="receipts")

@app.route("/edit/income/<int:i>")
def edit_income(i):
    return render_page(edit_income=i, active_view="manage")

@app.route("/edit/payment/<int:i>")
def edit_payment(i):
    return render_page(edit_payment=i, active_view="manage")

@app.route("/edit/expense/<int:i>")
def edit_expense(i):
    return render_page(edit_expense=i, active_view="expenses")

@app.get("/debug/balance")
def debug_balance_view():
    ctx = _debug_balance_context()
    return render_template(
        "debug_balance.html",
        s=ctx["summary"],
        orphan_events=ctx["orphan_events"],
        invalid_payments=ctx["invalid_payments"],
        orphan_events_json=json.dumps(ctx["orphan_events"], indent=2, ensure_ascii=False),
        invalid_payments_json=json.dumps(ctx["invalid_payments"], indent=2, ensure_ascii=False),
        eur=eur,
    )

@app.get("/problems")
def problems_view():
    ctx = _debug_balance_context()
    return render_template(
        "problems.html",
        problems=_build_problem_reports(ctx),
        summary=ctx["summary"],
        eur=eur,
    )

@app.post("/api/payment-action-impact")
def api_payment_action_impact():
    impact = _payment_action_impact(request.form.get("action_path", ""), request.form)
    if not impact:
        return jsonify({"ok": False})
    return jsonify({"ok": True, "impact": impact, "message": _impact_message(impact)})

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

    backup_dir = _create_data_backup("full-reset")

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

@app.post("/settings/restore")
def settings_restore():
    code = (request.form.get("confirm_code") or "").strip().upper()
    backup_name = (request.form.get("backup_name") or "").strip()
    if code != RESET_CONFIRM_CODE:
        return redirect("/manage?restore_error=code#backups")

    restored = _restore_backup(backup_name)
    if not restored:
        return redirect("/manage?restore_error=backup#backups")

    backup_dir, pre_restore = restored
    log_audit("backup_restored", f"restored: {backup_dir.name}; previous: {pre_restore.name}")
    return redirect(f"/manage?restored={backup_dir.name}#backups")

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
        _set_payment_state_event(data[i]["id"], cycle_key, new_state, data[i].get("amount", 0))
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
        amount, label = _payment_amount_and_label(payment_id)
        _set_payment_state_event(payment_id, cycle_key, new_state, amount)
        if new_state == PAID_ME:
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
    if i < len(data):
        payment_id = data[i].get("id")
        data.pop(i)
        if payment_id:
            _cleanup_payment_events(payment_id)
    save(PAYMENTS, data)
    return go_home()

def _parse_expense_date(raw):
    """Normalize a user-supplied date string to a zero-padded ISO-8601 date.

    Falls back to today's date if the input can't be parsed, since a single-digit
    day/month (e.g. "2026-07-7") would otherwise be stored as-is and later crash
    date.fromisoformat() in calc_month().
    """
    raw = (raw or "").strip()
    try:
        year, month, day = raw.split("-")
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return date.today().isoformat()

@app.post("/expense/add")
def expense_add():
    amount = request.form.get("amount","").strip()
    if amount:
        name = request.form.get("name","Výdavok")
        merchant = request.form.get("merchant", "").strip()
        item = {
            "name": name,
            "amount": float(amount),
            "date": _parse_expense_date(request.form.get("date")),
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
            "date": _parse_expense_date(request.form.get("date")),
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
        _set_payment_state_event(data[i]["id"], cycle_key, new_state, data[i].get("amount", 0))
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
    if i < len(data):
        payment_id = data[i].get("id")
        data.pop(i)
        if payment_id:
            _cleanup_payment_events(payment_id)
    save(ONETIME, data)
    return go_home()

@app.get("/receipt/image/<receipt_id>")
def receipt_image(receipt_id):
    # receipt_id is always our own uuid4().hex[:12] -- reject anything else
    # up front rather than letting a crafted id walk the receipts dir.
    if not re.fullmatch(r"[0-9a-f]{12}", receipt_id):
        abort(404)
    for ext in sorted(ALLOWED_RECEIPT_EXTENSIONS):
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
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_RECEIPT_EXTENSIONS:
        abort(400)
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

SETUP_TEMPLATE = "setup.html"

@app.route("/setup")
def setup_page():
    settings = load(SETTINGS, {"account_balance": 0, "use_reserve": False, "safe_min": 0})
    recurring = load(PAYMENTS, [])
    return render_template(SETUP_TEMPLATE, settings=settings, recurring=recurring)

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
