from __future__ import annotations
import re
from bs4 import BeautifulSoup

_SCHEDNUM_URL = re.compile(r"schednum=(\d+)", re.IGNORECASE)
_SCHEDNUM_TEXT = re.compile(r"Schedule#\s*(\d+)", re.IGNORECASE)


def parse_booking_result(html: str) -> dict:
    """Extract the schedule number from a reservation-detail page (mstr7a.aspx).

    Returns {"ok": bool, "schedule_number": str | None}. ok is True when a schedule
    number was found, which is the signal a booking exists.
    """
    num = None
    m = _SCHEDNUM_TEXT.search(html)
    if m:
        num = m.group(1)
    else:
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", action=_SCHEDNUM_URL)
        if form:
            num = _SCHEDNUM_URL.search(form.get("action", "")).group(1)
    return {"ok": num is not None, "schedule_number": num}
