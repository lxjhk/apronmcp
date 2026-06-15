"""Shared parsing helpers for Paperless141 ASP.NET GridView tables."""
from __future__ import annotations
from typing import Callable, Optional
from bs4 import BeautifulSoup


def _text(cell) -> str:
    return cell.get_text(" ", strip=True)


def parse_labeled_grid(
    html: str,
    table_id: str,
    label_to_key: dict[str, str],
    row_valid: Optional[Callable[[dict], bool]] = None,
) -> list[dict]:
    """Parse an ASP.NET GridView into a list of row dicts, keyed by header label.

    The header row is located by matching the visible ``<th>``/``<td>`` text against
    the keys of ``label_to_key`` (robust to extra control columns and to ASP.NET pager
    rows that appear above/below the data). Columns are mapped by the header position,
    so reordering columns does not break the parser.

    ``row_valid`` is an optional predicate applied to each candidate record; rows for
    which it returns False (e.g. pager rows that survive header detection) are dropped.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=table_id)
    if table is None:
        return []
    # Only rows belonging directly to this table (allowing a <tbody>); excludes rows
    # inside a nested table such as an ASP.NET pager, which would otherwise look like data.
    rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]

    col_index: dict[str, int] = {}
    header_idx: Optional[int] = None
    for i, tr in enumerate(rows):
        cells = tr.find_all(["th", "td"], recursive=False)
        found: dict[str, int] = {}
        for ci, cell in enumerate(cells):
            label = _text(cell)
            if label in label_to_key:
                found[label_to_key[label]] = ci
        # Accept the first row that carries a clear majority of the expected labels.
        if len(found) >= max(2, (len(label_to_key) + 1) // 2):
            header_idx = i
            col_index = found
            break
    if header_idx is None:
        return []

    max_idx = max(col_index.values())
    out: list[dict] = []
    for tr in rows[header_idx + 1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) <= max_idx:
            continue
        rec = {key: _text(cells[ci]) for key, ci in col_index.items()}
        if row_valid is not None and not row_valid(rec):
            continue
        if not any(rec.values()):
            continue
        out.append(rec)
    return out
