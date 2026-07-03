"""Parser for the "My Account" page (mstr1.aspx, GridView3)."""
from __future__ import annotations
import re
from ._common import parse_labeled_grid

TABLE_ID = "ctl00_ContentPlaceHolder1_GridView3"

_LABELS = {
    "Date": "date",
    "Activity Type": "activity_type",
    "Amount": "amount",
    "Tax": "tax",
    "Comment": "comment",
    "Account Balance": "balance",
}

_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def parse_account(html: str) -> list[dict]:
    """Parse account transactions into a list of dicts.

    Each dict has: date, activity_type, amount, tax, comment, balance.
    ASP.NET pager rows (e.g. "1 2 3 4 5 6") are filtered out by requiring the
    date column to look like a real MM/DD/YYYY date.
    """
    return parse_labeled_grid(
        html,
        TABLE_ID,
        _LABELS,
        row_valid=lambda r: bool(_DATE.match(r.get("date", ""))),
    )
