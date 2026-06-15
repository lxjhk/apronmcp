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
