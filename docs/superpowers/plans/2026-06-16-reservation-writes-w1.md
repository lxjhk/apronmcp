# Reservation Writes — Phase W1 (Discovery + Create + Cancel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `find_open_slots`, `create_reservation`, and `cancel_reservation` MCP tools (preview-then-confirm) to the paperless141-mcp server, validated by a real create→cancel round-trip on a throwaway far-future slot.

**Architecture:** Playwright UI automation drives the live "Make/Modify Schedules" flow (ViewState-heavy, stateful). Pure logic (validation, preview formatting, slot ranking, confirmation parsing) is separated from browser I/O so it is unit-testable offline; the browser flow is validated live on a throwaway slot.

**Tech Stack:** Python 3.11+, Playwright, BeautifulSoup, pytest. Existing modules: `config.py`, `session.py`, `browser.py` (`BrowserSession`, `open_scheduler`), `parsers/availability.py`, `tools.py`, `server.py`.

**Design spec:** `docs/superpowers/specs/2026-06-16-reservation-write-capabilities-design.md`

---

## Phase ordering & the discovery checkpoint

- **Group 1 (Tasks 1–4):** fully specifiable now — validation, preview formatting, slot ranking, confirmation parser. Offline TDD.
- **🛑 DISCOVERY CHECKPOINT (Task 5):** a live, guided capture on a throwaway far-future slot that pins down the exact create + cancel click-path and field selectors. **Tasks 6–9 are finalized against its output.** Do not write the browser driver before this.
- **Group 2 (Tasks 6–9):** browser write-flow driver, the two write tools, and the live round-trip validation.

**Safety rules that apply to EVERY task touching the live site:**
- Only ever act on a **throwaway far-future slot** (e.g. `2026-09-15`) or a `schedule_number` created by this test. NEVER the user's real reservations (#688447, #688368, #688279).
- Write tools default to `confirm=False` (preview only). A live write happens only with `confirm=True`.
- After any test write, verify via `get_my_schedule` and clean up with cancel.

---

## File Structure

```
src/paperless141_mcp/
    writes.py                 # NEW: validation, preview formatting, slot ranking (pure logic)
    browser.py                # MODIFY: add make/modify + booking + cancel flow methods
    tools.py                  # MODIFY: find_open_slots, create_reservation, cancel_reservation
    server.py                 # MODIFY: register the 3 new tools
    parsers/
        confirmation.py       # NEW: parse mstr7a.aspx booking result (schedule_number, success)
tests/
    test_writes.py            # NEW: validation, preview, ranking
    parsers/test_confirmation.py   # NEW
    fixtures/
        booking_confirmation_sample.html  # NEW synthetic fixture (committed)
docs/superpowers/discovery/
    2026-06-16-booking-flow.md  # NEW: discovery output (selectors + click-path), written in Task 5
```

---

## Task 1: Parameter validation (`writes.py`)

**Files:**
- Create: `src/paperless141_mcp/writes.py`
- Test: `tests/test_writes.py`

- [ ] **Step 1: Write the failing test**

`tests/test_writes.py`:

```python
import pytest
from paperless141_mcp.writes import validate_reservation_params, WriteValidationError


def test_valid_params_normalized():
    p = validate_reservation_params(
        date="2026-09-15", start="14:00", end="16:00", tail="N111AB"
    )
    assert p == {
        "date": "2026-09-15", "start": "14:00", "end": "16:00", "tail": "N111AB",
    }


def test_end_before_start_raises():
    with pytest.raises(WriteValidationError):
        validate_reservation_params(date="2026-09-15", start="16:00", end="14:00", tail="x")


def test_bad_date_raises():
    with pytest.raises(WriteValidationError):
        validate_reservation_params(date="09/15/2026", start="14:00", end="16:00", tail="x")


def test_bad_time_raises():
    with pytest.raises(WriteValidationError):
        validate_reservation_params(date="2026-09-15", start="2pm", end="16:00", tail="x")


def test_empty_tail_raises():
    with pytest.raises(WriteValidationError):
        validate_reservation_params(date="2026-09-15", start="14:00", end="16:00", tail="")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_writes.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.writes`

- [ ] **Step 3: Write minimal implementation**

`src/paperless141_mcp/writes.py`:

```python
from __future__ import annotations
from datetime import datetime


class WriteValidationError(ValueError):
    """Raised when reservation parameters are invalid."""


def _check_date(date: str) -> str:
    try:
        return datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        raise WriteValidationError(f"date must be YYYY-MM-DD, got {date!r}")


def _check_time(label: str, value: str) -> str:
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except (ValueError, TypeError):
        raise WriteValidationError(f"{label} must be HH:MM (24h), got {value!r}")


def validate_reservation_params(date: str, start: str, end: str, tail: str) -> dict:
    """Validate and normalize core reservation fields; raise WriteValidationError on bad input."""
    d = _check_date(date)
    s = _check_time("start", start)
    e = _check_time("end", end)
    if e <= s:
        raise WriteValidationError(f"end ({e}) must be after start ({s})")
    if not tail or not tail.strip():
        raise WriteValidationError("tail (aircraft) is required")
    return {"date": d, "start": s, "end": e, "tail": tail.strip()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_writes.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/writes.py tests/test_writes.py
git commit -m "feat: add reservation parameter validation"
```

---

## Task 2: Preview formatting (`writes.py`)

**Files:**
- Modify: `src/paperless141_mcp/writes.py`
- Test: `tests/test_writes.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_writes.py`)**

```python
from paperless141_mcp.writes import format_create_preview, format_cancel_preview


def test_create_preview_describes_booking():
    params = {"date": "2026-09-15", "start": "14:00", "end": "16:00", "tail": "N111AB",
              "cfi": None, "category": None, "note": None}
    preview = format_create_preview(params)
    assert preview["action"] == "create_reservation"
    assert preview["confirmed"] is False
    assert "N111AB" in preview["summary"]
    assert "2026-09-15" in preview["summary"]


def test_cancel_preview_echoes_reservation():
    reservation = {"schedule_number": "700123", "resource": "N111AB",
                   "start": "9/15/2026 2:00:00 PM", "end": "9/15/2026 4:00:00 PM"}
    preview = format_cancel_preview(reservation)
    assert preview["action"] == "cancel_reservation"
    assert preview["confirmed"] is False
    assert "700123" in preview["summary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_writes.py -k preview -v`
Expected: FAIL with ImportError for `format_create_preview`

- [ ] **Step 3: Write minimal implementation (append to `writes.py`)**

```python
def format_create_preview(params: dict) -> dict:
    """Build a human-readable, no-write preview of a create_reservation call."""
    extras = []
    for key in ("cfi", "category", "note"):
        if params.get(key):
            extras.append(f"{key}={params[key]}")
    suffix = (" [" + ", ".join(extras) + "]") if extras else ""
    summary = (
        f"BOOK {params['tail']} on {params['date']} "
        f"{params['start']}–{params['end']}{suffix}"
    )
    return {"action": "create_reservation", "confirmed": False,
            "summary": summary, "params": params}


def format_cancel_preview(reservation: dict) -> dict:
    """Build a human-readable, no-write preview of a cancel_reservation call."""
    summary = (
        f"CANCEL reservation #{reservation['schedule_number']} "
        f"({reservation.get('resource', '?')} "
        f"{reservation.get('start', '?')}–{reservation.get('end', '?')})"
    )
    return {"action": "cancel_reservation", "confirmed": False,
            "summary": summary, "reservation": reservation}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_writes.py -k preview -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/writes.py tests/test_writes.py
git commit -m "feat: add create/cancel preview formatting"
```

---

## Task 3: Slot ranking for `find_open_slots` (`writes.py`)

**Files:**
- Modify: `src/paperless141_mcp/writes.py`
- Test: `tests/test_writes.py`

> Operates on the output of the existing `parsers.availability.parse_availability`. Pure
> logic — no browser. Given a parsed board and optional filters, return candidate open
> slots ranked by earliest start.

- [ ] **Step 1: Write the failing test (append to `tests/test_writes.py`)**

```python
from paperless141_mcp.writes import open_slots_from_board


def test_open_slots_filters_and_ranks():
    parsed = {
        "resources": [
            {"reg": "N111AB", "type": "C152", "location": "KPAO"},
            {"reg": "N222CD", "type": "C172S", "location": "KSQL"},
        ],
        "rows": [
            {"time": "07:00", "cells": {"N111AB": {"status": "free"},
                                         "N222CD": {"status": "booked", "label": "x"}}},
            {"time": "07:30", "cells": {"N111AB": {"status": "free"},
                                         "N222CD": {"status": "free"}}},
        ],
    }
    slots = open_slots_from_board(parsed, type_or_tail="C152")
    assert slots == [
        {"reg": "N111AB", "type": "C152", "location": "KPAO", "time": "07:00"},
        {"reg": "N111AB", "type": "C152", "location": "KPAO", "time": "07:30"},
    ]


def test_open_slots_match_by_tail():
    parsed = {
        "resources": [{"reg": "N222CD", "type": "C172S", "location": "KSQL"}],
        "rows": [{"time": "07:30", "cells": {"N222CD": {"status": "free"}}}],
    }
    slots = open_slots_from_board(parsed, type_or_tail="N222CD")
    assert slots == [{"reg": "N222CD", "type": "C172S", "location": "KSQL", "time": "07:30"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_writes.py -k open_slots -v`
Expected: FAIL with ImportError for `open_slots_from_board`

- [ ] **Step 3: Write minimal implementation (append to `writes.py`)**

```python
def open_slots_from_board(parsed: dict, type_or_tail: str | None = None) -> list[dict]:
    """Return free (reg, type, location, time) slots from a parsed scheduler board.

    type_or_tail (optional) matches either an aircraft type (substring, case-insensitive)
    or an exact tail number. Results are ordered by resource then time.
    """
    by_reg = {r["reg"]: r for r in parsed["resources"]}
    needle = type_or_tail.lower() if type_or_tail else None
    out = []
    for res in parsed["resources"]:
        reg = res["reg"]
        if needle is not None:
            if needle != reg.lower() and needle not in (res.get("type", "").lower()):
                continue
        for row in parsed["rows"]:
            if row["cells"].get(reg, {}).get("status") == "free":
                out.append({**res, "time": row["time"]})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_writes.py -k open_slots -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/paperless141_mcp/writes.py tests/test_writes.py
git commit -m "feat: add open-slot ranking for find_open_slots"
```

---

## Task 4: Booking confirmation parser (`parsers/confirmation.py`)

**Files:**
- Create: `src/paperless141_mcp/parsers/confirmation.py`
- Create: `tests/fixtures/booking_confirmation_sample.html`
- Test: `tests/parsers/test_confirmation.py`

> Parses the reservation-detail page (`mstr7a.aspx?schednum=N`) to extract the
> `schedule_number` and confirm a booking exists. The real markup is captured during the
> discovery checkpoint (Task 5); this synthetic fixture mirrors the expected shape and is
> **replaced/validated** against the real capture in Task 5.

- [ ] **Step 1: Add a synthetic fixture**

`tests/fixtures/booking_confirmation_sample.html`:

```html
<html><head><title>Paperless141©: Schedule Detail</title></head><body>
<form id="login" action="./mstr7a.aspx?schednum=700123">
  <span id="ctl00_ContentPlaceHolder1_lblSchedNum">Schedule# 700123</span>
  <input id="ctl00_ContentPlaceHolder1_txtResource" value="N111AB">
  <input id="ctl00_ContentPlaceHolder1_txtStart" value="9/15/2026 2:00:00 PM">
  <input id="ctl00_ContentPlaceHolder1_txtEnd" value="9/15/2026 4:00:00 PM">
</form></body></html>
```

- [ ] **Step 2: Write the failing test**

`tests/parsers/test_confirmation.py`:

```python
from pathlib import Path
from paperless141_mcp.parsers.confirmation import parse_booking_result

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "booking_confirmation_sample.html"


def test_extracts_schedule_number():
    result = parse_booking_result(FIX.read_text())
    assert result["schedule_number"] == "700123"
    assert result["ok"] is True


def test_missing_schedule_number_is_not_ok():
    result = parse_booking_result("<html><body>no schedule here</body></html>")
    assert result["ok"] is False
    assert result["schedule_number"] is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/parsers/test_confirmation.py -v`
Expected: FAIL with `ModuleNotFoundError: paperless141_mcp.parsers.confirmation`

- [ ] **Step 4: Write minimal implementation**

`src/paperless141_mcp/parsers/confirmation.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/parsers/test_confirmation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/paperless141_mcp/parsers/confirmation.py tests/parsers/test_confirmation.py \
        tests/fixtures/booking_confirmation_sample.html
git commit -m "feat: add booking confirmation parser (schedule_number extraction)"
```

---

## 🛑 Task 5: DISCOVERY CHECKPOINT — capture the live booking + cancel flow

**Files:**
- Create: `docs/superpowers/discovery/2026-06-16-booking-flow.md`
- Create (git-ignored captures): `tests/fixtures/create_step*.html`, `*.png`

> This is an **interactive, live** task on a **throwaway far-future slot** (`2026-09-15`).
> It produces the exact click-path and selectors needed for Tasks 6–9. It performs a REAL
> create and then a REAL cancel to clean up — only on the throwaway slot, never the user's
> real reservations. Get explicit user go-ahead before the create step.

- [ ] **Step 1: Enter Make/Modify mode and capture the board**

Write a throwaway script (`scripts/discover_booking.py`, not committed) that:
1. `BrowserSession.open_scheduler("#ctl00_BtnSched", "2026-09-15")`
2. clicks `#ctl00_ContentPlaceHolder1_ButtMMS`, waits for networkidle
3. saves `tests/fixtures/create_step1_mmsmode.html` + screenshot
4. enumerates the now-clickable slot cells: for an aircraft column, list the anchors and
   their `href`/`onclick`, and which cells are visible/enabled.

Run it. Inspect the screenshot + HTML to identify how a bookable cell is clicked in MMS mode
(it may differ from the read-only board: a visible cell, a popup window via `window.open`, or
an inline form). Record findings.

- [ ] **Step 2: Open the create form on the throwaway slot (no submit) and capture**

Extend the script to click the identified bookable cell for one aircraft at one time, handling
popups (`context.on("page", ...)`) and dialogs (`context.on("dialog", ...)`). Save the
resulting create form as `create_step2_form.html` + screenshot. Identify the form's field
controls (resource, start, end, CFI, category, note) and the **Save/Book** button id.
**Do not click Save yet.**

- [ ] **Step 3: Get user go-ahead, then perform ONE real create**

Confirm with the user the exact slot to book. Fill the create form for the throwaway slot and
click Save. Capture the result page (`create_step3_result.html`). Confirm via
`get_my_schedule()` that a new reservation appeared; note its `schedule_number`.

- [ ] **Step 4: Capture the cancel flow on that test reservation**

From `get_my_schedule`, the new reservation links to `mstr7a.aspx?schednum=<N>`. Navigate
there, capture `cancel_step1_detail.html` + screenshot, and identify the **Cancel/Delete**
control. Click it (and confirm any dialog). Capture the result; confirm via `get_my_schedule`
that the test reservation is gone.

- [ ] **Step 5: Write the discovery document**

`docs/superpowers/discovery/2026-06-16-booking-flow.md` records, concretely:
- Create click-path: ordered steps + exact selectors (MMS button, slot-cell selector pattern,
  each form field id, Save button id).
- The real markup of `mstr7a.aspx` (so the Task 4 confirmation parser can be validated/adjusted
  against it — update `parsers/confirmation.py` + its fixture if the real ids differ).
- Cancel click-path: navigate to detail, cancel control selector, confirmation dialog handling.
- Any popups/dialogs and how they were handled.

- [ ] **Step 6: Commit the discovery doc (not the captures — they are git-ignored)**

```bash
git add docs/superpowers/discovery/2026-06-16-booking-flow.md
# include parsers/confirmation.py + fixture if they were corrected against real markup
git commit -m "docs: capture live booking + cancel flow (discovery)"
```

---

## Task 6: BrowserSession write-flow methods (`browser.py`)

**Files:**
- Modify: `src/paperless141_mcp/browser.py`

> Implement the methods using the **selectors recorded in Task 5's discovery doc**. The
> structure below is fixed; the selector constants marked `# from discovery` are filled from
> `docs/superpowers/discovery/2026-06-16-booking-flow.md`. These methods are validated live in
> Task 9 (no offline unit test — they require the live stateful flow).

- [ ] **Step 1: Add selector constants + methods**

Add to `src/paperless141_mcp/browser.py` (constants near the top, methods on `BrowserSession`):

```python
# Booking-flow selectors — populated from the Task 5 discovery doc.
MMS_BUTTON = "#ctl00_ContentPlaceHolder1_ButtMMS"
SAVE_BUTTON = ""        # from discovery: the create form's Save/Book button id
CANCEL_BUTTON = ""      # from discovery: the cancel/delete control on mstr7a.aspx


async def enter_make_modify(self) -> None:
    """Put the scheduler board into Make/Modify (editing) mode. Caller holds the lock."""
    await self._page.click(MMS_BUTTON)
    await self._page.wait_for_load_state("networkidle")
```

Add `book_slot` and `cancel_reservation_flow` on `BrowserSession`, each acquiring
`self._lock` and re-using `_open_locked("#ctl00_BtnSched")`. Their bodies follow the exact
ordered click-path from discovery: open scheduler at `date`, `enter_make_modify()`, select the
slot cell for `tail`/`start` (selector pattern from discovery), fill the create form fields
(field ids from discovery), click `SAVE_BUTTON`, and return the resulting page HTML. For
cancel: navigate to `mstr7a.aspx?schednum=<schedule_number>`, click `CANCEL_BUTTON`, handle the
confirm dialog, return the resulting HTML.

(The precise body is transcribed from the discovery doc — do not invent selectors; use the ones
recorded there.)

- [ ] **Step 2: Verify import**

Run: `. .venv/bin/activate && python -c "import paperless141_mcp.browser; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/paperless141_mcp/browser.py
git commit -m "feat: add make/modify, book_slot, and cancel flow to BrowserSession"
```

---

## Task 7: `create_reservation` tool (`tools.py` + `server.py`)

**Files:**
- Modify: `src/paperless141_mcp/tools.py`
- Modify: `src/paperless141_mcp/server.py`

- [ ] **Step 1: Add the tool function to `tools.py`**

```python
from .writes import validate_reservation_params, format_create_preview, open_slots_from_board
from .parsers.confirmation import parse_booking_result
from .parsers.availability import parse_availability

_BTN_SCHEDULER = "#ctl00_BtnSched"  # already defined; reuse


async def find_open_slots(date: str, type_or_tail: str | None = None) -> list[dict]:
    """Return free (reg, type, location, time) slots for a date, optional type/tail filter."""
    html = await get_browser().open_scheduler(_BTN_SCHEDULER, date)
    return open_slots_from_board(parse_availability(html), type_or_tail)


async def create_reservation(date: str, start: str, end: str, tail: str,
                             cfi: str | None = None, category: str | None = None,
                             note: str | None = None, confirm: bool = False) -> dict:
    """Create a reservation. With confirm=False, returns a preview and writes nothing."""
    params = validate_reservation_params(date, start, end, tail)
    params.update({"cfi": cfi, "category": category, "note": note})
    if not confirm:
        return format_create_preview(params)
    html = await get_browser().book_slot(**params)
    result = parse_booking_result(html)
    return {"action": "create_reservation", "confirmed": True, **result}
```

- [ ] **Step 2: Register in `server.py`**

```python
@mcp.tool()
async def find_open_slots(date: str, type_or_tail: str | None = None) -> list[dict]:
    """Find free aircraft time slots on a date (YYYY-MM-DD), optionally filtered by type or tail."""
    return await tools.find_open_slots(date, type_or_tail)


@mcp.tool()
async def create_reservation(date: str, start: str, end: str, tail: str,
                             cfi: str | None = None, category: str | None = None,
                             note: str | None = None, confirm: bool = False) -> dict:
    """Create a reservation. Defaults to a PREVIEW (confirm=False, no write).
    Set confirm=True to actually book. date=YYYY-MM-DD, start/end=HH:MM (24h), tail=aircraft.
    """
    return await tools.create_reservation(date, start, end, tail, cfi, category, note, confirm)
```

- [ ] **Step 3: Verify preview path with a unit-style check (no live write)**

Run:
```bash
. .venv/bin/activate && python -c "
import asyncio; from paperless141_mcp import tools
p = asyncio.run(tools.create_reservation('2026-09-15','14:00','16:00','N111AB'))
assert p['confirmed'] is False and 'N111AB' in p['summary']; print('preview ok:', p['summary'])
"
```
Expected: `preview ok: BOOK N111AB on 2026-09-15 14:00–16:00`

- [ ] **Step 4: Commit**

```bash
git add src/paperless141_mcp/tools.py src/paperless141_mcp/server.py
git commit -m "feat: add find_open_slots and create_reservation tools (preview-then-confirm)"
```

---

## Task 8: `cancel_reservation` tool (`tools.py` + `server.py`)

**Files:**
- Modify: `src/paperless141_mcp/tools.py`
- Modify: `src/paperless141_mcp/server.py`

- [ ] **Step 1: Add the tool function to `tools.py`**

```python
from .writes import format_cancel_preview
from .parsers.my_schedule import parse_my_schedule  # already imported; reuse


async def cancel_reservation(schedule_number: str, confirm: bool = False) -> dict:
    """Cancel one reservation by schedule_number. With confirm=False, previews only."""
    # Find the reservation in the user's schedule to echo it in the preview.
    sched = await get_my_schedule()
    match = next((r for r in sched if r["schedule_number"] == str(schedule_number)), None)
    if match is None:
        return {"action": "cancel_reservation", "confirmed": False,
                "error": f"no reservation #{schedule_number} found in your schedule"}
    if not confirm:
        return format_cancel_preview(match)
    html = await get_browser().cancel_reservation_flow(str(schedule_number))
    # Success = the reservation is no longer in the schedule.
    after = await get_my_schedule()
    gone = all(r["schedule_number"] != str(schedule_number) for r in after)
    return {"action": "cancel_reservation", "confirmed": True,
            "cancelled": gone, "schedule_number": str(schedule_number)}
```

- [ ] **Step 2: Register in `server.py`**

```python
@mcp.tool()
async def cancel_reservation(schedule_number: str, confirm: bool = False) -> dict:
    """Cancel one reservation by its schedule_number. Defaults to a PREVIEW (confirm=False).
    Set confirm=True to actually cancel.
    """
    return await tools.cancel_reservation(schedule_number, confirm)
```

- [ ] **Step 3: Verify the tool registers**

Run:
```bash
. .venv/bin/activate && python -c "
import asyncio; from paperless141_mcp.server import mcp
print(sorted(t.name for t in asyncio.run(mcp.list_tools())))
"
```
Expected: includes `cancel_reservation`, `create_reservation`, `find_open_slots`.

- [ ] **Step 4: Commit**

```bash
git add src/paperless141_mcp/tools.py src/paperless141_mcp/server.py
git commit -m "feat: add cancel_reservation tool (preview-then-confirm)"
```

---

## Task 9: Live round-trip validation + README + final review

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Live create→verify→cancel→verify on the throwaway slot**

With user go-ahead, run a deliberate script (not committed):
```python
import asyncio
from paperless141_mcp import tools

async def main():
    # find a free slot on the throwaway date
    slots = await tools.find_open_slots("2026-09-15", type_or_tail="C152")
    s = slots[0]; print("booking", s)
    created = await tools.create_reservation("2026-09-15", s["time"], "23:30", s["reg"], confirm=True)
    print("created:", created); num = created["schedule_number"]
    assert num, "no schedule_number returned"
    sched = await tools.get_my_schedule()
    assert any(r["schedule_number"] == num for r in sched), "not in schedule after create"
    cancelled = await tools.cancel_reservation(num, confirm=True)
    print("cancelled:", cancelled)
    assert cancelled["cancelled"] is True, "still present after cancel"
    await tools.get_browser().close()

asyncio.run(main())
```
Expected: create returns a `schedule_number`, it appears in `get_my_schedule`, cancel removes it.
Confirm the user's 3 real reservations (#688447, #688368, #688279) are untouched.

- [ ] **Step 2: Update `README.md`**

Add the three new tools to the tools table and a short "Write operations (preview-then-confirm)"
section noting the safety model. Move `create/modify/cancel` out of "not yet built" (leave
`modify` listed as Phase W2 / pending).

- [ ] **Step 3: Run the full offline suite**

Run: `. .venv/bin/activate && pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document write tools and validate create/cancel round-trip"
```

- [ ] **Step 5: Dispatch a final code-quality review** of the W1 diff (writes.py, browser.py
  changes, confirmation parser, tools) focusing on safety (preview-then-confirm enforced,
  single-target only, no false success claims) and the live-flow error handling.

---

## Self-review notes

- **Spec coverage:** find_open_slots ✓ (Task 3, 7); create preview+confirm ✓ (Task 7); cancel
  preview+confirm ✓ (Task 8); confirmation parsing ✓ (Task 4); discovery of the stateful flow ✓
  (Task 5); safety model — preview default, single schedule_number target, throwaway-slot test,
  no-false-success ✓ (Tasks 7,8,9); Playwright UI automation ✓ (Task 6). Modify is explicitly
  Phase W2 (out of this plan).
- **Discovery-dependent spots (by necessity, flagged inline):** `SAVE_BUTTON`, `CANCEL_BUTTON`,
  slot-cell selector pattern, and create-form field ids are filled from Task 5's discovery doc;
  the confirmation parser is validated against the real `mstr7a.aspx` markup in Task 5.
- **Type consistency:** `validate_reservation_params(...) -> dict` with keys
  date/start/end/tail; previews carry `action`/`confirmed`/`summary`; `book_slot(**params)`
  consumes date/start/end/tail/cfi/category/note; `parse_booking_result(html) -> {ok, schedule_number}`;
  `cancel_reservation_flow(schedule_number)`. Names consistent across Tasks 1–9.
