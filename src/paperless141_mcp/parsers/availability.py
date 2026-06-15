"""Parser for the aircraft scheduler time-grid (mstr7p.aspx, GridView2).

The grid is a matrix: columns are aircraft (resources), rows are 30-minute time
slots. The first three rows are headers (Reg#, >Type, >Loc). Each data cell encodes
one of three states:

  - free        : empty cell with an active __doPostBack link (white, bookable)
  - unavailable : a literal "*" (red, disabled) — closed/blocked
  - booked      : a coloured, disabled cell whose text labels the booking
                  (e.g. "Pilot Doe, Jane", "GROUND", "MAINT", "-OFF-")
"""
from __future__ import annotations
from bs4 import BeautifulSoup

TABLE_ID = "ctl00_ContentPlaceHolder1_GridView2"


def _classify(cell) -> dict:
    text = cell.get_text(" ", strip=True)
    link = cell.find("a")
    # A bookable (free) slot is an empty cell whose anchor fires a real postback.
    active_link = bool(link and "__doPostBack" in (link.get("href") or ""))
    if text == "*":
        return {"status": "unavailable"}
    if text == "":
        return {"status": "free"} if active_link else {"status": "unavailable"}
    label = text
    if label.startswith("Pilot "):  # drop the hidden "Pilot" prefix span
        label = label[len("Pilot "):].strip()
    return {"status": "booked", "label": label}


def parse_availability(html: str) -> dict:
    """Parse the scheduler grid into resources + time-slotted statuses.

    Returns::

        {
          "resources": [{"reg": "N111AB", "type": "C152", "location": "KPAO"}, ...],
          "rows": [
            {"time": "07:00", "cells": {"N111AB": {"status": "free"}, ...}},
            ...
          ],
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=TABLE_ID)
    if table is None:
        return {"resources": [], "rows": []}
    # Only rows belonging directly to this table (allowing a <tbody>), not rows nested
    # inside cell-level tables.
    trs = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
    if len(trs) < 4:
        return {"resources": [], "rows": []}

    def texts(tr):
        return [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]

    regs, types, locs = texts(trs[0]), texts(trs[1]), texts(trs[2])
    resources = []
    for ci in range(1, len(regs)):  # column 0 is the row label ("Reg#")
        resources.append(
            {
                "reg": regs[ci],
                "type": types[ci] if ci < len(types) else "",
                "location": locs[ci] if ci < len(locs) else "",
            }
        )

    rows = []
    for tr in trs[3:]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        time = cells[0].get_text(strip=True)
        if not time:
            continue
        cell_map = {}
        for ci in range(1, len(cells)):
            if ci - 1 >= len(resources):
                break
            cell_map[resources[ci - 1]["reg"]] = _classify(cells[ci])
        rows.append({"time": time, "cells": cell_map})
    return {"resources": resources, "rows": rows}


def free_slots_by_resource(parsed: dict) -> list[dict]:
    """Compact view: for each resource, the list of times where it is free.

    Returns a list of {reg, type, location, free_times: [...]} — far smaller than
    the full grid and directly answers "what is available when".
    """
    out = []
    for res in parsed["resources"]:
        reg = res["reg"]
        free = [
            row["time"]
            for row in parsed["rows"]
            if row["cells"].get(reg, {}).get("status") == "free"
        ]
        out.append({**res, "free_times": free})
    return out
