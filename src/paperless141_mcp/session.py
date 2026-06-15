from __future__ import annotations
import re
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from .config import Config

LOGIN_URL_PATH = "/mstr7p.aspx"
# Heuristic: a password input or the "Please Log In" banner means we are on the login page.
_LOGIN_MARKER = re.compile(r'type=["\']password["\']', re.IGNORECASE)


def looks_like_login_page(html: str) -> bool:
    """True if `html` is the Paperless141 login page (vs. an authenticated app page)."""
    return bool(_LOGIN_MARKER.search(html)) or "Please Log In" in html

# Selectors confirmed from the real login page (mstr7p.aspx, classic ASP.NET).
# The visible "User ID:" / "Password:" labels are NOT wired with <label for>, so
# label-based selectors do not work — we target the input ids directly.
_USER_SELECTOR = "#txtUserName"
_PASS_SELECTOR = "#txtPassword"
_SUBMIT_SELECTOR = "#ButtLogin"   # the green "Log In" submit button
# NOTE: #ImageButton1 is a "show password" toggle, NOT login — do not click it.
_COOKIE_ACCEPT_SELECTOR = "#BtnAgree"  # cookie-consent "Accept" banner, shown on fresh sessions


class LoginError(Exception):
    """Raised when login fails (bad creds or changed form)."""


async def submit_login(page, config: Config) -> None:
    """Fill and submit the Paperless141 login form on an already-loaded login `page`.

    Shared by SessionManager.login() and the recon tool so the fragile ASP.NET
    selectors live in exactly one place. Dismisses the cookie-consent banner first
    if it is present (best-effort), then fills credentials and clicks submit.
    """
    # Best-effort cookie consent — ignore if the banner is absent.
    try:
        accept = page.locator(_COOKIE_ACCEPT_SELECTOR)
        if await accept.count() and await accept.is_visible():
            await accept.click()
            await page.wait_for_load_state("networkidle")
    except Exception:  # noqa: BLE001 — consent is optional; never block login on it
        pass
    await page.locator(_USER_SELECTOR).fill(config.user)
    await page.locator(_PASS_SELECTOR).fill(config.password)
    await page.locator(_SUBMIT_SELECTOR).click()
    await page.wait_for_load_state("networkidle")


class SessionManager:
    def __init__(self, config: Config):
        self.config = config
        self._cookies: list[dict] = []

    def looks_like_login_page(self, html: str) -> bool:
        return looks_like_login_page(html)

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
                await submit_login(page, self.config)
                html = await page.content()
                if self.looks_like_login_page(html):
                    raise LoginError("Still on login page after submit — check credentials.")
                self._cookies = await page.context.cookies()
                return self._cookies
            except PWTimeout as e:
                raise LoginError(f"Login timed out: {e}") from e
            finally:
                await browser.close()
