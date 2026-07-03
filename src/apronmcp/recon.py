"""One-shot reconnaissance: log in, save HTML of key pages to fixtures/ for parser development.

Usage:  python -m apronmcp.recon
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from .config import load_config, Config
from .session import LOGIN_URL_PATH, submit_login

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

# Priority menu destinations to drill into after login, discovered from the landing page.
# Each entry is (fixture_name, CSS selector for the postback button on the landing page).
DRILL_TARGETS = [
    ("scheduler", "#ctl00_BtnSched"),     # Schedules — resource (aircraft) schedules
    ("my_schedule", "#ctl00_BtnSchedMy"),  # My Schedules — your bookings
    ("instructors", "#ctl00_BtnSchedI"),   # Instructors — instructor schedules
    ("account", "#ctl00_BtnAccount"),      # My Account — your finances & flights
]


def _scrub(html: str, cfg: Config) -> str:
    """Remove credentials from captured HTML before it touches disk."""
    out = html.replace(cfg.password, "***REDACTED***")
    out = out.replace(cfg.user, "***USER***")
    return out


async def _dump(page, name: str, cfg: Config) -> None:
    """Save the current page's HTML + a full-page screenshot to fixtures/."""
    (FIXTURE_DIR / f"{name}.html").write_text(_scrub(await page.content(), cfg))
    await page.screenshot(path=str(FIXTURE_DIR / f"{name}.png"), full_page=True)


async def run() -> None:
    cfg = load_config()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Always capture the login page FIRST — even if our login selectors are
        #    wrong, this lets us read the real field labels and fix them.
        await page.goto(cfg.base_url + LOGIN_URL_PATH, wait_until="networkidle")
        await _dump(page, "login", cfg)

        # 2. Attempt login. If a selector guess is wrong this raises, but the login
        #    capture above is already on disk so the run is still useful.
        try:
            await submit_login(page, cfg)
        except Exception as e:  # noqa: BLE001 — recon is diagnostic; report and stop cleanly
            await browser.close()
            print(f"Saved login page to {FIXTURE_DIR}/login.html + login.png")
            print(f"Login step failed (likely a selector mismatch): {e!r}")
            print("Open login.html and tell Claude the real field labels/ids so the "
                  "selectors can be corrected, then re-run.")
            return

        # 3. Capture the post-login landing page + screenshot.
        await _dump(page, "landing", cfg)
        landing_url = page.url
        landing_html = await page.content()

        # 4. Save every in-app link so we can map the navigation surface.
        links = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
        )
        (FIXTURE_DIR / "links.txt").write_text(
            f"# landing URL: {landing_url}\n"
            + "\n".join(f"{l['text']!r} -> {l['href']}" for l in links)
        )

        # 5. Drill into the priority menu destinations and capture each. The menu uses
        #    ASP.NET postback buttons (SetDestination + submit), so we re-load the landing
        #    page and click the button for each target to get a fresh navigation.
        captured = []
        for name, selector in DRILL_TARGETS:
            try:
                await page.goto(landing_url, wait_until="networkidle")
                await page.click(selector)
                await page.wait_for_load_state("networkidle")
                await _dump(page, name, cfg)
                captured.append((name, page.url))
            except Exception as e:  # noqa: BLE001 — diagnostic; keep going on the rest
                captured.append((name, f"FAILED: {e!r}"))

        await browser.close()

    # Sanity check: did we actually leave the login page? The login form keeps the
    # password input (#txtPassword) and a "Please Log In" marker; a real app page won't.
    still_on_login = "txtPassword" in landing_html or "Please Log In" in landing_html
    print(f"Recon wrote fixtures to {FIXTURE_DIR}")
    print(f"Landing URL after login: {landing_url}")
    if still_on_login:
        print("WARNING: landing page still looks like the LOGIN page — login did not "
              "succeed. Check credentials, or the submit selector may still be wrong. "
              "Inspect landing.html / landing.png.")
    else:
        print("Login succeeded.")
        print("Drilled menu destinations:")
        for name, result in captured:
            print(f"  {name:14s} -> {result}")


if __name__ == "__main__":
    asyncio.run(run())
