# Release Checklist

Use this before pushing BudgetPilot to a public remote or making a release.

## Must Pass

```bash
git status --short
python3 -m unittest discover -s tests
python3 -m py_compile budgetpilot.py budgetpilot_web.py first_run_wizard.py
npm run test:e2e
npm run review:chromium
```

- `git status --short` should be clean, except for changes you intend to
  commit.
- Tests should pass without skipped demo-data assumptions.
- Chromium E2E and visual review should pass on synthetic data.
- Runtime data should not be staged or committed.
- After pushing to GitHub, the `Tests` GitHub Actions workflow should pass.

## Data Privacy

Confirm live household data is ignored:

```bash
git status --ignored --short data backups
git ls-files data backups
```

Expected:

- `data/*.json`, `data/receipts/`, and `backups/` appear as ignored local
  files if they exist.
- `git ls-files data backups` should show only `data/.gitkeep` for `data/`
  and nothing from `backups/`.
- Demo data belongs in `data.example/` and `tests/fixtures/demo_data/`.

Do not publish screenshots, terminal output, logs, or docs containing real:

- account balances, bills, debts, receipts, merchants, names, addresses
- LAN IPs that identify your home setup
- absolute local paths from your machine
- backup directory contents

## Secret Scan

Run a quick text scan before publishing:

```bash
rg -n -i "password|passwd|secret|token|api[_-]?key|bearer|authorization|/home/|192\\.168\\.|10\\.0\\." \
  --glob '!data/**' --glob '!backups/**' --glob '!.venv/**' .
```

Review every hit. Test fixtures and documentation examples are fine; real
credentials or personal runtime values are not.

## Public Docs

Check these files after any behavior change:

- [README.md](../README.md) — quick explanation and startup path
- [docs/QUICKSTART.md](QUICKSTART.md) — first two minutes
- [docs/INSTALL.md](INSTALL.md) — setup and troubleshooting
- [docs/SECURITY.md](SECURITY.md) — LAN-only assumptions and optional password protection
- [docs/PRIVACY.md](PRIVACY.md) — local data and gitignore behavior
- [docs/DATA_MODEL.md](DATA_MODEL.md) — JSON shape
- [docs/ROADMAP.md](ROADMAP.md) — current status, not wishful thinking

## Demo Screenshots

Only capture screenshots from isolated synthetic data:

```bash
npm run screenshots:public
```

Then inspect every screenshot before committing it. It must show fake numbers
and no usernames, passwords, tokens, terminal output, local paths, LAN IPs, or
real household data.

## Security Position

BudgetPilot has a first-run local administrator account, CSRF protection,
security headers, and optional Basic Auth compatibility via
`BUDGETPILOT_PASSWORD`. It is still not a public-internet application.
Public release notes should say plainly:

- run it only on a trusted LAN or behind a VPN
- create the local administrator account before entering real data
- do not port-forward it
- do not expose it through a public tunnel
- remote access should use WireGuard/Tailscale or equivalent private VPN
