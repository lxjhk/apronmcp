from pathlib import Path
import pytest
from paperless141_mcp.parsers.availability import (
    parse_availability,
    free_slots_by_resource,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "availability_sample.html"
REAL = FIXTURES / "scheduler.html"  # git-ignored real capture, present only locally


def test_parses_resources():
    parsed = parse_availability(SAMPLE.read_text())
    assert parsed["resources"] == [
        {"reg": "N111AB", "type": "C152", "location": "KPAO"},
        {"reg": "N222CD", "type": "C172S", "location": "KSQL"},
    ]


def test_classifies_cell_states():
    parsed = parse_availability(SAMPLE.read_text())
    rows = {r["time"]: r["cells"] for r in parsed["rows"]}
    # 07:00 -> N111AB free (empty + active link), N222CD unavailable (*)
    assert rows["07:00"]["N111AB"] == {"status": "free"}
    assert rows["07:00"]["N222CD"] == {"status": "unavailable"}
    # 07:30 -> N111AB booked with label, N222CD free
    assert rows["07:30"]["N111AB"] == {"status": "booked", "label": "Doe, Jane"}
    assert rows["07:30"]["N222CD"] == {"status": "free"}
    # 08:00 -> N111AB maintenance (booked label MAINT)
    assert rows["08:00"]["N111AB"] == {"status": "booked", "label": "MAINT"}


def test_free_slots_by_resource_is_compact():
    parsed = parse_availability(SAMPLE.read_text())
    compact = free_slots_by_resource(parsed)
    by_reg = {r["reg"]: r for r in compact}
    assert by_reg["N111AB"]["free_times"] == ["07:00"]
    assert by_reg["N222CD"]["free_times"] == ["07:30", "08:00"]


def test_returns_empty_when_table_absent():
    assert parse_availability("<html><body>x</body></html>") == {
        "resources": [],
        "rows": [],
    }


@pytest.mark.skipif(not REAL.exists(), reason="real capture not present (run recon)")
def test_real_capture_parses():
    parsed = parse_availability(REAL.read_text())
    assert len(parsed["resources"]) > 5
    assert all("reg" in r for r in parsed["resources"])
    assert len(parsed["rows"]) > 5
    # every cell must be classified into a known status
    statuses = {
        c["status"]
        for row in parsed["rows"]
        for c in row["cells"].values()
    }
    assert statuses <= {"free", "unavailable", "booked"}
    # the real board has at least some of each meaningful state
    assert "free" in statuses and "booked" in statuses
