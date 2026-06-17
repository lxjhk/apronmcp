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
