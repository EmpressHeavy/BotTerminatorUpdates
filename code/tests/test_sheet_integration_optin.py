"""OPT-IN real Google Sheets test of the package's own writer (google-api-python-client path).

Skipped unless BOTH are set:
  BOT_TERMINATOR_TEST_SHEET_ID  = ID of a throwaway spreadsheet in YOUR Drive (never your real review sheet)
  BOT_TERMINATOR_GOOGLE_OAUTH_CLIENT (recommended; desktop OAuth client JSON, browser sign-in on first run)
    or BOT_TERMINATOR_GOOGLE_CREDENTIALS (service-account key; share the test sheet with its email)
and `pip install -r requirements-sheets.txt`. Writes only fake rows to a tab named BT_INTEGRATION_TEST
(created if missing); never touches other tabs.
"""
import os, sys, tempfile, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import review_sheet_writer as rsw
import review_followup as rf

SHEET = os.environ.get("BOT_TERMINATOR_TEST_SHEET_ID")
CREDS = os.environ.get(rsw.OAUTH_CLIENT_ENV) or os.environ.get(rsw.CREDENTIALS_ENV)
pytestmark = pytest.mark.skipif(not (SHEET and CREDS), reason="opt-in: set BOT_TERMINATOR_TEST_SHEET_ID and Google credentials")
TAB = "BT_INTEGRATION_TEST"


def test_real_sheet_append_only_roundtrip():
    root = tempfile.mkdtemp()
    svc = rsw._build_service(user_key="integration_test", root=root)
    meta = svc.spreadsheets().get(spreadsheetId=SHEET).execute()
    if TAB not in [s["properties"]["title"] for s in meta["sheets"]]:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET, body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()
    before = rsw.existing_rows(svc, SHEET, TAB)
    tag = str(int(time.time()))
    items = [{"type": "GRAVEYARD_RETURN", "action": "block", "handle": f"example_bot_{tag}", "x_user_id": "1234567890123456789",
              "label": "Graveyard return", "ref": "returns R1"}]
    rows = rf.in_review_rows(items, f"snap_{tag}", "2026-10-16")
    r1 = rsw.write_rows_to_sheet(rows, spreadsheet_id=SHEET, tab=TAB, service=svc, dedupe_key=rf._row_key)
    r2 = rsw.write_rows_to_sheet(rows, spreadsheet_id=SHEET, tab=TAB, service=svc, dedupe_key=rf._row_key)
    after = rsw.existing_rows(svc, SHEET, TAB)
    assert r1["rows_written"] == 1 and r2["rows_written"] == 0           # dedupe on repeat
    assert after[:len(before)] == before                                   # nothing overwritten
    assert after[-1][3] == "1234567890123456789" and after[-1][13] == "2026-10-16" and after[-1][10] == "In review"
    assert sum(1 for r in after if r[:2] == rsw.REVIEW_QUEUE_HEADER[:2]) == 1
