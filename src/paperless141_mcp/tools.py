from __future__ import annotations
from datetime import datetime
from .config import load_config, Config
from .browser import BrowserSession, BookingError
from .writes import (
    validate_reservation_params,
    format_create_preview,
    format_cancel_preview,
    open_slots_from_board,
)
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


async def find_open_slots(date: str, type_or_tail: str | None = None) -> list[dict]:
    """Return free (reg, type, location, time) slots for a date; optional type/tail filter."""
    date = _validate_date(date)
    html = await get_browser().open_scheduler(_BTN_SCHEDULER, date)
    return open_slots_from_board(parse_availability(html), type_or_tail)


async def create_reservation(
    date: str,
    start: str,
    end: str,
    tail: str,
    cfi: str | None = None,
    category: str | None = None,
    note: str | None = None,
    confirm: bool = False,
) -> dict:
    """Create a reservation. With confirm=False (default), returns a preview and writes nothing.

    With confirm=True, books the slot and reports the new schedule_number. Success is
    confirmed by re-reading the schedule — never assumed.
    """
    params = validate_reservation_params(date, start, end, tail)
    params.update({"cfi": cfi, "category": category, "note": note})
    if not confirm:
        return format_create_preview(params)
    before = {r["schedule_number"] for r in await get_my_schedule()}
    try:
        await get_browser().book_slot(
            date=params["date"], start=params["start"], end=params["end"],
            tail=params["tail"], cfi=cfi, category=category, note=note,
        )
    except BookingError as e:
        return {"action": "create_reservation", "confirmed": True, "ok": False, "error": str(e)}
    new = [r for r in await get_my_schedule() if r["schedule_number"] not in before]
    if not new:
        return {
            "action": "create_reservation", "confirmed": True, "ok": False,
            "error": ("booking was not created — the slot may be taken, outside operating "
                      "hours, or the aircraft may require a checkout you don't have"),
        }
    return {
        "action": "create_reservation", "confirmed": True, "ok": True,
        "schedule_number": new[0]["schedule_number"], "reservation": new[0],
    }


async def cancel_reservation(
    schedule_number: str, confirm: bool = False, reason: str = "Schedule Error"
) -> dict:
    """Cancel one reservation by schedule_number. With confirm=False (default), previews only.

    Only ever acts on the single given schedule_number. Success is confirmed by re-reading
    the schedule.
    """
    schedule_number = str(schedule_number)
    match = next(
        (r for r in await get_my_schedule() if r["schedule_number"] == schedule_number),
        None,
    )
    if match is None:
        return {"action": "cancel_reservation", "confirmed": False,
                "error": f"no reservation #{schedule_number} found in your schedule"}
    if not confirm:
        return format_cancel_preview(match)
    await get_browser().cancel_reservation_flow(schedule_number, reason=reason)
    gone = all(r["schedule_number"] != schedule_number for r in await get_my_schedule())
    return {"action": "cancel_reservation", "confirmed": True,
            "cancelled": gone, "schedule_number": schedule_number}
