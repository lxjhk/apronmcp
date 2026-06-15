import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from paperless141_mcp.client import cookies_to_httpx, Client
from paperless141_mcp.config import Config
from paperless141_mcp.session import SessionManager


def test_cookies_to_httpx_maps_name_value():
    pw_cookies = [
        {"name": "ASP.NET_SessionId", "value": "abc", "domain": "advantage.paperlessfbo.com"},
        {"name": "auth", "value": "xyz", "domain": "advantage.paperlessfbo.com"},
    ]
    jar = cookies_to_httpx(pw_cookies)
    assert jar["ASP.NET_SessionId"] == "abc"
    assert jar["auth"] == "xyz"


# ---------------------------------------------------------------------------
# Optional: test the re-login-on-expiry retry path of Client.get
# ---------------------------------------------------------------------------

LOGIN_HTML = '<input type="password" name="pass" />'
APP_HTML = "<html><body>Welcome to the app</body></html>"


class FakeSessionManager:
    """Minimal stand-in for SessionManager — no browser, no network."""

    def __init__(self):
        self._cookies: list[dict] = [
            {"name": "session", "value": "stale", "domain": "example.com"}
        ]
        self.login_call_count = 0

    @property
    def cookies(self) -> list[dict]:
        return self._cookies

    async def login(self) -> list[dict]:
        self.login_call_count += 1
        self._cookies = [{"name": "session", "value": "fresh", "domain": "example.com"}]
        return self._cookies

    def looks_like_login_page(self, html: str) -> bool:
        # Delegate to the real regex logic from the real class
        return SessionManager.looks_like_login_page(self, html)


def _make_fake_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_client_get_retries_on_session_expiry():
    """Client.get should re-login and retry once when the first response looks like the login page."""
    config = Config(user="u", password="p", base_url="https://example.com")
    session = FakeSessionManager()
    client = Client(config, session)

    # First GET returns a login page (stale cookie rejected by server).
    # Second GET (after re-login) returns the real app page.
    get_responses = [
        _make_fake_response(LOGIN_HTML),
        _make_fake_response(APP_HTML),
    ]

    mock_get = AsyncMock(side_effect=get_responses)

    # Build a mock httpx.AsyncClient that acts as an async context manager.
    mock_hc = MagicMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)
    mock_hc.get = mock_get

    with patch("paperless141_mcp.client.httpx.AsyncClient", return_value=mock_hc):
        html = await client.get("/some/page")

    assert html == APP_HTML
    assert session.login_call_count == 1, "Should have re-logged-in exactly once"
    assert mock_get.call_count == 2, "Should have made exactly two GET requests"

    # Verify the second request used the fresh cookie.
    _, second_call_kwargs = mock_get.call_args_list[1]
    assert second_call_kwargs.get("cookies", {}).get("session") == "fresh"
