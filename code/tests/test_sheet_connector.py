"""Connector (default) sheet-write path: plan generation, empty vs existing tab, dedupe, backend selection."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import sheet_connector as sc
import review_sheet_writer as rsw
import review_followup as rf
from test_append_only_writers import FakeSheet
from test_graveyard_returns import env, UK  # noqa: F401
from test_review_followup import rv  # noqa: F401

ITEMS = [{"type": "GRAVEYARD_RETURN", "handle": "example_bot_4", "x_user_id": "1234567890123456789",
          "label": "Graveyard return", "ref": "returns R3"}]


def test_default_backend_is_connector():
    assert sc.select_backend({}, env={})["backend"] == "connector"
    cfg = json.loads((ROOT / "config/default_user_config.json").read_text())
    assert cfg["sheets"]["backend"] == "connector" and sc.select_backend(cfg, env={})["backend"] == "connector"


def test_fallback_rules():
    keys = {rsw.OAUTH_CLIENT_ENV: "/x/client.json"}
    SA = {"runtime": "standalone"}; SE = {"BOT_TERMINATOR_STANDALONE": "1"}
    # Grok Bot runtime (default): google_api / csv are refused, even with keys
    for b in ("google_api", "csv"):
        assert sc.select_backend({"sheets": {"backend": b}}, env=keys)["backend"] == "refused"
        assert sc.select_backend({"runtime": "grokbot", "sheets": {"backend": b}}, env=dict(keys, **SE))["backend"] == "refused"
    # standalone (config runtime standalone AND env flag): google_api only when chosen AND keys set
    assert sc.select_backend(dict(SA, sheets={"backend": "google_api"}), env=dict(keys, **SE))["backend"] == "google_api"
    r = sc.select_backend(dict(SA, sheets={"backend": "google_api"}), env=SE)
    assert r["backend"] == "csv" and "CSV" in r["message"]
    assert sc.select_backend(dict(SA, sheets={"backend": "csv"}), env=SE)["backend"] == "csv"
    # connector stays default even when fallback env vars exist
    assert sc.select_backend({}, env=keys)["backend"] == "connector"
    # connector unavailable: google_api only with env vars, else CSV with a clear message (never silent)
    # inside Grok Bot (connector) with no connection: refuse, even when google_api keys exist (no silent fallback)
    assert sc.select_backend({}, connector_available=False, env=keys)["backend"] == "refused"
    r = sc.select_backend({}, connector_available=False, env={})
    assert r["backend"] == "refused" and "Nothing was written to a sheet" in r["message"]
    assert sc.select_backend({"sheets": {"backend": "bogus"}}, env={})["backend"] == "refused"
    assert sc.select_backend(dict(SA, sheets={"backend": "bogus"}), env=SE)["backend"] == "csv"


def test_empty_tab_plan_and_read_step():
    rd = sc.read_step("SID", "In review")
    assert rd["tool"] == "read_range" and rd["arguments"]["ranges"] == [{"sheet": "In review", "cells": "A1:R"}]
    p = sc.plan_append([["", "BT-1"]], spreadsheet_id="SID", existing=[])
    a = p["arguments"]
    assert p["tool"] == "append_rows" and a["cells"] == "A3:R" and a["parseInput"] is True and a["insertRows"] is True
    assert a["values"][0] == rsw.REVIEW_QUEUE_HEADER and a["values"][1] == ["", "BT-1"] and p["header_written"]
    resp = {"updates": {"updatedRange": "'In review'!A3:R4"}}
    assert sc.start_row_from_response(resp, p) == 4


def test_existing_rows_plan_matches_fake_append_and_dedupe():
    existing = [[], [], rsw.REVIEW_QUEUE_HEADER, ["", "BT-1"]]
    rows = rf.in_review_rows(ITEMS, "snap_demo", "2026-10-16")
    p = sc.plan_append(rows, spreadsheet_id="SID", existing=existing, dedupe_key=rf._row_key)
    assert not p["header_written"] and p["arguments"]["values"] == rows
    assert rows[0][3] == "'1234567890123456789" and rows[0][13] == "'2026-10-16"
    # executing the plan on a fake sheet == what the google_api writer produces on an identical sheet
    a, b = FakeSheet(existing), FakeSheet(existing)
    resp = a.append(spreadsheetId="SID", range=f"'{p['arguments']['sheet']}'!{p['arguments']['cells']}",
                    valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
                    body={"values": p["arguments"]["values"]}).execute()
    rsw.write_rows_to_sheet(rows, spreadsheet_id="SID", service=b, dedupe_key=rf._row_key)
    assert a.rows == b.rows and sc.start_row_from_response(resp, p) == 5
    # sheet read back (no apostrophe) -> dedupe -> nothing to append
    again = a.rows
    assert sc.plan_append(rows, spreadsheet_id="SID", existing=[[c.lstrip("'") for c in r] for r in again],
                          dedupe_key=rf._row_key) is None


def test_rows_from_read_result_formats():
    content = "\n\nSelect,Review ID\n,BT-1\n\n"
    res = {"spreadsheetId": "SID", "ranges": [{"sheet": "In review", "content": content}]}
    assert sc.rows_from_read_result(res) == [[], [], ["Select", "Review ID"], ["", "BT-1"]]
    assert sc.rows_from_read_result(json.dumps(res)) == sc.rows_from_read_result(content)
    # a saved tool result with text around the JSON (found in the real-sheet run) still parses as JSON
    assert sc.rows_from_read_result("tool output:\n" + json.dumps(res) + "\n") == sc.rows_from_read_result(res)


def test_in_review_plan_end_to_end(rv):
    p = sc.in_review_plan(UK, rv["s2"], spreadsheet_id="SID", existing=[], root=rv["root"])
    vals = p["arguments"]["values"]
    assert vals[0] == rsw.REVIEW_QUEUE_HEADER and {r[10] for r in vals[1:]} == {"In review"}
    assert [r[16] for r in vals[1:]].count("GRAVEYARD_RETURN") == 3


# ---------- write_in_review through the connector (default) ----------
def _boom_service():
    class Boom:
        def __getattr__(s, n): raise AssertionError("google_api must not be called on the connector path")
    return Boom()


def test_write_in_review_default_returns_connector_plan_no_google_call(rv, monkeypatch):
    monkeypatch.setattr(rsw, "_build_service", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no api")))
    o1 = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", service=_boom_service())
    assert o1["sheet"]["backend"] == "connector" and o1["sheet"]["read"]["tool"] == "read_range"
    assert "plan" not in o1["sheet"] and o1["csv"].endswith(".csv")   # local CSV still written
    o2 = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", existing=[], service=_boom_service())
    plan = o2["sheet"]["plan"]
    assert plan["tool"] == "append_rows" and plan["header_written"] and plan["rows_written"] == 4
    a = plan["arguments"]
    assert a["parseInput"] is True and a["insertRows"] is True and a["sheet"] == rsw.REVIEW_QUEUE_TAB
    data = a["values"][1:]
    assert {r[10] for r in data} == {"In review"} and "GRAVEYARD_RETURN" in {r[16] for r in data}
    assert all(str(r[3]).startswith("'") and str(r[13]).startswith("'") for r in data)


def test_write_in_review_dedupe_across_plan_rounds(rv):
    sh = FakeSheet([["Title"], [], rsw.REVIEW_QUEUE_HEADER, ["", "BT-old", "", "2000000999", "@someone"]])
    p1 = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", existing=sh.rows)["sheet"]["plan"]
    assert p1 and not p1["header_written"]
    # the sheet shows text markers stripped, as the connector reads it back
    sh.rows += [[str(c).lstrip("'") for c in r] for r in p1["arguments"]["values"]]
    p2 = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID",
                            existing={"ranges": [{"content": _csv(sh.rows)}]})["sheet"]["plan"]
    assert p2 is None and sh.rows[3][1] == "BT-old"


def test_write_in_review_fallback_rules(rv):
    svc = FakeSheet([])
    g = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", service=svc,
                           cfg={"runtime": "standalone", "sheets": {"backend": "google_api"}},
                           env={rsw.CREDENTIALS_ENV: "k", "BOT_TERMINATOR_STANDALONE": "1"})
    assert len(svc.rows) == 7 and g["sheet"]["start_row"] == 4                    # explicit google_api
    import preflight, pytest
    for e in ({}, {rsw.OAUTH_CLIENT_ENV: "c"}):   # connector chosen but not connected: refuse, never fall back
        with pytest.raises(preflight.PreflightError, match="Google Sheets isn't connected"):
            rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", service=FakeSheet([]),
                               connector_available=False, env=e)
    n = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID",
                           cfg={"runtime": "standalone", "sheets": {"backend": "google_api"}},
                           env={"BOT_TERMINATOR_STANDALONE": "1"})
    assert n["sheet"]["backend"] == "csv" and n["sheet"]["message"]
    x = rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID",
                           cfg={"runtime": "standalone", "sheets": {"backend": "csv"}}, env={"BOT_TERMINATOR_STANDALONE": "1"})
    assert x["sheet"]["backend"] == "csv" and x["sheet"]["message"]
    for b in ("google_api", "csv"):   # Grok Bot runtime: these backends are refused, not honored
        with pytest.raises(preflight.PreflightError, match="isn't allowed in Grok Bot"):
            rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="SID", cfg={"sheets": {"backend": b}},
                               env={rsw.CREDENTIALS_ENV: "k"})
    assert "sheet" not in rf.write_in_review(UK, rv["s2"], rv["root"])            # no sheet id: CSV only


def _csv(rows):
    import csv as _c, io as _io
    b = _io.StringIO(); _c.writer(b).writerows(rows); return b.getvalue()
