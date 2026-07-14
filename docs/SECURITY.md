# Security

## Current assumptions

Saldo's web UI (`budgetpilot_web.py`) is built for **trusted LAN use only
unless you explicitly enable a password**:

- **Password protection is optional.** Set `BUDGETPILOT_PASSWORD` to enable
  HTTP Basic Auth for the whole web UI. The default username is `saldo`; set
  `BUDGETPILOT_USER` to override it.
- **Without `BUDGETPILOT_PASSWORD`, there is no authentication.** Anyone who
  can reach the server's address can view and edit all data.
- The server binds `0.0.0.0` on port `8765` specifically so it's reachable
  from other devices on your home network (e.g. your phone) — this is a
  feature, not an oversight, but it means it's also reachable by anything
  else on that network.
- Do **not** port-forward this to the public internet or run it on a
  network you don't fully trust. Basic Auth is a useful household/LAN guard,
  not a complete public-internet security model.

## Enabling a password

For an interactive shell:

```bash
export BUDGETPILOT_USER=saldo
export BUDGETPILOT_PASSWORD='choose-a-long-password'
python3 budgetpilot_web.py
```

For the user systemd service, create a private drop-in:

```bash
systemctl --user edit budgetpilot.service
```

Add:

```ini
[Service]
Environment=BUDGETPILOT_USER=saldo
Environment=BUDGETPILOT_PASSWORD=choose-a-long-password
```

Then run:

```bash
systemctl --user daemon-reload
systemctl --user restart budgetpilot.service
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

## Other notes

- `budgetpilot_web.py` calls `budgetpilot.py` via `subprocess` using a list
  of arguments (not a shell string), so it isn't vulnerable to shell
  injection through that call.
- There's no rate limiting, CSRF protection, or input sanitization beyond
  basic type coercion — acceptable for a single-household LAN tool, not
  acceptable if exposed publicly.

## Future direction

HTTP Basic Auth exists for simple household protection, but public exposure
would still need stronger hardening: HTTPS termination, CSRF protection,
rate limiting, monitoring, and regular dependency maintenance.

If you find a security issue, please open an issue describing it (avoid
including real financial data in the report).
