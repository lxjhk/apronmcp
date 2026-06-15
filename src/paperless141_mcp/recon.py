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
