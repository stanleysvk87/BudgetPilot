# Docker

BudgetPilot can run in a small Python container. The container runs Gunicorn
as a non-root user and stores runtime data, backups, the local user database,
and the session secret under `/var/lib/budgetpilot`, backed by a named Docker
volume.

## Local-only Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:8765`.

The default Compose file binds to `127.0.0.1` only. On first launch, create
the local administrator account before entering financial data.

If you want LAN access from another device, set `BUDGETPILOT_BIND=0.0.0.0`
in your private `.env` file and keep the app on a trusted network or private
VPN. Do not expose this container directly to the public internet.

`BUDGETPILOT_HOST_PORT` changes the host-side port without changing the
container's internal port.

`BUDGETPILOT_WORKERS` controls the Gunicorn worker count inside the
container. The default is `2`.

## Backups

Back up the named Docker volume while the container is stopped:

```bash
docker compose down
docker run --rm -v budgetpilot_budgetpilot-data:/data -v "$PWD":/backup alpine \
  tar -czf /backup/budgetpilot-data-backup.tgz -C /data .
```

Restore from a trusted backup, then restart:

```bash
docker run --rm -v budgetpilot_budgetpilot-data:/data -v "$PWD":/backup alpine \
  sh -c 'rm -rf /data/* && tar -xzf /backup/budgetpilot-data-backup.tgz -C /data'
docker compose up -d
```

## Notes

Receipt OCR may need extra system packages (`tesseract-ocr` and language
data). The base image intentionally does not install them yet, so manual
expense entry still works and OCR gracefully falls back when unavailable.

## Reverse Proxy Example

Minimal Caddy example for a private network or VPN hostname:

```caddyfile
budgetpilot.example.invalid {
  reverse_proxy 127.0.0.1:8765
}
```

When using HTTPS through a trusted proxy, set `BUDGETPILOT_COOKIE_SECURE=true`
and `BUDGETPILOT_PROXY_FIX=true`. BudgetPilot is not designed to run under a
URL subpath such as `/budgetpilot`; use a dedicated hostname.
