# Desktop app

`desktop_app.py` runs the same Flask app (`budgetpilot_web.py`) unchanged
in a background thread, and opens it in a native OS window via
[pywebview](https://pywebview.flowrl.com/) instead of a browser tab. It is
packaging only — no routes, templates, or data model change.

This is meant for a single-user local install (e.g. your own laptop), not
for the LAN/multi-device deployment described in the main
[README](../README.md#open-it-from-another-device-on-your-lan-eg-your-phone)
or [DOCKER.md](DOCKER.md).

## Install

```bash
pip install -r requirements-desktop.txt
```

`requirements-desktop.txt` pulls in the normal `requirements.txt` plus
`pywebview`. It is intentionally separate from `requirements.txt` so the
server/Docker deployment never needs a GUI toolkit.

### Linux system dependencies

pywebview's GTK backend needs WebKitGTK and PyGObject (`gi`), which are
system packages, not something `pip` can reliably build. On
Debian/Ubuntu-based distros:

```bash
sudo apt install python3-webview   # pulls in gir1.2-webkit2-4.1 + python3-gi
# or, if python3-webview isn't packaged on your distro:
sudo apt install python3-gi gir1.2-webkit2-4.1
```

If you install these via `apt` (not `pip`) and also use a virtualenv,
create it with `--system-site-packages` so it can see the
system-installed `gi`/`webview` modules:

```bash
python3 -m venv --system-site-packages .venv-desktop
.venv-desktop/bin/pip install -r requirements-desktop.txt
```

## Run

```bash
python3 desktop_app.py
```

The window always binds Flask to `127.0.0.1` on a free port chosen at
startup — independent of `BUDGETPILOT_PORT`/`BUDGETPILOT_HOST`, so it never
collides with an already-running server/Docker instance on the same
machine.

## App-menu launcher (optional)

On a Linux desktop with a `.desktop` entry system (GNOME, KDE, COSMIC,
...), you can add BudgetPilot to the application menu:

1. A small wrapper script that `cd`s into the repo and runs the desktop
   entry point, e.g. `run_desktop.sh`:

   ```bash
   #!/bin/bash
   cd "$HOME/BudgetPilot" || exit 1
   exec .venv-desktop/bin/python3 desktop_app.py
   ```

2. `~/.local/share/applications/budgetpilot.desktop`:

   ```ini
   [Desktop Entry]
   Type=Application
   Name=BudgetPilot
   Comment=Forward-cashflow budget tracker
   Exec=/full/path/to/BudgetPilot/run_desktop.sh
   Icon=accessories-calculator
   Terminal=false
   Categories=Office;Finance;
   ```

3. `update-desktop-database ~/.local/share/applications` to refresh the
   menu immediately (otherwise it appears after the next login).

There is no dedicated BudgetPilot icon yet, hence the generic
`accessories-calculator` fallback.
