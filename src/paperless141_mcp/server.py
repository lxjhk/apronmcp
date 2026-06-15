"""FastMCP server entrypoint:  python -m paperless141_mcp.server"""
from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("paperless141")


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
async def get_aircraft_availability(only_available: bool = True) -> dict:
    """Show aircraft availability from the scheduler board (current/today view).

    Returns each aircraft with the time slots where it is free. Set only_available
    to False to include fully-booked aircraft as well.
    """
    return await tools.get_aircraft_availability(only_available)


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
