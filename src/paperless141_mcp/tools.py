from __future__ import annotations
from datetime import datetime
from .config import load_config, Config
from .browser import BrowserSession
from .parsers.my_schedule import parse_my_schedule
from .parsers.account import parse_account
from .parsers.availability import (
    parse_availability,
    free_slots_by_resource,
    parse_board_date,
)


class DateFormatError(ValueError):
    """Raised when a date argument is not in YYYY-MM-DD format."""


def _validate_date(date: str) -> str:
    """Validate a YYYY-MM-DD date string, returning it normalized; raise on bad input."""
    try:
        return datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        raise DateFormatError(f"date must be YYYY-MM-DD, got {date!r}")

# Process-wide singletons (single user, single session — see spec "Out of scope").
_config: Config | None = None
_browser: BrowserSession | None = None

# Menu postback buttons on the landing page (mstrI.aspx), confirmed via recon.
_BTN_MY_SCHEDULE = "#ctl00_BtnSchedMy"
_BTN_ACCOUNT = "#ctl00_BtnAccount"
_BTN_SCHEDULER = "#ctl00_BtnSched"


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_browser() -> BrowserSession:
    """Persistent Playwright session used for postback-navigated pages."""
    global _browser
    if _browser is None:
        _browser = BrowserSession(_get_config())
    return _browser


async def session_status() -> dict:
    """Report whether we currently hold a logged-in browser session."""
    return {
        "logged_in": get_browser().logged_in,
        "base_url": _get_config().base_url,
        "user": "***",  # never expose the real user id
    }


async def get_my_schedule() -> list[dict]:
    """Return the user's own reservations (schedule_number, resource, start, end, pilot, cfi, note)."""
    html = await get_browser().open_menu(_BTN_MY_SCHEDULE)
    return parse_my_schedule(html)


async def get_account(limit: int = 50) -> list[dict]:
    """Return recent account transactions (date, activity_type, amount, tax, comment, balance).

    Only the first page of transactions is read; ``limit`` caps how many are returned.
    """
    html = await get_browser().open_menu(_BTN_ACCOUNT)
    rows = parse_account(html)
    return rows[:limit] if limit > 0 else rows


async def get_aircraft_availability(
    date: str | None = None, only_available: bool = True
) -> dict:
    """Return aircraft availability from the scheduler board for a given date.

    ``date`` is YYYY-MM-DD; when omitted the board's default (today) is used. Each
    resource lists the time slots where it is free. When ``only_available`` is True
    (default) resources with no free slots are omitted to keep the response compact.
    """
    if date is not None:
        date = _validate_date(date)
    html = await get_browser().open_scheduler(_BTN_SCHEDULER, date)
    parsed = parse_availability(html)
    resources = free_slots_by_resource(parsed)
    if only_available:
        resources = [r for r in resources if r["free_times"]]
    return {
        "date": parse_board_date(html),
        "resource_count": len(parsed["resources"]),
        "resources": resources,
    }
