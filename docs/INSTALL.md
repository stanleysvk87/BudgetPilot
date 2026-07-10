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

## Running

```bash
python3 budgetpilot.py           # CLI
python3 budgetpilot_web.py       # web UI, http://localhost:8765
python3 -m unittest discover -s tests   # tests
```

## Running on Linux as a background service

A user-level systemd unit is the recommended way to keep the web UI running
persistently without root — see `deploy/budgetpilot.service` and
`deploy/README.md` for a ready-to-copy unit file and setup steps
(`systemctl --user enable --now budgetpilot.service`, with `loginctl
enable-linger $USER` so it survives logout). Without that, a terminal,
`tmux`/`screen` session, or `nohup python3 budgetpilot_web.py &` also work.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**
Flask isn't installed in the Python environment you're running with —
install it (see above) or activate your virtualenv first.

**Web UI isn't reachable from my phone**
`budgetpilot_web.py` binds to `0.0.0.0:8765`, so it should be reachable at
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
alive — find and stop it (`lsof -i :8765` on Linux), or edit the
`app.run(..., port=8765, ...)` line at the bottom of `budgetpilot_web.py`.
