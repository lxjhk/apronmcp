# apronmcp

An [MCP](https://modelcontextprotocol.io) server that exposes your own
**Paperless141** flight-school account (the web app at
`https://advantage.paperlessfbo.com`) to an MCP client such as Claude — check your
schedule, find open aircraft, and book or cancel reservations in plain language.

Paperless141 has no API, so this server logs into the website with your credentials
using a headless browser (Playwright) and reads the pages. It only ever automates
**your own authenticated account** — you must have valid credentials and the right to
automate access to it.

> **Disclaimer:** apronmcp is an unofficial, community-built tool. It is not
> affiliated with or endorsed by Paperless141 / PaperlessFBO. Automating your account
> may be restricted by your flight school's or Paperless141's terms of service —
> check before using it, and use it at your own risk.

## Tools

### Read-only

| Tool | What it returns |
|------|-----------------|
| `session_status()` | Whether a logged-in session is currently held. |
| `get_my_schedule()` | Your reservations: `schedule_number, resource, start, end, pilot, cfi, note`. |
| `get_account(limit=50)` | Recent transactions: `date, activity_type, amount, tax, comment, balance`. |
| `get_aircraft_availability(date=None, only_available=True)` | Each aircraft and the time slots where it is free, for a given date (YYYY-MM-DD; defaults to today). |
| `find_open_slots(date, type_or_tail=None)` | Free `(reg, type, location, time)` slots for a date, optionally filtered by aircraft type or tail. |

### Write (preview-then-confirm)

| Tool | Behaviour |
|------|-----------|
| `create_reservation(date, start, end, tail, cfi=None, category=None, note=None, confirm=False)` | `confirm=False` (default) **previews** only. `confirm=True` books the slot and returns the new `schedule_number`. |
| `cancel_reservation(schedule_number, confirm=False, reason="Schedule Error")` | `confirm=False` previews. `confirm=True` deletes that one reservation. |

**Write safety model:**
- Every write tool defaults to `confirm=False` — it describes the intended change and writes nothing. A live write happens only with `confirm=True`.
- `cancel_reservation` only ever affects the single `schedule_number` you pass — never a list or range.
- Success is confirmed by re-reading your schedule; the tools never claim a write succeeded that they couldn't verify.
- A booking is silently rejected by Paperless141 unless the aircraft+time is genuinely free, within operating hours, and you're checked out on the aircraft.

> Modify is not yet implemented (Phase W2, in progress).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

Create a `.env` file (git-ignored — never committed) with your login:

```
PAPERLESS_USER=your_user_id
PAPERLESS_PASS=your_password
PAPERLESS_BASE_URL=https://advantage.paperlessfbo.com
```

## Run as an MCP server

```bash
apronmcp            # or: python -m apronmcp.server
```

### Register with an MCP client

Add this to your client's MCP server config (e.g. `claude mcp add` or
`claude_desktop_config.json`), pointing at the Python environment where you
installed apronmcp. Credentials can be supplied via the `env` block (shown) or
via the `.env` file above.

```json
{
  "mcpServers": {
    "apronmcp": {
      "command": "/path/to/.venv/bin/apronmcp",
      "env": {
        "PAPERLESS_USER": "your_user_id",
        "PAPERLESS_PASS": "your_password"
      }
    }
  }
}
```

## Deploy your own on Cloudflare (remote MCP)

You can run apronmcp as a remote MCP server on your own Cloudflare account —
the Python server runs in a [Cloudflare Container](https://developers.cloudflare.com/containers/)
behind a Worker that requires a bearer token. Your credentials live only in your
Cloudflare account as secrets. Requires the Workers Paid plan ($5/mo — Containers
are not on the free tier).

```bash
git clone https://github.com/lxjhk/apronmcp && cd apronmcp
npm install
npx wrangler login
npx wrangler secret put PAPERLESS_USER
npx wrangler secret put PAPERLESS_PASS
openssl rand -hex 32          # generate a token, use it in the next step
npx wrangler secret put APRONMCP_TOKEN
npx wrangler deploy
```

Then register it with your MCP client:

```bash
claude mcp add --transport http apronmcp \
  https://apronmcp.<your-subdomain>.workers.dev/mcp \
  --header "Authorization: Bearer <your APRONMCP_TOKEN>"
```

Notes:

- The container sleeps after 10 minutes idle; the first call after that takes a
  few extra seconds (cold start + fresh login).
- Only one container instance ever runs, so there is never more than one
  logged-in browser session against your account.
- claude.ai **web** connectors require OAuth and are not supported by the
  bearer-token setup; Claude Code and Claude Desktop work.

## How it works

- **`session.py`** — logs into the ASP.NET form (`mstr7p.aspx`); shared `submit_login()`
  handles the cookie banner and the real field selectors.
- **`browser.py`** — a persistent Playwright session. Navigation in Paperless141 is
  entirely ASP.NET postback (menu buttons run `SetDestination(...)` then submit), so the
  browser stays open and clicks the menu for each page. Calls are serialized; the session
  re-logs-in automatically on expiry.
- **`parsers/`** — turn each page's `GridView` table into clean JSON. Robust to ASP.NET
  pager/control rows. The availability grid is classified into `free` / `unavailable` /
  `booked` cells.
- **`recon.py`** — a one-shot capture tool used during development to snapshot the
  authenticated pages into `tests/fixtures/` (git-ignored; may contain real data).

## Development

```bash
pytest -q          # parser/unit tests run offline against synthetic *_sample.html fixtures
```

Parsers are also tested against the real captured fixtures (`tests/fixtures/*.html`) when
those are present locally — those files are git-ignored because they can contain real
student/flight data.

## Known limitations / not yet built

- **Modify reservations** — discovered (`ButModSched` on `mstr7a.aspx`) but not yet built (Phase W2).
- **Account pagination** — `get_account` reads only the first page of transactions.
- **Instructor availability** — the CFI schedule grid (`mstr9.aspx`) is captured during
  recon but not yet exposed as a tool.
- `find_open_slots` depends on the scheduler board's client-side rendering; on some dates the
  board only renders clickable free cells for a subset of aircraft. `create_reservation` does
  not rely on this (it sets the aircraft/time directly in the booking modal).

## License

[MIT](LICENSE)
