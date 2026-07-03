# apronmcp on Cloudflare Containers — Design

**Date:** 2026-07-03
**Status:** Approved (containers path chosen over a native Workers rewrite)

## Goal

Let anyone deploy their own remote apronmcp instance on Cloudflare — "deploy your own
Worker" model — so an MCP client (Claude Code, Claude Desktop) can reach it over
streamable HTTP from anywhere, with the user's Paperless141 credentials stored only as
secrets in their own Cloudflare account.

## Why Cloudflare Containers (not a Workers rewrite)

The server drives Paperless141 with Playwright and ~all of its value is the validated
ASP.NET selectors/flows and parsers, written in Python. Cloudflare Containers (GA
April 2026) runs that code unchanged inside a Docker image fronted by a thin Worker.
A native Workers port (`McpAgent` + `@cloudflare/playwright`) would rewrite every
parser and browser flow in TypeScript and leave two codebases to keep in sync.
Trade-off accepted: a few-second cold start when the container wakes, and the
$5/month Workers Paid plan that Containers require.

## Architecture

```
MCP client ──streamable HTTP + Bearer token──▶ Worker (cloudflare/worker.ts)
                                                 │  401 unless Authorization matches
                                                 ▼
                                        Container (Durable Object singleton)
                                          Python apronmcp, FastMCP http transport :8000
                                          Playwright Chromium inside the container
                                                 │
                                                 ▼
                                        advantage.paperlessfbo.com
```

### 1. Python server: transport switch

`apronmcp/server.py` `main()` reads `APRONMCP_TRANSPORT`:

- unset or `stdio` → `mcp.run()` exactly as today (local default; no behavior change).
- `http` → FastMCP streamable-HTTP transport on `0.0.0.0:8000`, endpoint `/mcp`.

No changes to tools, parsers, browser flows, or the preview-then-confirm write safety
model.

### 2. Dockerfile (repo root)

- Base: official `mcr.microsoft.com/playwright/python` image (Chromium + system deps
  preinstalled; pin a version compatible with the `playwright` pin in pyproject).
- `pip install .`, run `apronmcp` with `APRONMCP_TRANSPORT=http`, expose 8000.

### 3. Worker + wrangler config

- `wrangler.jsonc` at repo root: Worker `apronmcp`, container binding to the
  Dockerfile, Durable Object migration, `max_instances: 1`.
- `cloudflare/worker.ts` (~60 lines) using `@cloudflare/containers`:
  - Reject requests without `Authorization: Bearer <APRONMCP_TOKEN>` → 401.
    The container is never reachable unauthenticated.
  - Route `/mcp` to the container on port 8000; anything else → 404.
  - **Singleton:** one fixed Durable Object id, so at most one logged-in browser
    session exists — mirrors the local server's serialized calls and avoids
    concurrent logins to the same Paperless141 account.
  - `sleepAfter: "10m"` — scale to zero when idle. On wake, the existing
    session-expiry auto-re-login covers the fresh browser.
  - Secrets `PAPERLESS_USER`, `PAPERLESS_PASS` are forwarded from Worker env into
    the container's env; `APRONMCP_TOKEN` stays in the Worker only.

### 4. Deploy-your-own flow (README section)

```bash
git clone https://github.com/lxjhk/apronmcp && cd apronmcp
npm install                       # wrangler + @cloudflare/containers
npx wrangler secret put PAPERLESS_USER
npx wrangler secret put PAPERLESS_PASS
npx wrangler secret put APRONMCP_TOKEN    # any long random string you generate
npx wrangler deploy
claude mcp add --transport http apronmcp https://apronmcp.<subdomain>.workers.dev/mcp \
  --header "Authorization: Bearer <token>"
```

## Error handling

- Bad/missing token → 401 from the Worker; nothing reaches the container.
- Container cold start → Worker waits for the container port; first tool call after
  idle is a few seconds slower and triggers a fresh login (existing retry logic).
- Playwright/login failures inside the container surface as MCP tool errors exactly
  as they do locally.

## Testing

- Existing offline pytest suite unchanged (CI still green; transport switch gets a
  unit test).
- Local container verification: `docker build` + `docker run` with a `.env`, then an
  MCP initialize round-trip against `localhost:8000/mcp`.
- Live smoke test after `wrangler deploy`: `session_status` then `get_my_schedule`
  through the deployed URL (read-only tools only).

## Out of scope (v1)

- OAuth (needed only for claude.ai web connectors; Claude Code/Desktop use the
  bearer header). Can be layered on later with `workers-oauth-provider`.
- Multi-user / multi-tenant hosting — deliberately unsupported; one deployment per
  pilot, holding only their own credentials.
- Phase W2 `modify_reservation` (separate track on `feature/reservation-modify`).
