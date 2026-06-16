import pytest
from paperless141_mcp.tools import _validate_date, DateFormatError
from paperless141_mcp.parsers.availability import parse_board_date


def test_validate_date_accepts_iso():
    assert _validate_date("2026-06-19") == "2026-06-19"


@pytest.mark.parametrize("bad", ["06/19/2026", "2026-6-19x", "tomorrow", "", "2026-13-01"])
def test_validate_date_rejects_bad_formats(bad):
    with pytest.raises(DateFormatError):
        _validate_date(bad)


def test_parse_board_date_reads_input_value():
    html = '<input id="ctl00_ContentPlaceHolder1_DropDate1" type="date" value="2026-06-19">'
    assert parse_board_date(html) == "2026-06-19"


def test_parse_board_date_returns_none_when_absent():
    assert parse_board_date("<html><body>no date</body></html>") is None
