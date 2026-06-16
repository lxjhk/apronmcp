# paperless141-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that exposes your own
**Paperless141** flight-school account (the web app at
`https://advantage.paperlessfbo.com`) to an MCP client such as Claude.

Paperless141 has no API, so this server logs into the website with your credentials
using a headless browser (Playwright) and reads the pages. It only ever automates
**your own authenticated account** — you must have valid credentials and the right to
automate access to it.

## Tools

| Tool | What it returns |
|------|-----------------|
| `session_status()` | Whether a logged-in session is currently held. |
| `get_my_schedule()` | Your reservations: `schedule_number, resource, start, end, pilot, cfi, note`. |
| `get_account(limit=50)` | Recent transactions: `date, activity_type, amount, tax, comment, balance`. |
| `get_aircraft_availability(date=None, only_available=True)` | Each aircraft and the time slots where it is free, for a given date (YYYY-MM-DD; defaults to today). |

All tools are **read-only** — nothing is booked, edited, or deleted.

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
python -m paperless141_mcp.server
```

### Register with an MCP client

Add this to your client's MCP server config. Credentials can be supplied via the
`env` block (shown) or via the `.env` file above.

```json
{
  "mcpServers": {
    "paperless141": {
      "command": "/Users/lxjhk/Desktop/paperless/.venv/bin/python",
      "args": ["-m", "paperless141_mcp.server"],
      "env": {
        "PAPERLESS_USER": "your_user_id",
        "PAPERLESS_PASS": "your_password"
      }
    }
  }
}
```

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

- **Account pagination** — `get_account` reads only the first page of transactions.
- **Instructor availability** — the CFI schedule grid (`mstr9.aspx`) is captured during
  recon but not yet exposed as a tool.
- No write operations (booking, edits) — intentionally out of scope.
