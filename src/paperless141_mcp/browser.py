"""Persistent Playwright browser session for postback-navigated Paperless141 pages.

Paperless141 navigates entirely via ASP.NET postbacks (menu buttons run
``SetDestination(...)`` then submit the form), so a stateless httpx GET cannot reach
the inner pages. This session logs in once, keeps a single browser/page alive, and
re-uses it for every navigation. Calls are serialised with a lock because one page
cannot service two postback navigations at once.
"""
from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright

from .config import Config
from .session import (
    LOGIN_URL_PATH,
    LoginError,
    submit_login,
    looks_like_login_page,
)


class BrowserSession:
    """A logged-in, reusable Playwright page for the user's own Paperless141 account."""

    def __init__(self, config: Config):
        self.config = config
        self._pw = None
        self._browser = None
        self._page = None
        self._landing_url: str | None = None
        self._lock = asyncio.Lock()

    @property
    def logged_in(self) -> bool:
        return self._page is not None and self._landing_url is not None

    async def start(self) -> None:
        """Launch the browser and log in. Idempotent — a no-op once logged in."""
        if self.logged_in:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        try:
            await self._login()
        except Exception:
            # Don't leak the Chromium process / Playwright driver on a failed login.
            await self.close()
            raise

    async def _login(self) -> None:
        await self._page.goto(
            self.config.base_url + LOGIN_URL_PATH, wait_until="networkidle"
        )
        await submit_login(self._page, self.config)
        html = await self._page.content()
        if looks_like_login_page(html):
            raise LoginError("Login failed — still on the login page (check credentials).")
        self._landing_url = self._page.url

    async def open_menu(self, button_selector: str) -> str:
        """Navigate to a menu destination by clicking its postback button; return HTML.

        Re-logs-in once if the session has expired between calls.
        """
        async with self._lock:
            await self.start()
            html = await self._navigate(button_selector)
            if looks_like_login_page(html):
                # Session expired — re-login and retry once.
                await self._login()
                html = await self._navigate(button_selector)
            return html

    async def _navigate(self, button_selector: str) -> str:
        await self._page.goto(self._landing_url, wait_until="networkidle")
        await self._page.click(button_selector)
        await self._page.wait_for_load_state("networkidle")
        return await self._page.content()

    async def close(self) -> None:
        """Tear down the browser and Playwright. Safe to call multiple times."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
        self._page = None
        self._landing_url = None
