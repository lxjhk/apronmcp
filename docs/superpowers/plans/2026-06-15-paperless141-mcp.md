# Paperless141 MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only MCP server (Python) that logs into the Paperless141 flight-school web app and exposes its schedule/availability and lookup data to Claude.

**Architecture:** Hybrid — Playwright performs the brittle ASP.NET login and yields session cookies; a fast httpx client seeded with those cookies does the data reads; BeautifulSoup parsers turn HTML into JSON; any JS/postback page falls back to Playwright. There is NO API — everything is driven through the authenticated web UI of the user's own account.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP) SDK, `playwright`, `httpx`, `beautifulsoup4`, `python-dotenv`, `pytest`, `pytest-asyncio`.

**Design spec:** `docs/superpowers/specs/2026-06-15-paperless141-mcp-design.md`

---

## Phase ordering & the recon checkpoint

- **Phase A (Tasks 1–6):** fully specifiable now — scaffold, config, session/login, recon tool, server skeleton.
- **🛑 RECON CHECKPOINT (after Task 4):** the user runs `python -m paperless141_mcp.recon`. This produces real HTML fixtures in `fixtures/`. **Do not write parsers before this exists.**
- **Phase B (Tasks 7+):** parsers + data tools, built test-first against the captured fixtures. Task 7 is a complete worked example; each additional screen repeats that exact pattern with selectors matched to its real fixture.

---

## File Structure

```
pyproject.toml                         # project + deps
.env.example                           # documents required env vars (committed)
.env                                   # real creds (git-ignored, user-created)
src/paperless141_mcp/
    __init__.py
    config.py                          # load + validate env config
    session.py                         # Playwright login -> cookies; expiry + re-login
    client.py                          # httpx wrapper (cookies+headers); Playwright fallback
    recon.py                           # one-shot: login, walk pages, dump HTML to fixtures/
    parsers/
        __init__.py
        schedule.py                    # schedule HTML -> JSON (Phase B)
    tools.py                           # MCP tool fns (Phase B for data tools)
    server.py                          # FastMCP server wiring (stdio)
tests/
    test_config.py
    test_session.py
    test_client.py
    parsers/
        test_schedule.py
    fixtures/                          # captured HTML lives here (git-ignored)
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/paperless141_mcp/__init__.py`
- Create: `.env.example`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "paperless141-mcp"
version = "0.1.0"
description = "Read-only MCP server for the Paperless141 flight-school web app"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2.0",
    "playwright>=1.44",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

- [ ] **Step 2: Create package marker**

`src/paperless141_mcp/__init__.py`:

```python
"""Read-only MCP server for the Paperless141 flight-school web app."""
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.env.example`**

```
PAPERLESS_USER=your_user_id
PAPERLESS_PASS=your_password
PAPERLESS_BASE_URL=https://advantage.paperlessfbo.com
```

- [ ] **Step 4: Install deps and browser**

Run:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```
Expected: installs succeed; Chromium downloads.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/paperless141_mcp/__init__.py .env.example
git commit -m "chore: scaffold paperless141-mcp project"
```

---

## Task 2: Config loading

**Files:**
- Create: `src/paperless141_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
import pytest
from paperless141_mcp.config import load_config, ConfigError


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    monkeypatch.delenv("PAPERLESS_BASE_URL", raising=False)
    cfg = load_config()
    assert cfg.user == "alice"
    assert cfg.password == "secret"
    assert cfg.base_url == "https://advantage.paperlessfbo.com"


def test_load_config_missing_creds_raises(monkeypatch):
    monkeypatch.delenv("PAPERLESS_USER", raising=False)
    monkeypatch.delenv("PAPERLESS_PASS", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_repr_does_not_leak_password(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    cfg = load_config()
    assert "secret" not in repr(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.config`

- [ ] **Step 3: Write minimal implementation**

`src/paperless141_mcp/config.py`:

```python
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://advantage.paperlessfbo.com"


class ConfigError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Config:
    user: str
    password: str = field(repr=False)  # never show in repr/logs
    base_url: str = DEFAULT_BASE_URL


def load_config() -> Config:
    load_dotenv()  # load .env if present; real env vars take precedence
    user = os.environ.get("PAPERLESS_USER")
    password = os.environ.get("PAPERLESS_PASS")
    if not user or not password:
        raise ConfigError(
            "PAPERLESS_USER and PAPERLESS_PASS must be set (see .env.example)."
        )
    base_url = os.environ.get("PAPERLESS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return Config(user=user, password=password, base_url=base_url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/config.py tests/test_config.py
git commit -m "feat: add config loading with credential validation"
```

---

## Task 3: SessionManager — Playwright login

**Files:**
- Create: `src/paperless141_mcp/session.py`
- Test: `tests/test_session.py`

> The login form lives at `mstr7p.aspx` and shows "User ID" and "Password" fields plus a submit
> control. We use **accessibility/label-based selectors** (robust to ASP.NET's generated `id`s).
> If recon shows the labels differ, adjust the selectors in Step 3 to match the captured fixture.

- [ ] **Step 1: Write the failing test**

`tests/test_session.py`:

```python
import pytest
from paperless141_mcp.session import SessionManager, LoginError
from paperless141_mcp.config import Config


def test_is_logged_out_detects_login_page():
    sm = SessionManager(Config(user="u", password="p"))
    login_html = '<form><input name="UserID"><input name="Password" type="password"></form>'
    assert sm.looks_like_login_page(login_html) is True


def test_is_logged_out_false_for_app_page():
    sm = SessionManager(Config(user="u", password="p"))
    app_html = '<div id="schedule">Welcome alice</div>'
    assert sm.looks_like_login_page(app_html) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.session`

- [ ] **Step 3: Write minimal implementation**

`src/paperless141_mcp/session.py`:

```python
from __future__ import annotations
import re
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .config import Config

LOGIN_URL_PATH = "/mstr7p.aspx"
# Heuristic: a password input + no app shell means we are on the login page.
_LOGIN_MARKER = re.compile(r'type=["\']password["\']', re.IGNORECASE)


class LoginError(Exception):
    """Raised when login fails (bad creds or changed form)."""


class SessionManager:
    def __init__(self, config: Config):
        self.config = config
        self._cookies: list[dict] = []

    def looks_like_login_page(self, html: str) -> bool:
        return bool(_LOGIN_MARKER.search(html))

    @property
    def cookies(self) -> list[dict]:
        return self._cookies

    async def login(self) -> list[dict]:
        """Log in with Playwright; store and return session cookies."""
        url = self.config.base_url + LOGIN_URL_PATH
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle")
                # Label-based selectors; adjust to fixture if recon shows different labels.
                await page.get_by_label("User ID").fill(self.config.user)
                await page.get_by_label("Password").fill(self.config.password)
                await page.get_by_role("button", name=re.compile("log ?in", re.I)).click()
                await page.wait_for_load_state("networkidle")
                html = await page.content()
                if self.looks_like_login_page(html):
                    raise LoginError("Still on login page after submit — check credentials.")
                self._cookies = await page.context.cookies()
                return self._cookies
            except PWTimeout as e:
                raise LoginError(f"Login timed out: {e}") from e
            finally:
                await browser.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session.py -v`
Expected: PASS (2 passed). (The pure-logic methods are tested; `login()` is exercised live during the recon checkpoint and the manual smoke test, not in CI.)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/session.py tests/test_session.py
git commit -m "feat: add Playwright SessionManager with login + page detection"
```

---

## Task 4: Recon command

**Files:**
- Create: `src/paperless141_mcp/recon.py`

> This task produces the tool that unblocks Phase B. After it's written, the **user runs it** to
> capture fixtures. It has no unit test (it is an interactive capture script); correctness is
> verified by inspecting the files it writes.

- [ ] **Step 1: Write `recon.py`**

`src/paperless141_mcp/recon.py`:

```python
"""One-shot reconnaissance: log in, save HTML of key pages to fixtures/ for parser development.

Usage:  python -m paperless141_mcp.recon
"""
from __future__ import annotations
import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright
from .config import load_config, Config
from .session import LOGIN_URL_PATH

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

# Candidate pages to capture after login. These are best-guess entry points; recon will also
# save the post-login landing page and a screenshot so we can discover the real nav links.
CANDIDATE_PAGES = {
    "landing": "",            # whatever you land on after login
}


def _scrub(html: str, cfg: Config) -> str:
    """Remove credentials from captured HTML before it touches disk."""
    out = html.replace(cfg.password, "***REDACTED***")
    out = out.replace(cfg.user, "***USER***")
    return out


async def run() -> None:
    cfg = load_config()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(cfg.base_url + LOGIN_URL_PATH, wait_until="networkidle")
        await page.get_by_label("User ID").fill(cfg.user)
        await page.get_by_label("Password").fill(cfg.password)
        await page.get_by_role("button", name=re.compile("log ?in", re.I)).click()
        await page.wait_for_load_state("networkidle")

        # Save the landing page + a screenshot to discover real navigation.
        (FIXTURE_DIR / "landing.html").write_text(_scrub(await page.content(), cfg))
        await page.screenshot(path=str(FIXTURE_DIR / "landing.png"), full_page=True)

        # Save every in-app link so we can map the navigation surface.
        links = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
        )
        (FIXTURE_DIR / "links.txt").write_text(
            "\n".join(f"{l['text']!r} -> {l['href']}" for l in links)
        )
        await browser.close()
    print(f"Recon complete. Wrote fixtures to {FIXTURE_DIR}")
    print("Next: open landing.png + links.txt, identify the schedule/lookup pages, "
          "then capture those URLs in a follow-up pass.")


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 2: Commit**

```bash
git add src/paperless141_mcp/recon.py
git commit -m "feat: add recon command to capture authenticated page fixtures"
```

---

## 🛑 RECON CHECKPOINT (user action)

Before Phase B, the user runs:

```bash
. .venv/bin/activate
# 1. Create .env with real credentials (copy from .env.example)
python -m paperless141_mcp.recon
```

Then we together inspect `tests/fixtures/landing.png`, `landing.html`, and `links.txt` to identify
the real schedule and lookup page URLs, and capture those pages (extend `CANDIDATE_PAGES` and re-run,
or navigate to them in the same script). **Phase B tasks are finalized against these real fixtures.**
If the login labels/selectors in Tasks 3–4 don't match what recon reveals, fix them first and re-run.

---

## Task 5: httpx client seeded with session cookies

**Files:**
- Create: `src/paperless141_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

`tests/test_client.py`:

```python
from paperless141_mcp.client import cookies_to_httpx


def test_cookies_to_httpx_maps_name_value():
    pw_cookies = [
        {"name": "ASP.NET_SessionId", "value": "abc", "domain": "advantage.paperlessfbo.com"},
        {"name": "auth", "value": "xyz", "domain": "advantage.paperlessfbo.com"},
    ]
    jar = cookies_to_httpx(pw_cookies)
    assert jar["ASP.NET_SessionId"] == "abc"
    assert jar["auth"] == "xyz"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.client`

- [ ] **Step 3: Write minimal implementation**

`src/paperless141_mcp/client.py`:

```python
from __future__ import annotations
import httpx
from .config import Config
from .session import SessionManager

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def cookies_to_httpx(pw_cookies: list[dict]) -> dict[str, str]:
    """Flatten Playwright cookies into a name->value dict for httpx."""
    return {c["name"]: c["value"] for c in pw_cookies}


class Client:
    """Fetches authenticated pages via httpx, re-logging-in on session expiry."""

    def __init__(self, config: Config, session: SessionManager):
        self.config = config
        self.session = session

    async def _ensure_session(self) -> None:
        if not self.session.cookies:
            await self.session.login()

    async def get(self, path: str) -> str:
        """GET an in-app page, returning HTML. Re-logs-in once if the session expired."""
        await self._ensure_session()
        url = self.config.base_url + path
        cookies = cookies_to_httpx(self.session.cookies)
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as hc:
            resp = await hc.get(url, cookies=cookies)
            html = resp.text
            if self.session.looks_like_login_page(html):
                # Session expired — re-login once and retry.
                await self.session.login()
                cookies = cookies_to_httpx(self.session.cookies)
                resp = await hc.get(url, cookies=cookies)
                html = resp.text
            return html
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_client.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/client.py tests/test_client.py
git commit -m "feat: add httpx client seeded with session cookies + re-login retry"
```

---

## Task 6: MCP server skeleton + `session_status` tool

**Files:**
- Create: `src/paperless141_mcp/tools.py`
- Create: `src/paperless141_mcp/server.py`

- [ ] **Step 1: Write `tools.py` with shared state + first tool**

`src/paperless141_mcp/tools.py`:

```python
from __future__ import annotations
from .config import load_config
from .session import SessionManager
from .client import Client

# Process-wide singletons (single user, single session — see spec "Out of scope").
_config = None
_session = None
_client = None


def get_client() -> Client:
    global _config, _session, _client
    if _client is None:
        _config = load_config()
        _session = SessionManager(_config)
        _client = Client(_config, _session)
    return _client


async def session_status() -> dict:
    """Report whether we currently hold a logged-in session."""
    client = get_client()
    return {
        "logged_in": bool(client.session.cookies),
        "base_url": client.config.base_url,
        "user": "***",  # never expose the real user id
    }
```

- [ ] **Step 2: Write `server.py`**

`src/paperless141_mcp/server.py`:

```python
"""FastMCP server entrypoint:  python -m paperless141_mcp.server"""
from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("paperless141")


@mcp.tool()
async def session_status() -> dict:
    """Check whether the server currently holds a logged-in Paperless141 session."""
    return await tools.session_status()


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the server imports and lists the tool**

Run:
```bash
python -c "from paperless141_mcp.server import mcp; print('ok')"
```
Expected: prints `ok` (no import errors).

- [ ] **Step 4: Commit**

```bash
git add src/paperless141_mcp/tools.py src/paperless141_mcp/server.py
git commit -m "feat: add FastMCP server skeleton with session_status tool"
```

---

## Task 7 (Phase B): Schedule parser + `get_schedule` tool — WORKED EXAMPLE

> **This is the template every data screen follows.** The HTML below is a *representative*
> ASP.NET schedule table. After recon, replace the fixture with the **real** captured HTML and
> adjust the selectors so the test asserts against actual values. The TDD shape stays identical.

**Files:**
- Create: `tests/fixtures/schedule_sample.html` (replaced by real capture)
- Create: `tests/parsers/test_schedule.py`
- Create: `src/paperless141_mcp/parsers/__init__.py`
- Create: `src/paperless141_mcp/parsers/schedule.py`
- Modify: `src/paperless141_mcp/tools.py`
- Modify: `src/paperless141_mcp/server.py`

- [ ] **Step 1: Add a representative fixture**

`tests/fixtures/schedule_sample.html`:

```html
<table id="grdSchedule">
  <tr><th>Date</th><th>Time</th><th>Aircraft</th><th>Instructor</th><th>Student</th><th>Status</th></tr>
  <tr><td>2026-06-16</td><td>09:00</td><td>N123AB</td><td>J. Smith</td><td>A. Jones</td><td>Booked</td></tr>
  <tr><td>2026-06-16</td><td>11:00</td><td>N123AB</td><td></td><td></td><td>Open</td></tr>
</table>
```

- [ ] **Step 2: Write the failing test**

`tests/parsers/test_schedule.py`:

```python
from pathlib import Path
from paperless141_mcp.parsers.schedule import parse_schedule

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "schedule_sample.html"


def test_parse_schedule_returns_rows():
    rows = parse_schedule(FIX.read_text())
    assert len(rows) == 2
    assert rows[0] == {
        "date": "2026-06-16", "time": "09:00", "aircraft": "N123AB",
        "instructor": "J. Smith", "student": "A. Jones", "status": "Booked",
    }


def test_parse_schedule_open_slot_has_empty_fields():
    rows = parse_schedule(FIX.read_text())
    assert rows[1]["status"] == "Open"
    assert rows[1]["instructor"] == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/parsers/test_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.parsers.schedule`

- [ ] **Step 4: Write minimal implementation**

`src/paperless141_mcp/parsers/__init__.py`:

```python
"""HTML -> JSON parsers, one per Paperless141 screen."""
```

`src/paperless141_mcp/parsers/schedule.py`:

```python
from __future__ import annotations
from bs4 import BeautifulSoup

# Column order in the schedule grid. Adjust to match the real captured table after recon.
_COLUMNS = ["date", "time", "aircraft", "instructor", "student", "status"]


def parse_schedule(html: str) -> list[dict]:
    """Parse the schedule grid HTML into a list of row dicts."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="grdSchedule")
    if table is None:
        return []
    rows: list[dict] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")  # skip header rows (they use <th>)
        if not cells:
            continue
        values = [c.get_text(strip=True) for c in cells]
        rows.append(dict(zip(_COLUMNS, values)))
    return rows
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/parsers/test_schedule.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Wire the `get_schedule` tool**

Add to `src/paperless141_mcp/tools.py`:

```python
from .parsers.schedule import parse_schedule

# Set to the real schedule page path discovered during recon.
SCHEDULE_PATH = "/schedule.aspx"  # placeholder — replace with the captured URL path


async def get_schedule(start_date: str, end_date: str) -> list[dict]:
    """Fetch and parse schedule rows. Date filtering is applied client-side for now."""
    client = get_client()
    html = await client.get(SCHEDULE_PATH)
    rows = parse_schedule(html)
    return [r for r in rows if start_date <= r.get("date", "") <= end_date]
```

Add to `src/paperless141_mcp/server.py`:

```python
@mcp.tool()
async def get_schedule(start_date: str, end_date: str) -> list[dict]:
    """Read schedule entries between start_date and end_date (YYYY-MM-DD, inclusive)."""
    return await tools.get_schedule(start_date, end_date)
```

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/paperless141_mcp/parsers tests/parsers tests/fixtures/schedule_sample.html \
        src/paperless141_mcp/tools.py src/paperless141_mcp/server.py
git commit -m "feat: add schedule parser and get_schedule tool"
```

---

## Task 8+ (Phase B): Remaining screens — repeat Task 7's pattern

For each additional screen identified during recon (e.g. availability, student lookup, aircraft
status), create one task that repeats Task 7 exactly:

1. Save the real captured HTML as `tests/fixtures/<screen>.html`.
2. Write `tests/parsers/test_<screen>.py` asserting the real values you see in the fixture.
3. Run it red.
4. Implement `src/paperless141_mcp/parsers/<screen>.py` (`parse_<screen>(html) -> list[dict]`).
5. Run it green.
6. Add `<screen>` function in `tools.py` + `@mcp.tool()` wrapper in `server.py`.
7. Run `pytest -v`; commit.

Concrete target tools from the spec: `check_availability(resource, date)`,
`lookup(query)` / `get_student(id_or_name)`. Finalize their exact arguments and return shapes
against the captured fixtures — do not invent fields the real pages don't show.

---

## Task 9: Wire into Claude as an MCP server + live smoke test

**Files:**
- Create: `README.md` (run/config instructions)

- [ ] **Step 1: Document the MCP client config**

Add to `README.md` a config block for the user's MCP client:

```json
{
  "mcpServers": {
    "paperless141": {
      "command": "/abs/path/to/.venv/bin/python",
      "args": ["-m", "paperless141_mcp.server"],
      "env": {
        "PAPERLESS_USER": "your_user_id",
        "PAPERLESS_PASS": "your_password"
      }
    }
  }
}
```

- [ ] **Step 2: Manual smoke test (deliberate, not CI)**

Run:
```bash
. .venv/bin/activate
python -c "import asyncio; from paperless141_mcp import tools; \
print(asyncio.run(tools.session_status()))"
```
Expected: `{'logged_in': False, ...}` then, after a tool call that logs in, `logged_in: True`.
Then call `get_schedule` for a known date range and confirm real rows come back.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add MCP client config and smoke-test instructions"
```

---

## Self-review notes

- **Spec coverage:** read-only goal ✓ (no write tools anywhere); schedule/availability ✓ (Task 7, Task 8+); lookup ✓ (Task 8+); hybrid Playwright+httpx ✓ (Tasks 3,5); recon-first ✓ (Task 4 + checkpoint); credentials via env, never logged ✓ (Tasks 2,6); error handling re-login ✓ (Task 5); offline fixture testing ✓ (Tasks 7,8+).
- **Known deferred specifics (by necessity, not placeholder):** exact login selectors, real page URL paths (`SCHEDULE_PATH`), and real column/field layouts are resolved at the recon checkpoint against captured HTML. Every such spot is flagged inline with how to finalize it.
- **Type consistency:** `parse_<screen>(html) -> list[dict]`, `Client.get(path) -> str`, `SessionManager.login() -> list[dict]`, `cookies_to_httpx(list) -> dict` used consistently across tasks.
