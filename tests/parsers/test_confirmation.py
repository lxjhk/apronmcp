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
