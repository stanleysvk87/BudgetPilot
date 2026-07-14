# Deploying as a persistent service (no root required)

This runs BudgetPilot as a **user-level** systemd service, so it doesn't
need `sudo` for the service itself (installing the `tesseract-ocr` system
package for OCR still does — see [../docs/receipt_ocr.md](../docs/receipt_ocr.md)).

```bash
cd ~/BudgetPilot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

mkdir -p ~/.config/systemd/user
cp deploy/budgetpilot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now budgetpilot.service

# Let it keep running after you log out / SSH disconnects:
loginctl enable-linger "$USER"
```

Check it's up:

```bash
systemctl --user status budgetpilot.service
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8765/
```

Then from any device on the same LAN: `http://<this-machine's-LAN-IP>:8765`.

## Optional password protection

Set `BUDGETPILOT_PASSWORD` to require HTTP Basic Auth for the whole web UI.
For the user service, keep the password out of git by using a private
systemd drop-in:

```bash
systemctl --user edit budgetpilot.service
```

Add:

```ini
[Service]
Environment=BUDGETPILOT_USER=saldo
Environment=BUDGETPILOT_PASSWORD=choose-a-long-password
```

Then reload:

```bash
systemctl --user daemon-reload
systemctl --user restart budgetpilot.service
```

## Updating to a newer version

```bash
cd ~/BudgetPilot
git pull
.venv/bin/pip install -r requirements.txt   # in case dependencies changed
systemctl --user restart budgetpilot.service
```

## Logs

```bash
journalctl --user -u budgetpilot.service -f
```

## OCR (optional)

The service runs fine without this — the receipt-upload form just won't
extract anything, you fill it in by hand on the review screen.

```bash
sudo apt install tesseract-ocr tesseract-ocr-slk
systemctl --user restart budgetpilot.service
```
