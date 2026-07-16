# BudgetPilot Public Release Audit

Date: 2026-07-16

## 1. Executive Summary

BudgetPilot is close to being publishable as a public source repository, but a
running instance must not be presented as generally safe for public internet
exposure. The supported deployment classification for the first public release
is: **safe behind localhost, a trusted LAN, or a private VPN/Tailscale; not
currently safe to expose directly to the public internet**.

Major release-readiness work completed in this pass:

- added first-run single local administrator setup with hashed passwords;
- protected financial pages, APIs, and write actions behind login or Basic
  Auth compatibility credentials;
- kept CSRF protection on state-changing requests;
- added logout and basic IP-based login throttling;
- added Dockerfile, Docker Compose, `.dockerignore`, `.env.example`,
  `.editorconfig`, and `.gitattributes`;
- moved Docker runtime state to `/var/lib/budgetpilot` in a persistent named
  volume and runs Gunicorn as a non-root user;
- fixed multi-worker first-start session-secret creation so Docker/Gunicorn
  workers share one persisted Flask secret immediately;
- documented deployment limits, Docker, native Linux paths, reverse proxy
  settings, localization status, and security posture;
- verified tests, native isolated startup, restart persistence, backup/restore,
  and Docker build/start on this host.

Public GitHub source publication is separate from safe production exposure.
The source can be prepared for publication after the manual items below, but a
live BudgetPilot instance should remain private-network only.

## 2. Current Architecture

Active entry points:

- `budgetpilot_web.py` - Flask web app and route registration.
- `budgetpilot.py` - CLI forecast entry point.
- `forecast.py`, `obligations.py`, `payment_events.py`,
  `balance_first_summary.py` - core financial logic.
- `json_store.py` and `paths.py` - JSON persistence, atomic writes, runtime
  paths, and production-data guard.

Runtime data lives under `BUDGETPILOT_HOME/data` or, if unset, the historical
default `~/BudgetPilot/data`. Backups live under `BUDGETPILOT_HOME/backups`.
Docker sets `BUDGETPILOT_HOME=/var/lib/budgetpilot`.

The web UI uses templates in `templates/`, with small inline auth/setup
templates. The data store is flat JSON, not SQLite or a server database.

## 3. Repository Inventory

Active production code:

- `budgetpilot_web.py`, `budgetpilot.py`
- `forecast.py`, `obligations.py`, `payment_events.py`
- `balance_first_summary.py`, `envelopes.py`, `envelope_editor.py`
- `first_run_wizard.py`, `receipts.py`, `audit_log.py`
- `json_store.py`, `paths.py`
- `templates/*.html`

Required configuration and deployment:

- `requirements.txt`
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- `.env.example`
- `deploy/budgetpilot.service`, `deploy/README.md`
- `.github/workflows/tests.yml`

Documentation:

- `README.md`, `LICENSE`, `CHANGELOG.md`
- `docs/*.md`
- root `CONTRIBUTING.md`, `SECURITY.md`

Tests:

- `tests/*.py`
- `tests/fixtures/demo_data/*.json`

Maintenance scripts:

- `scripts/load_demo_data.py`

Generated/ignored local files:

- `__pycache__/`, `.venv/`, `tests/__pycache__/`, `scripts/__pycache__/`

User data:

- `data/*.json`, `data/.session_secret_key`, `data/receipts/`
- `backups/`

Candidates for later archival, not deleted in this pass:

- older backup trees under ignored `backups/`

## 4. Confirmed Working Features

Verified by tests or smoke checks:

- local admin setup, hashed password storage, login, logout;
- protected pages and protected API redirects;
- CSRF rejection for missing/forged tokens;
- recurring and one-time payment calculations;
- paid, paid-other, paid-reserve, pending, and deferred payment states;
- deferred carryover promotion when target date arrives;
- envelope remaining-budget calculation without double-counting spent money;
- receipt upload path validation and OCR review boundary;
- reset creates a backup before wiping;
- restore can bring data back after reset;
- synthetic data persists across process restart.

## 5. Tests Performed

- `python3 -m unittest discover -s tests` - 357 tests passed.
- Localization/browser phase:
  - `python3 -m unittest tests.test_localization` - localization coverage
    tests passed;
  - `npm run test:e2e` - Chromium end-to-end suite passed;
  - `npm run review:chromium` - desktop/laptop/tablet/mobile/narrow-mobile
    visual, console, network, and overflow review passed;
  - `npm run screenshots:public` - regenerated sanitized screenshots from
    synthetic data under `docs/assets/screenshots/`.
- `python3 -m py_compile ...` - main modules compiled.
- Native smoke test on isolated `BUDGETPILOT_HOME`:
  - started on `127.0.0.1:18765`;
  - created admin;
  - completed financial setup with synthetic data;
  - restarted server;
  - verified unauthenticated redirect, login, and persisted payment;
  - verified reset backup and restore.
- Docker Compose smoke on this host:
  - `docker compose -p budgetpilot-smoke config`;
  - `docker compose -p budgetpilot-smoke build`;
  - `BUDGETPILOT_HOST_PORT=18766 docker compose -p budgetpilot-smoke up -d`;
  - confirmed first-launch setup route;
  - created first admin and completed financial setup through Chromium;
  - restarted the container and verified login/dashboard data persisted;
  - confirmed container runs as non-root `budgetpilot`;
  - confirmed `users.json` stored under `/var/lib/budgetpilot/data`;
  - cleaned stack with `down --volumes`.

Known test-log noise: invalid synthetic `every_months` and corrupt JSON fixture
warnings are intentionally emitted by regression tests and are non-failing.

## 6. Bugs Found

- Public-facing app name was inconsistent (`Saldo` vs. BudgetPilot).
- No first-run local administrator account existed before this pass.
- The first-run financial setup gate could intercept auth routes and restore
  after reset.
- `.env.example` was ignored by `.gitignore`.
- Docker build context lacked `.dockerignore`.
- Docker runtime data/backups were not persistently grouped before the Docker
  changes.
- Compose used a fixed `container_name`, which can conflict.
- Multi-worker Gunicorn on a fresh runtime could create divergent in-memory
  Flask session secrets before `data/.session_secret_key` existed, causing
  first-run CSRF/session failures.
- Deployment docs still described older Basic Auth / unauthenticated behavior.
- Some docs described the old template architecture.

## 7. Fixes Implemented

- Added local admin account setup, login/logout, hashed password storage in
  `data/users.json`, route protection, and login throttling.
- Kept Basic Auth as compatibility mode via `BUDGETPILOT_PASSWORD`.
- Added configurable host/port, secure-cookie and proxy-related env settings.
- Added Docker/Gunicorn deployment files and native systemd example.
- Made `data/.session_secret_key` creation atomic and covered it with a
  concurrent regression test.
- Updated documentation and public release checklist.
- Added auth tests and adjusted existing tests for authenticated routes.

## 8. UI and Visual Findings

The UI is functional and mobile-aware, with sidebar/bottom navigation,
responsive table/card behavior, visible financial statuses, and a language
switcher. Chromium review was completed with Playwright using synthetic data.
Checked viewport sizes: 1440x900, 1280x720, 768x1024, 1024x768, 390x844,
844x390, and 320x700.

Defects fixed during Chromium review:

- auth page CSS was not injected into inline templates;
- `/manage` screen actions overflowed at tablet portrait width;
- several summary/action links and details summaries had too-small hit areas;
- the mobile drawer screenshot could be captured before its transition ended;
- English forecast statuses still showed Slovak `POZOR`.

The final automated visual review found no JavaScript console errors, failed
requests, HTTP 4xx/5xx responses, or horizontal overflow.

Financial warnings use text and labels, not only color. Dangerous reset/restore
actions require confirmation text and CSRF.

## 9. Localization Status

The web UI now supports Slovak and English. Slovak is the source/fallback
language. English translations live in `translations/en.json`; Slovak source
keys live in `translations/sk.json`; fallback and language persistence live in
`i18n.py`. The language switcher is visible on auth, first-run setup, and the
main application shell.

`tests/test_localization.py` verifies catalog parity, fallback behavior,
language cookie persistence, and rendered Slovak/English pages. Remaining
known limit: euro/date formatting is not locale-specific beyond translated
labels.

## 10. Security and Privacy Findings

Positive findings:

- first-run local admin, no universal default password;
- password hashes stored with Werkzeug hashing;
- CSRF protection for state-changing routes;
- HttpOnly and SameSite session cookie settings;
- production-aware `SESSION_COOKIE_SECURE` via env/public URL;
- optional `ProxyFix` only when explicitly enabled;
- security headers set on responses;
- receipt IDs validated before filesystem access;
- runtime financial data and backups ignored by Git;
- `.dockerignore` prevents local data/backups/secrets from entering Docker
  build context.

Remaining security limits:

- not safe for direct public-internet exposure;
- login throttling is keyed by the observed client IP, so shared NAT and
  reverse proxies affect how attempts are grouped;
- no HTTPS termination inside the app;
- no multi-user authorization model;
- no password reset flow by design;
- no dependency audit tool was available in the verified command set.

## 11. `.gitignore` Findings

Improved to ignore runtime JSON, receipts, session secret, backups, caches,
coverage, build output, logs, test reports, and editor files. Added
`!.env.example` so safe config docs can be tracked.

Tracked sensitive runtime files found: none except `data/.gitkeep`. Ignored
local runtime data and backups are present in the working tree and must not be
force-added.

## 12. License Findings

The repository contains a complete Apache License 2.0 with `Copyright 2026
Stanislav Hambalko`.

Apache-2.0 is appropriate for BudgetPilot's public release goals: it is a
standard OSI-approved permissive license, allows use/modification/
redistribution including commercial use, includes an express patent grant,
and keeps the usual notice and no-warranty terms. No custom legal text was
introduced.

No third-party image/font assets were identified. Dependencies are Python
packages (`Flask`, `Gunicorn`, `pytesseract`, `Pillow`) with standard open
source licensing; no NOTICE file appears required from current usage.

The README and package metadata reference `Apache-2.0` consistently.

## 13. Documentation Findings

Updated:

- README deployment/auth language;
- Docker documentation;
- native Linux installation and systemd guidance;
- security policy;
- localization status;
- release checklist;
- architecture notes.

Still useful after public release:

- add a short Slovak user-facing README section or separate Slovak user guide
  if the repository starts attracting non-English contributors.

Sanitized screenshot assets now exist under `docs/assets/screenshots/` and are
generated from synthetic data by `npm run screenshots:public`.

## 14. Docker and Portability Findings

Docker:

- `python:3.11-slim` base supports multiple architectures.
- Built successfully on Debian 12/Armbian ARM64.
- Runs as non-root user.
- Uses Gunicorn.
- Uses named volume at `/var/lib/budgetpilot`.
- Health check configured.
- Host bind defaults to `127.0.0.1`; host port configurable with
  `BUDGETPILOT_HOST_PORT`.

Native:

- Verified on this host: Debian 12 userspace on ARM64 (`aarch64`).
- Python 3.11.2 used.
- Native install is expected to work on Debian/Ubuntu-like distributions with
  Python 3.10+ and dependencies from `requirements.txt`.
- Fedora/Arch native installs were not tested; expected to work by dependency
  review, with distro-specific package names only needed for optional
  Tesseract OCR.

Compatibility matrix:

| Platform | Architecture | Docker | Native | Status | Evidence |
|---|---:|---|---|---|---|
| Debian 12 / Armbian Bookworm | ARM64 | tested | tested | tested | Unit tests, native smoke, Docker build/run on this host |
| Debian 12 | x86_64 | verified by dependency review | expected to work | not tested | Python/Gunicorn/Flask pure Python; Pillow has manylinux x86_64 wheels |
| Ubuntu 22.04+ | x86_64 | expected to work | expected to work | not tested | Same Python stack; docs use portable venv/Docker paths |
| Ubuntu/Debian | ARM64 | tested on Debian 12 ARM64 | tested on Debian 12 ARM64 | tested for Debian, expected for Ubuntu | Docker build pulled ARM64 wheels; native tests passed |
| Fedora | x86_64 | expected to work | expected to work | not tested | Docker is distro-neutral; native Python deps expected |
| Arch-based Linux | x86_64 | expected to work | expected to work | not tested | Docker is distro-neutral; native rolling Python deps likely compatible |
| Windows/macOS | x86_64/ARM64 | unsupported by this audit | unsupported by this audit | not tested | No validation performed |

## 15. Public Release Blockers

No code or documentation blockers remain in the repository after the current
verification pass.

Manual repository-hosting steps still remain outside the working tree:

- review the final diff and commit it;
- create the `v0.1.0` Git tag/release;
- set GitHub About description/topics from the suggestions below;
- confirm the GitHub Actions workflow passes after push.

Do not claim public-internet deployment support. BudgetPilot remains a
localhost, trusted-LAN, or private-VPN application.

## 16. Non-Blocking Recommendations

- Add a small dependency-audit workflow if desired (`pip-audit` or similar).
- Add a tagged Docker image workflow after repository publication.
- Add optional encrypted backups later.

## 17. Suggested GitHub Description

Short description:

> Privacy-focused, self-hosted personal and household budgeting app for upcoming payments, available balance, risk, and deferrable expenses.

Longer About text:

> BudgetPilot is a local-first personal and household budgeting application that helps users understand what must still be paid, what can be postponed, how much money remains, and whether the current month is financially safe.

## 18. Suggested GitHub Topics

`personal-finance`, `budgeting`, `household-budget`, `self-hosted`,
`privacy`, `flask`, `python`, `docker`, `finance-dashboard`, `slovak`,
`multilingual`

The bilingual UI has landed, so `multilingual` is appropriate.

## 19. Proposed First Release Version

`v0.1.0` - Initial public MVP.

Release title: `BudgetPilot v0.1.0 - Local-first household cashflow MVP`

## 20. Release Checklist

- [x] Confirm license holder.
- [ ] Run `python3 -m unittest discover -s tests`.
- [ ] Run Docker Compose smoke check.
- [ ] Inspect `git status --ignored` for accidental data/backups.
- [ ] Capture sanitized screenshots only.
- [x] Verify README does not promise public exposure support.
- [ ] Create a GitHub release from a clean commit; do not push real `data/`.

## 21. Commands Used for Verification

Key commands:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile budgetpilot.py budgetpilot_web.py first_run_wizard.py forecast.py obligations.py json_store.py paths.py payment_events.py receipts.py envelope_editor.py balance_first_summary.py audit_log.py
docker compose -p budgetpilot-smoke config
docker compose -p budgetpilot-smoke build
BUDGETPILOT_HOST_PORT=18766 docker compose -p budgetpilot-smoke up -d
BUDGETPILOT_HOST_PORT=18766 docker compose -p budgetpilot-smoke down --volumes --remove-orphans
```

Native smoke used `BUDGETPILOT_HOME=/tmp/budgetpilot-smoke-*`,
`BUDGETPILOT_HOST=127.0.0.1`, and `BUDGETPILOT_PORT=18765`.

## 22. Files Changed

Created:

- `.dockerignore`, `.editorconfig`, `.gitattributes`, `.env.example`
- `Dockerfile`, `docker-compose.yml`
- root `CONTRIBUTING.md`, `SECURITY.md`
- `docs/DOCKER.md`, `docs/LOCALIZATION.md`, this audit document
- `tests/test_auth.py`

Modified:

- auth/security/runtime config in `budgetpilot_web.py`
- first-run route gating in `first_run_wizard.py`
- app shell logout and product naming in templates
- Docker/native/security/localization docs
- `.gitignore`, `requirements.txt`, deployment service/docs
- tests for authenticated route behavior

Pre-existing uncommitted changes were already present before this pass and
were preserved rather than reverted.

## 23. Unresolved Risks

- Fedora, Arch, Ubuntu, and x86_64 were not directly tested.
- OCR depends on optional system Tesseract packages and was not validated in
  Docker.
- Runtime JSON is simple and local-first, but there is no migration framework.
- Authentication is single-admin, not multi-user authorization.
