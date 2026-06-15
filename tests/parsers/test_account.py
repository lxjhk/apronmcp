from pathlib import Path
import pytest
from paperless141_mcp.parsers.account import parse_account

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "account_sample.html"
REAL = FIXTURES / "account.html"  # git-ignored real capture, present only locally


def test_parses_transactions_and_skips_pager_rows():
    rows = parse_account(SAMPLE.read_text())
    assert len(rows) == 2  # the two data rows, not the pager rows
    assert rows[0] == {
        "date": "06/14/2026",
        "activity_type": "DEBIT",
        "amount": "457.47",
        "tax": "0.00",
        "comment": "15MJ 1.70 Hrs@245.00/H",
        "balance": "3839.30",
    }


def test_credit_row_parsed():
    rows = parse_account(SAMPLE.read_text())
    assert rows[1]["activity_type"] == "CREDIT"
    assert rows[1]["amount"] == "1000.00"


def test_returns_empty_list_when_table_absent():
    assert parse_account("<html><body>no grid</body></html>") == []


@pytest.mark.skipif(not REAL.exists(), reason="real capture not present (run recon)")
def test_real_capture_parses_with_expected_keys():
    rows = parse_account(REAL.read_text())
    assert len(rows) >= 1
    assert set(rows[0]) == {
        "date", "activity_type", "amount", "tax", "comment", "balance",
    }
    # every parsed row must have a real date (pager rows excluded)
    import re
    assert all(re.match(r"\d{1,2}/\d{1,2}/\d{4}$", r["date"]) for r in rows)
