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


def open_slots_from_board(parsed: dict, type_or_tail: str | None = None) -> list[dict]:
    """Return free (reg, type, location, time) slots from a parsed scheduler board.

    type_or_tail (optional) matches either an aircraft type (substring, case-insensitive)
    or an exact tail number. Results are ordered by resource then time.
    """
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
