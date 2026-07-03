from pathlib import Path
import pytest
from apronmcp.parsers.my_schedule import parse_my_schedule

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


def test_nested_pager_table_does_not_produce_phantom_rows():
    """A pager row containing a nested <table> of digits must not be read as data
    (regression: cell extraction must only look at a row's direct children)."""
    html = """
    <table id="ctl00_ContentPlaceHolder1_GridView1">
      <tr><th>&nbsp;</th><th>Schedule#</th><th>Resource</th><th>Start</th>
          <th>End</th><th>Pilot</th><th>CFI</th><th>Note</th></tr>
      <tr><td><input value="Download"/></td><td>700001</td><td>268Z</td>
          <td>s</td><td>e</td><td>P</td><td>C</td><td></td></tr>
      <tr><td colspan="8"><table><tr><td>1</td><td>2</td><td>3</td>
          <td>4</td><td>5</td><td>6</td><td>7</td><td>8</td></tr></table></td></tr>
    </table>
    """
    rows = parse_my_schedule(html)
    assert [r["schedule_number"] for r in rows] == ["700001"]


@pytest.mark.skipif(not REAL.exists(), reason="real capture not present (run recon)")
def test_real_capture_parses_with_expected_keys():
    rows = parse_my_schedule(REAL.read_text())
    assert len(rows) >= 1
    assert set(rows[0]) == {
        "schedule_number", "resource", "start", "end", "pilot", "cfi", "note",
    }
    assert rows[0]["schedule_number"].isdigit()
