# Install

## Requirements

- Python 3.10 or newer (developed and tested on 3.10.12)
- [Flask](https://flask.palletsprojects.com/) — only needed to run the web
  UI (`budgetpilot_web.py`); the CLI (`budgetpilot.py`) and the test suite
  use only the Python standard library.

## Install with a virtualenv (recommended)

```bash
cd BudgetPilot
python3 -m venv .venv
source .venv/bin/activate
pip install flask
```

## Install without a virtualenv

```bash
pip install --user flask
```

## Running

```bash
python3 budgetpilot.py           # CLI
python3 budgetpilot_web.py       # web UI, http://localhost:8765
python3 -m unittest discover -s tests   # tests
```

## Running on Linux as a background service

There is no systemd unit shipped yet (see [ROADMAP.md](ROADMAP.md)). For now,
run it in a terminal, `tmux`/`screen` session, or a simple `nohup python3
budgetpilot_web.py &`.

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
Copy the demo files back from git (`git checkout -- data/`) or see
`rollback_latest.sh`, which restores the most recent `backups/` snapshot of
`budgetpilot.py`, `budgetpilot_web.py`, and `data/`.

**Port 8765 already in use**
Another process is using it, or a previous `budgetpilot_web.py` run is still
alive — find and stop it (`lsof -i :8765` on Linux), or edit the
`app.run(..., port=8765, ...)` line at the bottom of `budgetpilot_web.py`.
