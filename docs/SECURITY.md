# Security

## Current assumptions

BudgetPilot's web UI (`budgetpilot_web.py`) is built for **localhost,
trusted LAN, or private VPN/Tailscale access**. It is not currently designed
for direct public-internet exposure.

- On first launch, BudgetPilot requires creation of a local administrator
  account. Passwords are stored as Werkzeug password hashes in
  `data/users.json`, never as plaintext.
- Existing deployments may still set `BUDGETPILOT_PASSWORD` for HTTP Basic
  Auth compatibility. The default Basic Auth username is currently `saldo`;
  set `BUDGETPILOT_USER` to override it. New deployments should use the
  first-run administrator account as the primary auth mechanism.
- Every financial page and state-changing route is protected by the local
  admin session or valid Basic Auth compatibility credentials.
- Native runs historically bind `0.0.0.0:8765` so the app is reachable
  from other devices on your home network (e.g. your phone). Override this
  with `BUDGETPILOT_HOST=127.0.0.1` for localhost-only native use. Docker
  Compose binds the host side to `127.0.0.1` by default.
- Do **not** port-forward this to the public internet or run it on a
  network you don't fully trust. Login is a useful household/LAN guard, not
  a complete public-internet security model.

## First-run administrator

On a fresh runtime data directory, open the app and create the first local
administrator. There is no universal default username or password.

The password hash is stored in `data/users.json`, alongside other local
runtime data. You can change the local administrator username and password
from Settings -> Administrator and security. Password changes require the
current password, store a new Werkzeug password hash, and keep the
single-administrator model.

Back up `data/users.json` with the rest of the `data/` directory. If you
lose the password, there is intentionally no insecure password-recovery
workflow; restore from backup or stop the app and carefully replace the
local user file.

## Basic Auth compatibility

For existing deployments that already use HTTP Basic Auth:

```bash
export BUDGETPILOT_USER=saldo
export BUDGETPILOT_PASSWORD='choose-a-long-password'
python3 budgetpilot_web.py
```

For the native systemd service example, keep credentials in
`/etc/budgetpilot/budgetpilot.env`:

```ini
Environment=BUDGETPILOT_USER=saldo
Environment=BUDGETPILOT_PASSWORD=choose-a-long-password
```

Then run:

```bash
sudo systemctl restart budgetpilot.service
```

## Remote access

If you want to check your dashboard away from home, put it behind a VPN
rather than exposing the port directly:

- [WireGuard](https://www.wireguard.com/) or
  [Tailscale](https://tailscale.com/) are good fits for a single home
  server — you connect to your own network first, then reach
  `http://<lan-ip>:8765` exactly as you would at home.
- Do not use port-forwarding + `ngrok`-style public tunnels for this app in
  its current form.

## Reverse proxies

Reverse proxies such as Caddy, Nginx, and Traefik can terminate HTTPS and
limit network access, but they are not a substitute for BudgetPilot's login.
If you run behind a trusted HTTPS proxy, set:

```bash
export BUDGETPILOT_PROXY_FIX=true
export BUDGETPILOT_COOKIE_SECURE=true
export BUDGETPILOT_PUBLIC_URL=https://budgetpilot.example.invalid
```

Do not enable `BUDGETPILOT_PROXY_FIX` unless the app only receives traffic
from that trusted proxy. When enabled, Flask trusts forwarded host, scheme,
port, and client-IP headers from that proxy; enabling it for direct or
untrusted traffic lets clients influence what the app sees as the request
origin.

## Other notes

- `budgetpilot_web.py` calls `budgetpilot.py` via `subprocess` using a list
  of arguments (not a shell string), so it isn't vulnerable to shell
  injection through that call.
- There is CSRF protection for state-changing requests, conservative
  security headers, receipt-id path validation, and basic type coercion.
  Repeated failed logins are throttled server-side by observed client IP.
  This is a practical household/LAN guard, not a complete brute-force
  defense for hostile public traffic.
- IP-based lockout depends on how the app observes client addresses. Shared
  NAT can group multiple household devices under one address. Reverse
  proxies can make all clients appear as the proxy address unless forwarded
  headers are configured correctly, and forwarded headers must only be
  trusted from a proxy you control.
- BudgetPilot still must not be exposed directly to the public internet.
  Private VPN access through WireGuard, Tailscale, or an equivalent private
  network remains the recommended remote-access model.

## Future direction

The local administrator account is intentionally simple. Public exposure
would still need stronger hardening: HTTPS termination, rate limiting,
monitoring, stronger authentication, and regular dependency maintenance.

If you find a security issue, use GitHub Private Vulnerability Reporting
when available. If this repository has no private reporting channel, open a
minimal public issue requesting private contact and do not include sensitive
details, real financial data, passwords, receipt photos, private network
details, local paths, screenshots, or data-file contents.
