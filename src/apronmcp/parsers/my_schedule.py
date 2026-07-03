"""Parser for the "My Schedules" page (mstr8.aspx, GridView1)."""
from __future__ import annotations
import re
from ._common import parse_labeled_grid

TABLE_ID = "ctl00_ContentPlaceHolder1_GridView1"

_LABELS = {
    "Schedule#": "schedule_number",
    "Resource": "resource",
    "Start": "start",
    "End": "end",
    "Pilot": "pilot",
    "CFI": "cfi",
    "Note": "note",
}

_SCHED_NUM = re.compile(r"^\d+$")


def parse_my_schedule(html: str) -> list[dict]:
    """Parse the user's own reservations into a list of dicts.

    Each dict has: schedule_number, resource, start, end, pilot, cfi, note.
    """
    return parse_labeled_grid(
        html,
        TABLE_ID,
        _LABELS,
        row_valid=lambda r: bool(_SCHED_NUM.match(r.get("schedule_number", ""))),
    )
