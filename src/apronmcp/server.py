"""FastMCP server entrypoint:  python -m apronmcp.server"""
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from . import tools


@asynccontextmanager
async def _lifespan(_app):
    """Close the persistent browser session when the server shuts down."""
    try:
        yield
    finally:
        await tools.get_browser().close()


mcp = FastMCP("apronmcp", lifespan=_lifespan)


@mcp.tool()
async def session_status() -> dict:
    """Check whether the server currently holds a logged-in Paperless141 session."""
    return await tools.session_status()


@mcp.tool()
async def get_my_schedule() -> list[dict]:
    """List the user's own Paperless141 reservations (bookings).

    Each item: schedule_number, resource (aircraft), start, end, pilot, cfi, note.
    """
    return await tools.get_my_schedule()


@mcp.tool()
async def get_account(limit: int = 50) -> list[dict]:
    """List recent account transactions (billing / flight charges).

    Each item: date, activity_type (DEBIT/CREDIT), amount, tax, comment, balance.
    Returns the first page of transactions, capped at `limit`.
    """
    return await tools.get_account(limit)


@mcp.tool()
async def get_aircraft_availability(
    date: str | None = None, only_available: bool = True
) -> dict:
    """Show aircraft availability from the scheduler board for a date.

    date: YYYY-MM-DD (defaults to today if omitted). Returns each aircraft with the
    time slots where it is free. Set only_available to False to include fully-booked
    aircraft as well. The returned "date" field reports the board date actually shown.
    """
    return await tools.get_aircraft_availability(date, only_available)


@mcp.tool()
async def find_open_slots(date: str, type_or_tail: str | None = None) -> list[dict]:
    """Find free aircraft time slots on a date (YYYY-MM-DD), optionally filtered by type or tail.

    Use this to turn a vague request into concrete bookable options before create_reservation.
    """
    return await tools.find_open_slots(date, type_or_tail)


@mcp.tool()
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
    """Create a reservation. Defaults to a PREVIEW (confirm=False, writes nothing).

    Set confirm=True to actually book. date=YYYY-MM-DD, start/end=HH:MM (24h), tail=aircraft
    (e.g. "15MJ"), cfi="SOLO" or an instructor, category e.g. "Flight". Always preview and
    confirm the details with the user before calling with confirm=True.
    """
    return await tools.create_reservation(
        date, start, end, tail, cfi, category, note, confirm
    )


@mcp.tool()
async def cancel_reservation(
    schedule_number: str, confirm: bool = False, reason: str = "Schedule Error"
) -> dict:
    """Cancel ONE reservation by its schedule_number. Defaults to a PREVIEW (confirm=False).

    Set confirm=True to actually cancel. Only ever affects the single given schedule_number.
    Confirm the specific reservation with the user before calling with confirm=True.
    """
    return await tools.cancel_reservation(schedule_number, confirm, reason)


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
