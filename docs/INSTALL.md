# Install

## Requirements

- Python 3.10 or newer (developed and tested on 3.10.12 and 3.11.2)
- [Flask](https://flask.palletsprojects.com/) — only needed to run the web
  UI (`budgetpilot_web.py`); the CLI (`budgetpilot.py`) and the test suite
  use only the Python standard library.
- `pytesseract` + `Pillow` — only needed for receipt-photo OCR (see
  [receipt_ocr.md](receipt_ocr.md)). Without them the upload form still
  works, it just won't extract anything — you fill the amount/date in by
  hand on the review screen.
- The system `tesseract` binary — only needed for OCR to actually extract
  text (`pytesseract` is just a wrapper around it): `sudo apt install
  tesseract-ocr tesseract-ocr-slk` on Debian/Ubuntu/Raspberry Pi OS.

## Install with a virtualenv (recommended)

```bash
cd BudgetPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Install without a virtualenv

```bash
pip install --user -r requirements.txt
```

## Dependency policy

`requirements.txt` is the supported Python dependency source for native
installs, Docker, and CI. Runtime packages use bounded major-version ranges
instead of open-ended minimums: Flask 3.x, Gunicorn 22-23, pytesseract
0.3.x, and Pillow 10-11. This keeps Python 3.10+ compatibility while
avoiding surprise major-version upgrades. JavaScript browser-test tooling is
installed with `npm ci` from the committed `package-lock.json`.

## Running

```bash
BUDGETPILOT_HOME="$PWD/.local-runtime" python3 budgetpilot.py
BUDGETPILOT_HOME="$PWD/.local-runtime" BUDGETPILOT_HOST=127.0.0.1 BUDGETPILOT_PORT=8765 python3 budgetpilot_web.py
python3 -m unittest discover -s tests
```

On first web launch, create the local administrator account. There is no
default password.

## Native Linux deployment layout

For a persistent native Linux installation, use separate application,
configuration, and data directories:

- application files: `/opt/budgetpilot`
- runtime data and backups: `/var/lib/budgetpilot`
- private environment file: `/etc/budgetpilot/budgetpilot.env`
- logs: systemd journal, or `/var/log/budgetpilot` if you add file logging

BudgetPilot does not hard-code these paths. Point it at the runtime data
directory with `BUDGETPILOT_HOME=/var/lib/budgetpilot`.

Example (see `deploy/README.md` for the full systemd walkthrough):

```bash
sudo useradd --system --home /var/lib/budgetpilot --create-home --shell /usr/sbin/nologin budgetpilot
sudo mkdir -p /opt/budgetpilot /var/lib/budgetpilot /etc/budgetpilot
sudo chown "$USER":"$USER" /opt/budgetpilot
sudo chown budgetpilot:budgetpilot /var/lib/budgetpilot
sudo chown root:root /etc/budgetpilot
sudo chmod 750 /etc/budgetpilot

cd /opt/budgetpilot
git clone https://github.com/stanleysvk87/BudgetPilot.git .
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo cp .env.example /etc/budgetpilot/budgetpilot.env
sudo chown root:root /etc/budgetpilot/budgetpilot.env
sudo chmod 640 /etc/budgetpilot/budgetpilot.env
```

`/etc/budgetpilot/budgetpilot.env` may hold secrets (e.g. `BUDGETPILOT_PASSWORD`),
so it stays root-owned and unreadable by other users — the systemd unit's
`EnvironmentFile=` directive is read by the (root) service manager before it
drops to the `budgetpilot` user, so this permission does not stop the service
from picking it up.

Edit `/etc/budgetpilot/budgetpilot.env` for native service use:

```bash
BUDGETPILOT_HOME=/var/lib/budgetpilot
BUDGETPILOT_HOST=127.0.0.1
BUDGETPILOT_PORT=8765
BUDGETPILOT_COOKIE_SECURE=false
BUDGETPILOT_PROXY_FIX=false
```

The systemd unit's `EnvironmentFile=` directive loads this file directly (see
`deploy/budgetpilot.service`) — that's the supported way to run with it, and
needs no extra permission handling on your part since the (root) service
manager reads the file before dropping to the `budgetpilot` user. The file is
root-only (640) on purpose, since it may hold secrets; don't loosen its
permissions for a manual test run. For a quick foreground check instead, use
an isolated runtime directory you own, as in the "Running" section above.

For a persistent native service, use the provided systemd unit, which runs
Gunicorn instead of Flask's development server.

## Running on Linux as a background service

A systemd unit is the recommended way to keep the web UI running
persistently. See `deploy/budgetpilot.service` and `deploy/README.md` for a
portable example. Without systemd, a terminal, `tmux`/`screen` session, or a
supervisor such as `supervisord` can run the same command.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**
Flask isn't installed in the Python environment you're running with —
install it (see above) or activate your virtualenv first.

**Web UI isn't reachable from my phone**
If `BUDGETPILOT_HOST=0.0.0.0`, the web UI should be reachable at
`http://<your-computer's-LAN-IP>:8765`. Check:
- your phone is on the same Wi-Fi network as the computer
- no firewall on the computer is blocking port 8765
- you used the LAN IP (e.g. `192.168.x.x`), not `localhost` or `127.0.0.1`

**I want to reset to a clean state**
Use the "Vymazať všetko" action in `/settings`, or load the fake demo state
with `python3 scripts/load_demo_data.py`. The script backs up existing
runtime data before copying `data.example/*.json` into `data/`. `data/*.json`
is runtime state and is ignored by git, so `git checkout -- data/` is no
longer the reset path.

**Port 8765 already in use**
Another process is using it, or a previous `budgetpilot_web.py` run is still
alive — find and stop it (`lsof -i :8765` on Linux), or set
`BUDGETPILOT_PORT` to another port.
