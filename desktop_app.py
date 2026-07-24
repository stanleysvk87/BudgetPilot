#!/usr/bin/env python3
"""Desktop entry point for BudgetPilot.

Runs the existing Flask app (budgetpilot_web.py) unchanged in a background
thread and opens it in a native OS window via pywebview instead of a browser
tab. No route/template/data-model changes — this is packaging only.
"""
import os
import socket
import threading
import time
import urllib.request

# Desktop mode is single-user/local: never bind to 0.0.0.0 (the server
# deployment default) and never collide with a systemd-managed instance on
# the default port 8765. Host/port are decided here rather than reusing
# budgetpilot_web's own app.run() call (which some branches hardcode to
# 0.0.0.0:8765) so this works regardless of which branch/checkout is used.
HOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


PORT = _free_port()

import webview  # noqa: E402  (import after HOST/PORT are decided)

from budgetpilot_web import app  # noqa: E402


def _run_flask() -> None:
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def _wait_until_ready(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5).close()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main() -> None:
    url = f"http://{HOST}:{PORT}/"
    threading.Thread(target=_run_flask, daemon=True).start()
    _wait_until_ready(url)
    webview.create_window("BudgetPilot", url, width=1200, height=800, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
