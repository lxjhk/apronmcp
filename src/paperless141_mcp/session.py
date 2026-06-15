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
