# Paperless141 MCP — Design

**Date:** 2026-06-15
**Status:** Approved (design phase)

## Goal

Expose the **Paperless141** flight-school management system (https://advantage.paperlessfbo.com)
to Claude as an MCP server, focused on **read-only** use:

1. **Look up data** — schedules, student/aircraft records, flight logs, etc.
2. **Scheduling / availability** — read the calendar, find open slots for aircraft/instructors.

No write operations in scope (no booking, no record edits). Read-only keeps the live system safe
and the integration reliable.

## Key constraint

Paperless141 exposes **no API**. The only access is the web login form (`mstr7p.aspx`), a classic
ASP.NET application (ViewState, `__doPostBack`, event-validation tokens). The MCP must therefore
authenticate and read pages the way a browser does. This only automates the user's **own
authenticated account** — it requires the user's legitimate credentials and access.

## Architecture — Hybrid (Playwright login + httpx reads)

```
Claude  ──MCP(stdio)──▶  paperless141-mcp (Python)
                              │
                  ┌───────────┼────────────────────────┐
                  ▼           ▼                         ▼
           SessionManager   httpx client            Playwright
           (Playwright      (fast reads,            (fallback for
            login →         seeded w/ session        JS/postback
            cookies)        cookies)                 pages only)
                              │
                              ▼
                          Parsers (BeautifulSoup)
                          HTML → structured JSON
```

On the first tool call, **SessionManager** uses Playwright (headless Chromium) to log in once and
extract the ASP.NET session/auth cookies. Those cookies seed a fast **httpx** client that performs
the actual data reads. Returned HTML is run through page-specific **parsers** into clean JSON.
Any page that turns out to require JavaScript/postback navigation falls back to Playwright for that
single page — so we are never blocked by a JS-heavy screen.

Rationale for hybrid over pure-Playwright or pure-HTTP: Playwright reliably handles the brittle
ASP.NET login (ViewState/JS), while httpx makes the repeated data reads fast and cheap. The
Playwright fallback removes the main risk of the pure-HTTP approach.

## Components (each small, independently testable)

| File | Responsibility |
|------|----------------|
| `session.py` | Login via Playwright, cookie extraction, session-expiry detection + auto re-login. |
| `client.py`  | httpx wrapper (cookies + browser-like headers); Playwright fallback for JS pages. |
| `parsers/`   | One function per screen: raw HTML → structured JSON. No network, pure functions. |
| `tools.py`   | MCP tool definitions — thin wrappers over client + parsers. |
| `server.py`  | MCP server wiring (Python MCP SDK, stdio transport). |
| `recon.py`   | One-shot capture command: log in, walk key pages, dump HTML to `fixtures/`. |

## Tools (tentative — finalized after recon)

- `get_schedule(start_date, end_date, resource?)` — schedule/calendar entries in a date range.
- `check_availability(resource, date)` — open slots for an aircraft/instructor on a date.
- `lookup(query)` / `get_student(id_or_name)` — read student/aircraft/log records.
- `session_status()` — health/debug (logged in? session age?).

Exact tool names, arguments, and return shapes are finalized **after recon** reveals the real page
structure. The list above is the intended surface, not a contract.

## Credentials & config

- Read from environment: `PAPERLESS_USER`, `PAPERLESS_PASS`, plus `PAPERLESS_BASE_URL`
  (default `https://advantage.paperlessfbo.com`).
- Stored locally in a git-ignored `.env` (loaded for local runs) and/or the MCP client's server
  `env` block. **Never** hardcoded, committed, or printed to logs/stdout.
- Session/cookies live in memory only for the life of the process.

## Phase 0: Reconnaissance (required first, server-driven)

The page structure behind the login is unknown. Before writing any parser:

1. User puts credentials in a local `.env`.
2. Run `python -m paperless141_mcp.recon`. It logs in (Playwright) and saves HTML snapshots of the
   login flow + scheduling and lookup pages into `fixtures/` (with secrets scrubbed).
3. Those snapshots become **test fixtures**. Parsers are built test-first against real HTML — no
   guessing about the DOM.

The user never copies HTML by hand; the server captures it.

## Error handling

- **Session expired** (the login page warns it happens) → auto re-login once, then retry the read.
- **Login failure** (bad creds / changed form) → clear, actionable error; no infinite retry.
- **Parse mismatch** (site markup changed) → return an error plus a raw HTML snippet for diagnosis,
  rather than silently returning wrong data.
- **Politeness** — single in-flight session, no parallel hammering of the site, reasonable timeouts.

## Testing

- **Parsers**: offline unit tests against saved `fixtures/` HTML — deterministic, no network.
- **Session/client**: tested against mocks/recorded responses.
- **Live smoke test**: a single manual end-to-end check, run deliberately, not in CI.

## Out of scope (YAGNI)

- Any write/mutation operation (booking, edits).
- Multi-user / credential-vault features — single user, single account.
- Caching layer / persistence — in-memory session only, until proven necessary.
