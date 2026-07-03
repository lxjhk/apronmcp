# Cloudflare Containers Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make apronmcp deployable as a remote MCP server on Cloudflare Containers — existing Python/Playwright server in a Docker image, fronted by a thin bearer-token auth Worker, deploy-your-own model.

**Architecture:** `apronmcp.server.main()` gains an `APRONMCP_TRANSPORT=http` switch that runs FastMCP's streamable-HTTP transport on `0.0.0.0:8000`. A Dockerfile (official Playwright Python base image) packages the server. A ~50-line Worker (`@cloudflare/containers`) rejects requests without the `APRONMCP_TOKEN` bearer secret and routes `/mcp` to a singleton container instance.

**Tech Stack:** Python 3.11+ / FastMCP (`mcp` ≥1.10), Playwright 1.61, Docker, Cloudflare Workers + Containers, wrangler v4, `@cloudflare/containers`.

**Design spec:** `docs/superpowers/specs/2026-07-03-cloudflare-containers-deploy-design.md`

## Global Constraints

- Local stdio behavior must be unchanged: `apronmcp` with no env vars set runs stdio exactly as today.
- The container must never be reachable without the bearer token — auth lives in the Worker, before any routing.
- Exactly one container instance (`max_instances: 1`, fixed instance name `"singleton"`) so at most one Paperless141 browser login exists.
- Playwright version in the image is pinned to the base image's version: `playwright==1.61.0` with base `mcr.microsoft.com/playwright/python:v1.61.0-noble`.
- Secrets are `PAPERLESS_USER`, `PAPERLESS_PASS`, `APRONMCP_TOKEN` — Worker secrets only; `APRONMCP_TOKEN` is never forwarded into the container.
- All offline tests (`pytest -q`) must stay green after every task.

---

### Task 1: `APRONMCP_TRANSPORT` switch in `server.py`

**Files:**
- Modify: `src/apronmcp/server.py` (the `main()` function at the bottom, currently `def main() -> None: mcp.run()`)
- Modify: `pyproject.toml` (raise `mcp>=1.2.0` → `mcp>=1.10` — streamable HTTP needs it)
- Test: `tests/test_server_transport.py` (new)

**Interfaces:**
- Produces: `transport_from_env(value: str | None) -> str` — maps env value to a FastMCP transport name; `main()` honors `APRONMCP_TRANSPORT`. Task 2's Dockerfile relies on `APRONMCP_TRANSPORT=http` + console script `apronmcp` serving `POST /mcp` on port 8000.

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_transport.py`:

```python
import pytest

from apronmcp.server import transport_from_env


def test_default_is_stdio():
    assert transport_from_env(None) == "stdio"


def test_explicit_stdio():
    assert transport_from_env("stdio") == "stdio"


def test_http_maps_to_streamable_http():
    assert transport_from_env("http") == "streamable-http"


def test_unknown_value_raises():
    with pytest.raises(ValueError, match="APRONMCP_TRANSPORT"):
        transport_from_env("carrier-pigeon")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_server_transport.py -v`
Expected: FAIL — `ImportError: cannot import name 'transport_from_env'`

- [ ] **Step 3: Implement**

In `src/apronmcp/server.py`, add `import os` to the imports, then replace:

```python
def main() -> None:
    mcp.run()  # stdio transport
```

with:

```python
def transport_from_env(value: str | None) -> str:
    """Map APRONMCP_TRANSPORT to a FastMCP transport name (default: stdio)."""
    if value is None or value == "stdio":
        return "stdio"
    if value == "http":
        return "streamable-http"
    raise ValueError(f"APRONMCP_TRANSPORT must be 'stdio' or 'http', got {value!r}")


def main() -> None:
    transport = transport_from_env(os.environ.get("APRONMCP_TRANSPORT"))
    if transport == "streamable-http":
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = 8000
        mcp.settings.stateless_http = True  # survives container sleep/wake
    mcp.run(transport=transport)
```

In `pyproject.toml` change `"mcp>=1.2.0",` to `"mcp>=1.10",`.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -q`
Expected: all pass (40 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/apronmcp/server.py tests/test_server_transport.py pyproject.toml
git commit -m "feat: APRONMCP_TRANSPORT=http runs streamable-HTTP transport on :8000"
```

---

### Task 2: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)

**Interfaces:**
- Consumes: Task 1's `APRONMCP_TRANSPORT=http` behavior and the `apronmcp` console script.
- Produces: an image that serves streamable-HTTP MCP on container port 8000; Task 3's `wrangler.jsonc` points at `./Dockerfile`.

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.venv
venv
node_modules
tests
docs
scripts
.env
.env.*
__pycache__
*.pyc
*.egg-info
.github
.playwright
uv.lock
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
# Base image bundles Chromium + system deps matching Playwright 1.61.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Pin playwright to the base image's browser version, then install the package.
RUN pip install --no-cache-dir "playwright==1.61.0" \
    && pip install --no-cache-dir .

ENV APRONMCP_TRANSPORT=http
EXPOSE 8000
CMD ["apronmcp"]
```

- [ ] **Step 3: Verify with a local build (skip if Docker unavailable)**

```bash
docker build -t apronmcp:local .
docker run --rm -d --name apronmcp-test -p 8000:8000 --env-file .env apronmcp:local
sleep 3
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
docker rm -f apronmcp-test
```

Expected: an SSE/JSON response containing `"serverInfo"` with `"name":"apronmcp"`.
If Docker is not installed locally, note it and rely on the Task 5 deploy-time verification (Cloudflare builds the image remotely).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: Dockerfile for Cloudflare Containers (Playwright base, http transport)"
```

---

### Task 3: Auth Worker + wrangler config + package.json

**Files:**
- Create: `cloudflare/worker.ts`
- Create: `wrangler.jsonc` (repo root)
- Create: `package.json` (repo root)
- Modify: `.gitignore` (add `package-lock.json`? No — commit the lockfile; add `.wrangler/` build cache)

**Interfaces:**
- Consumes: Task 2's image (`./Dockerfile`, port 8000).
- Produces: Worker `apronmcp` exposing `POST /mcp` guarded by `Authorization: Bearer <APRONMCP_TOKEN>`; secrets `PAPERLESS_USER`/`PAPERLESS_PASS` forwarded into the container env.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "apronmcp-cloudflare",
  "private": true,
  "scripts": {
    "deploy": "wrangler deploy",
    "check": "wrangler deploy --dry-run"
  },
  "devDependencies": {
    "wrangler": "^4.0.0"
  },
  "dependencies": {
    "@cloudflare/containers": "^0.0.28"
  }
}
```

Then run: `npm install` (creates `package-lock.json` — commit it).

- [ ] **Step 2: Create `cloudflare/worker.ts`**

```ts
import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

export class ApronContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "10m";
  // Paperless141 credentials go into the container; APRONMCP_TOKEN stays in the Worker.
  envVars = {
    PAPERLESS_USER: (env as Record<string, string>).PAPERLESS_USER ?? "",
    PAPERLESS_PASS: (env as Record<string, string>).PAPERLESS_PASS ?? "",
    PAPERLESS_BASE_URL:
      (env as Record<string, string>).PAPERLESS_BASE_URL ??
      "https://advantage.paperlessfbo.com",
  };
}

interface WorkerEnv {
  APRONMCP_TOKEN: string;
  APRON_CONTAINER: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, workerEnv: WorkerEnv): Promise<Response> {
    const auth = request.headers.get("Authorization") ?? "";
    if (!workerEnv.APRONMCP_TOKEN || auth !== `Bearer ${workerEnv.APRONMCP_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    const { pathname } = new URL(request.url);
    if (pathname === "/mcp" || pathname.startsWith("/mcp/")) {
      // Fixed instance name -> exactly one container / one Paperless141 login.
      return getContainer(workerEnv.APRON_CONTAINER, "singleton").fetch(request);
    }
    return new Response("Not found", { status: 404 });
  },
};
```

- [ ] **Step 3: Create `wrangler.jsonc`**

```jsonc
{
  "name": "apronmcp",
  "main": "cloudflare/worker.ts",
  "compatibility_date": "2026-06-01",
  "containers": [
    {
      "class_name": "ApronContainer",
      "image": "./Dockerfile",
      "max_instances": 1,
      "instance_type": "standard"
    }
  ],
  "durable_objects": {
    "bindings": [{ "name": "APRON_CONTAINER", "class_name": "ApronContainer" }]
  },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["ApronContainer"] }]
}
```

- [ ] **Step 4: Add `.wrangler/` and `node_modules/` to `.gitignore`** (node_modules is already there; add `.wrangler/`).

- [ ] **Step 5: Validate config**

Run: `npx wrangler deploy --dry-run`
Expected: config parses and bundling succeeds; output ends with a dry-run notice and no error. (No Cloudflare login needed for a dry run.)

- [ ] **Step 6: Commit**

```bash
git add cloudflare/worker.ts wrangler.jsonc package.json package-lock.json .gitignore
git commit -m "feat: Cloudflare Worker (bearer auth) + Containers config for remote MCP"
```

---

### Task 4: README "Deploy your own on Cloudflare" section

**Files:**
- Modify: `README.md` (after the "Register with an MCP client" section)

**Interfaces:**
- Consumes: everything above; documents the exact commands a stranger runs.

- [ ] **Step 1: Add the section**

Insert after the local MCP-client JSON block:

```markdown
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
```

- [ ] **Step 2: Run tests (docs-only change, sanity check)**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: deploy-your-own Cloudflare instructions"
```

---

### Task 5: Live deploy + smoke test (needs the user's Cloudflare account)

**Files:** none (operational).

- [ ] **Step 1: Authenticate** — user runs `! npx wrangler login` (interactive) or exports `CLOUDFLARE_API_TOKEN`.
- [ ] **Step 2: Set the three secrets** (`wrangler secret put` ×3; generate `APRONMCP_TOKEN` with `openssl rand -hex 32`).
- [ ] **Step 3: `npx wrangler deploy`** — Cloudflare builds the image remotely; expect a `*.workers.dev` URL.
- [ ] **Step 4: Negative auth check** — `curl -i https://apronmcp.<sub>.workers.dev/mcp` (no header). Expected: `401 Unauthorized`.
- [ ] **Step 5: MCP initialize with the token** (same curl as Task 2 Step 3 plus `-H "Authorization: Bearer <token>"` against the workers.dev URL). Expected: `serverInfo.name == "apronmcp"`.
- [ ] **Step 6: Read-only smoke test** — `claude mcp add` as documented, then call `session_status` and `get_my_schedule`. Expected: real schedule rows; **no write tools invoked**.

---

## Self-review notes

- Spec coverage: transport switch (T1), Dockerfile (T2), Worker/auth/singleton/sleepAfter/secrets (T3), README deploy flow (T4), live verification (T5). Out-of-scope items (OAuth, multi-user, W2) have no tasks — intentional.
- `@cloudflare/containers` version: `^0.0.28` is a floor guess from mid-2026; `npm install` in T3 resolves the current release — if the package's minor API differs (e.g. `envVars` naming), consult https://github.com/cloudflare/containers and adjust in place.
- `stateless_http=True` avoids broken sessions after container sleep; if the deployed client shows tool-list but calls fail, re-test with it removed.
