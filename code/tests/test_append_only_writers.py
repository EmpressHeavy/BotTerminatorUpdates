"""Review sheet / CSV writers always APPEND after the last existing row (never fixed row, never overwrite)."""
import csv, io, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import review_sheet_writer as rsw
import review_followup as rf
import graveyard_returns as gr
import graveyard_return_cards as grc
import storage as st
from test_graveyard_returns import env, UK  # noqa: F401
from test_review_followup import rv  # noqa: F401


class FakeSheet:
    """Minimal Sheets API with values.get and values.append semantics (table end = last used row; empty table ->
    anchor row of the range; INSERT_ROWS never overwrites). Rejects any other write method."""
    def __init__(self, rows=None):
        self.rows = [list(r) for r in (rows or [])]
        self._op = None
        self.calls = []
    def spreadsheets(self): return self
    def values(self): return self
    def get(self, spreadsheetId, range):
        self._op = ("get",); return self
    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        assert valueInputOption == "USER_ENTERED" and insertDataOption == "INSERT_ROWS"
        self.calls.append(range); self._op = ("app", range, body["values"]); return self
    def execute(self):
        if self._op[0] == "get":
            return {"values": [list(r) for r in self.rows]} if self.rows else {}
        _, rng, vals = self._op
        anchor = int(rng.split("!A")[1].split(":")[0])
        used = [i for i, r in enumerate(self.rows) if any(str(c) for c in r)]
        start = (used[-1] + 2) if used and used[-1] + 1 >= anchor else anchor
        while len(self.rows) < start - 1:
            self.rows.append([])
        self.rows[start - 1:start - 1] = [list(v) for v in vals]   # insert, never overwrite
        tab = rng.split("!")[0]
        return {"updates": {"updatedRange": f"{tab}!A{start}:R{start + len(vals) - 1}", "updatedRows": len(vals)}}


def test_sheet_appends_after_existing_rows_and_keeps_them():
    existing = [["Title"], [], rsw.REVIEW_QUEUE_HEADER, ["", "BT-1"], ["", "BT-2"]]
    sh = FakeSheet(existing)
    res = rsw.write_rows_to_sheet([["", "BT-3"], ["", "BT-4"]], spreadsheet_id="s", service=sh)
    assert res["start_row"] == 6 and sh.rows[:5] == existing
    assert [r[1] for r in sh.rows[3:]] == ["BT-1", "BT-2", "BT-3", "BT-4"]
    assert sh.rows.count(rsw.REVIEW_QUEUE_HEADER) == 1  # no repeated header


def test_repeated_sheet_writes_append_in_order_and_empty_tab_keeps_layout():
    sh = FakeSheet()
    r1 = rsw.write_rows_to_sheet([["", "A"]], spreadsheet_id="s", service=sh)
    assert r1["start_row"] == 4 and sh.rows[2] == rsw.REVIEW_QUEUE_HEADER  # empty tab: original layout
    rsw.write_rows_to_sheet([["", "B"]], spreadsheet_id="s", service=sh)
    r3 = rsw.write_rows_to_sheet(lambda start: [["", f"C@{start}"]], spreadsheet_id="s", service=sh)
    assert [r[1] for r in sh.rows[3:]] == ["A", "B", "C@6"] and r3["start_row"] == 6
    assert all(c.endswith("!A3:R") for c in sh.calls[1:]) and sh.calls[0].endswith("!A3:R")


def test_csv_appends_without_losing_rows(tmp_path):
    p = tmp_path / "q.csv"
    rsw.write_rows_csv([["", "BT-1"]], p)
    rsw.write_rows_csv([["", "BT-2"], ["", "BT-3"]], p)
    data = list(csv.reader(p.open(encoding="utf-8")))
    assert data[0] == rsw.REVIEW_QUEUE_HEADER and [r[1] for r in data[1:]] == ["BT-1", "BT-2", "BT-3"]
    assert sum(1 for r in data if r == rsw.REVIEW_QUEUE_HEADER) == 1


def test_in_review_csv_and_sheet_append_without_duplicates(rv):
    out1 = rf.write_in_review(UK, rv["s2"], rv["root"])
    out2 = rf.write_in_review(UK, rv["s2"], rv["root"])  # same in-review accounts: not added twice
    rows = list(csv.reader(open(out2["csv"])))
    assert out1["rows"] == 4 and len(rows) == 5
    sh = FakeSheet([["Title"], [], rsw.REVIEW_QUEUE_HEADER, ["", "BT-old", "", "2000000999", "@someone"]])
    rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="s", service=sh, cfg={"runtime": "standalone", "sheets": {"backend": "google_api"}}, env={"BOT_TERMINATOR_GOOGLE_CREDENTIALS": "x", "BOT_TERMINATOR_STANDALONE": "1"})
    rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="s", service=sh, cfg={"runtime": "standalone", "sheets": {"backend": "google_api"}}, env={"BOT_TERMINATOR_GOOGLE_CREDENTIALS": "x", "BOT_TERMINATOR_STANDALONE": "1"})
    assert sh.rows[3][1] == "BT-old" and len(sh.rows) == 8
    assert {r[10] for r in sh.rows[4:]} == {"In review"}


def test_graveyard_returns_csv_append_only(env):
    p = st.reports_path(env["root"], user_key=UK) / f"graveyard_returns_{env['s2']}.csv"
    before = p.read_text().splitlines()
    gr.detect_returns(UK, env["s2"], env["root"])
    assert p.read_text().splitlines() == before and len(before) == 6


def test_in_review_ids_and_dates_stay_text_in_sheets():
    """Real-sheet finding 2026-10-16: unprefixed IDs/dates were parsed by USER_ENTERED (date serial; long IDs rounded)."""
    rows = rf.in_review_rows([{"type": "GRAVEYARD_RETURN", "handle": "example_bot_4", "x_user_id": "1234567890123456789",
                               "label": "Graveyard return", "ref": "returns R3"}], "snap_demo", "2026-10-16")
    assert rows[0][3] == "'1234567890123456789" and rows[0][13] == "'2026-10-16"
    # dedupe key matches the same account whether read back from the sheet (no apostrophe) or freshly built
    assert rf._row_key(rows[0]) == rf._row_key(["", "", "", "1234567890123456789", "@example_bot_4", "", "", "", "",
                                                 "snap_demo", "In review"])


def test_bridge_runs_real_writer_code():
    from sheet_connector_bridge import BridgeService, rows_from_csv
    svc = BridgeService(rows_from_csv("\n\nSelect,Review ID\n,BT-1\n\n"))
    svc.append_response = {"updates": {"updatedRange": "'In review'!A5:R5"}}
    res = rsw.write_rows_to_sheet([["", "BT-2"]], spreadsheet_id="x", service=svc)
    assert res["start_row"] == 5 and svc.appends == [{"range": "'In review'!A3:R", "valueInputOption": "USER_ENTERED",
                                                     "insertDataOption": "INSERT_ROWS", "values": [["", "BT-2"]]}]


def test_effective_formula_is_position_independent():
    import populate_review_sheet as prs
    f = prs.effective_formula(4)
    assert f == prs.effective_formula(99) and 'INDIRECT("K"&ROW())' in f and "K4" not in f
