"""One-shot reconnaissance: log in, save HTML of key pages to fixtures/ for parser development.

Usage:  python -m paperless141_mcp.recon
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from .config import load_config, Config
from .session import LOGIN_URL_PATH, submit_login

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

        # 4. Save every in-app link so we can map the navigation surface.
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
