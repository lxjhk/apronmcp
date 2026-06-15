from pathlib import Path
import pytest
from paperless141_mcp.parsers.my_schedule import parse_my_schedule

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "my_schedule_sample.html"
REAL = FIXTURES / "my_schedule.html"  # git-ignored real capture, present only locally


def test_parses_rows_from_sample():
    rows = parse_my_schedule(SAMPLE.read_text())
    assert len(rows) == 2
    assert rows[0] == {
        "schedule_number": "700001",
        "resource": "268Z",
        "start": "6/15/2026 6:00:00 PM",
        "end": "6/15/2026 8:00:00 PM",
        "pilot": "Doe, Jane",
        "cfi": "Smith, Bob",
        "note": "",
    }


def test_empty_cfi_and_note_are_blank_strings():
    rows = parse_my_schedule(SAMPLE.read_text())
    assert rows[1]["cfi"] == ""
    assert rows[1]["note"] == "XC trip"
    assert rows[1]["schedule_number"] == "700002"


def test_returns_empty_list_when_table_absent():
    assert parse_my_schedule("<html><body>no grid</body></html>") == []


@pytest.mark.skipif(not REAL.exists(), reason="real capture not present (run recon)")
def test_real_capture_parses_with_expected_keys():
    rows = parse_my_schedule(REAL.read_text())
    assert len(rows) >= 1
    assert set(rows[0]) == {
        "schedule_number", "resource", "start", "end", "pilot", "cfi", "note",
    }
    assert rows[0]["schedule_number"].isdigit()
