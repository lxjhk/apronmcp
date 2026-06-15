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
