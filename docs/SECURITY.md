# Security

## Current assumptions

BudgetPilot's web UI (`budgetpilot_web.py`) is built for **trusted LAN use
only**:

- **No authentication.** Anyone who can reach the server's address can view
  and edit all data — there is no login, no session, no access control.
- The server binds `0.0.0.0` on port `8765` specifically so it's reachable
  from other devices on your home network (e.g. your phone) — this is a
  feature, not an oversight, but it means it's also reachable by anything
  else on that network.
- Do **not** port-forward this to the public internet or run it on a
  network you don't fully trust. There is nothing standing between an
  attacker on the network and full read/write access to your financial
  data.

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

Authentication (even something simple like HTTP basic auth or a single
shared password) should be added before this app is ever considered for
exposure beyond a trusted LAN/VPN — see [ROADMAP.md](ROADMAP.md). It is not
implemented today.

If you find a security issue, please open an issue describing it (avoid
including real financial data in the report).
