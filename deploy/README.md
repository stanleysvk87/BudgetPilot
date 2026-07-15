# Deploying as a persistent service

This is an optional native Linux deployment path. Docker Compose is the
preferred public deployment method because it avoids distribution-specific
Python/package differences.

```bash
sudo useradd --system --home /var/lib/budgetpilot --create-home --shell /usr/sbin/nologin budgetpilot
sudo mkdir -p /opt/budgetpilot /etc/budgetpilot /var/lib/budgetpilot
sudo chown -R "$USER":"$USER" /opt/budgetpilot
sudo chown -R budgetpilot:budgetpilot /var/lib/budgetpilot

cd /opt/budgetpilot
git clone https://github.com/stanleysvk87/BudgetPilot.git .
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo cp .env.example /etc/budgetpilot/budgetpilot.env
sudo cp deploy/budgetpilot.service /etc/systemd/system/budgetpilot.service
sudo systemctl daemon-reload
sudo systemctl enable --now budgetpilot.service
```

Check it's up:

```bash
systemctl status budgetpilot.service
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8765/
```

Then open `http://localhost:8765` and create the first local administrator.
For LAN access, change `BUDGETPILOT_HOST` and firewall rules deliberately,
and keep access limited to a trusted network or VPN.

## Optional password protection

New installations should use the first-run local administrator account. If
you also need Basic Auth compatibility, keep values in
`/etc/budgetpilot/budgetpilot.env`, not in git:

```bash
BUDGETPILOT_USER=saldo
BUDGETPILOT_PASSWORD=choose-a-long-password
```

Then reload:

```bash
sudo systemctl restart budgetpilot.service
```

## Updating to a newer version

```bash
cd /opt/budgetpilot
git pull
.venv/bin/pip install -r requirements.txt   # in case dependencies changed
sudo systemctl restart budgetpilot.service
```

## Logs

```bash
journalctl -u budgetpilot.service -f
```

## OCR (optional)

The service runs fine without this — the receipt-upload form just won't
extract anything, you fill it in by hand on the review screen.

```bash
sudo apt install tesseract-ocr tesseract-ocr-slk
sudo systemctl restart budgetpilot.service
```
