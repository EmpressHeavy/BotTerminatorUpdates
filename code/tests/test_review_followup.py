"""Accounts-in-review follow-up: unmarked accounts from removal cards AND Graveyard returns cards."""
import csv, io, json, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st
import build_candidate_cards as bcc
import record_chat_selection as rcs
import removal_runner as rr
import graveyard_returns as gr
import graveyard_return_cards as grc
import review_followup as rf
from removal_test_adapter import DryTestAdapter
from test_graveyard_returns import env, UK, set_cfg, hist  # noqa: F401


@pytest.fixture
def rv(env):
    """Removal card: pick the first candidate only (second stays unmarked). Returns card: pick R2, R4."""
    cards = bcc.build_cards_for_snapshot(UK, env["s2"], env["root"])
    nums = cards["cards"]["1"]
    b = rcs.build(env["s2"], 1, nums, str(nums[0]), user_key=UK)
    rcs.append_history(b["history_entry"], user_key=UK)
    grc.build_flow_for_snapshot(UK, env["s2"], env["root"])
    grc.record_card_answer(UK, env["s2"], 1, ["2", "4"], root=env["root"])
    env["unmarked_candidate"] = next(a["handle"] for a in cards["accounts"] if a["chat_no"] == nums[1]).lstrip("@")
    return env


def _run_rm(env, a):
    return rr.run_removals(UK, env["s2"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())


def _run_bl(env, a):
    return gr.run_blocks(UK, env["s2"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())


def test_collects_both_sources_in_review(rv):
    items = rf.collect_in_review(UK, rv["s2"], rv["root"])
    assert all(i["status"] == "IN_REVIEW" for i in items)
    assert [(i["type"], i["handle"]) for i in items] == [("CANDIDATE", rv["unmarked_candidate"]),
        ("GRAVEYARD_RETURN", "demo_01_renamed"), ("GRAVEYARD_RETURN", "demo_03"), ("GRAVEYARD_RETURN", "demo_11")]
    flow = rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    c = flow["cards"][0]
    assert len(flow["cards"]) == 1 and len(c["options"]) == 5 <= rf.MAX_OPTIONS
    assert c["options"][0]["label"].endswith("— remove") and c["options"][1]["label"].endswith("block (Graveyard return)")
    assert c["options"][-1]["label"] == "Mark all for termination" and c["allowCustom"] is False
    assert not st.load_always_keep(rv["root"], user_key=UK)   # never auto-moved anywhere


def test_unmarked_written_in_review_not_keepers(rv):
    out = rf.write_in_review(UK, rv["s2"], rv["root"])
    rows = list(csv.reader(open(out["csv"])))
    assert rows[0][10] == "Status" and len(rows) == 5
    assert {r[10] for r in rows[1:]} == {"In review"}
    assert [r[16] for r in rows[1:]] == ["CANDIDATE", "GRAVEYARD_RETURN", "GRAVEYARD_RETURN", "GRAVEYARD_RETURN"]
    assert "BLOCK" in rows[2][17] and "REMOVE" in rows[1][17]
    assert not any("Keep" in c for r in rows[1:] for c in r[10:11])

    class Svc:  # mock Sheets API
        def __init__(s): s.body = None
        def spreadsheets(s): return s
        def values(s): return s
        def get(s, spreadsheetId, range): return s  # empty tab (append-only writer reads existing rows first)
        def append(s, spreadsheetId, range, valueInputOption, insertDataOption, body):
            s.body = {"data": [{"range": range, "values": body["values"]}]}; return s
        def execute(s): return {}
    svc = Svc()
    rf.write_in_review(UK, rv["s2"], rv["root"], spreadsheet_id="sheet123", first_row=20, service=svc,
                       cfg={"runtime": "standalone", "sheets": {"backend": "google_api"}},
                       env={"BOT_TERMINATOR_GOOGLE_CREDENTIALS": "x", "BOT_TERMINATOR_STANDALONE": "1"})  # explicit google_api fallback (default is now the connector)
    ranges = [d["range"] for d in svc.body["data"]]
    assert all(r.startswith("'In review'!") for r in ranges) and "Keepers" not in json.dumps(svc.body)


def test_terminate_candidate_removal_only_and_returnee_block_only(rv):
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    res = rf.record_terminate(UK, rv["s2"], 1, ["1", "3"], root=rv["root"])  # candidate + demo_03 returnee
    assert res["removal_authorized"] == [1] and res["block_authorized"] == [3]
    a = DryTestAdapter(); s = _run_rm(rv, a)
    removed = [c[1] for c in a.calls if c[0] == "remove"]
    assert rv["unmarked_candidate"] in removed and "demo_03" not in removed and not [c for c in a.calls if c[0] == "block"]
    b = DryTestAdapter(); _run_bl(rv, b)
    blocked = [c[1] for c in b.calls if c[0] == "block"]
    assert "demo_03" in blocked and rv["unmarked_candidate"] not in blocked and not [c for c in b.calls if c[0] == "remove"]
    assert res["keep_card"]["kind"] == "keep" and [o["value"] for o in res["keep_card"]["options"]] == ["2", "4", "always_keep"]


def test_mark_all_terminates_whole_card(rv):
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    res = rf.record_terminate(UK, rv["s2"], 1, ["Mark all for termination"], root=rv["root"])
    assert res["removal_authorized"] == [1] and res["block_authorized"] == [2, 3, 4] and res["keep_card"] is None


def test_keep_not_a_bot_always_keep_and_untouched_stays(rv):
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    t = rf.record_terminate(UK, rv["s2"], 1, [], root=rv["root"])
    assert t["removal_authorized"] == [] and t["block_authorized"] == [] and t["still_in_review"] == [1, 2, 3, 4]
    k = rf.record_keep(UK, rv["s2"], 1, ["2"], root=rv["root"])
    assert k["kept"] == [2] and k["kind"] == "NOT_A_BOT" and k["sheet_ops"][0]["sheet"] == "Keepers"
    assert not st.load_always_keep(rv["root"], user_key=UK)
    left = {i["handle"] for i in rf.collect_in_review(UK, rv["s2"], rv["root"])}
    assert left == {rv["unmarked_candidate"], "demo_03", "demo_11"}
    # a later card: Always Keep toggle
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    k2 = rf.record_keep(UK, rv["s2"], 1, ["3", "Add the ones I keep to Always Keep"], root=rv["root"])
    assert k2["kind"] == "ALWAYS_KEEP"
    ak = st.load_always_keep(rv["root"], user_key=UK)
    assert len(ak) == 1 and ak[0]["username"] == "demo_11"
    assert {i["handle"] for i in rf.collect_in_review(UK, rv["s2"], rv["root"])} == {rv["unmarked_candidate"], "demo_03"}
    # nothing was authorized to remove or block
    b = DryTestAdapter(); _run_bl(rv, b)   # only R2/R4 (authorized on the returns card) are blocked
    assert sorted(c[1] for c in b.calls if c[0] == "block") == ["demo_02", "demo_04"]
    a = DryTestAdapter(); _run_rm(rv, a)   # the first-picked candidate only; the unmarked one is never removed
    assert rv["unmarked_candidate"] not in [c[1] for c in a.calls if c[0] == "remove"]
    statuses = [e["status"] for e in hist(rv)]
    assert "REVIEW_DECISION" in statuses


def test_protections_still_recheck_after_review_terminate(rv):
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    rf.record_terminate(UK, rv["s2"], 1, ["Mark all for termination"], root=rv["root"])
    fresh = {rv["unmarked_candidate"]: {"i_follow": True}, "demo_03": {"verified_type": None},
             "demo_01_renamed": {"i_follow": None}, "demo_11": {"verified_type": "blue"}}
    a = DryTestAdapter(fresh=fresh); s = _run_rm(rv, a)
    assert rv["unmarked_candidate"] not in [c[1] for c in a.calls if c[0] == "remove"]
    b = DryTestAdapter(fresh=fresh); sb = _run_bl(rv, b)
    blocked = [c[1] for c in b.calls if c[0] == "block"]
    assert not set(blocked) & {"demo_03", "demo_01_renamed", "demo_11"}


def test_manual_mode_review_terminate_needs_confirmation(rv):
    set_cfg(rv, operating_mode="review")
    rf.build_for_snapshot(UK, rv["s2"], rv["root"])
    rf.record_terminate(UK, rv["s2"], 1, ["1"], root=rv["root"])
    a = DryTestAdapter(); _run_rm(rv, a)
    assert rv["unmarked_candidate"] not in [c[1] for c in a.calls if c[0] == "remove"]


def test_old_final_review_card_decisions_are_honored(rv):
    sd = st.snapshot_dir(rv["s2"], rv["root"], user_key=UK)
    n = json.load(open(sd / "chat_numbering.json"))["accounts"][1]["chat_no"]
    res = rcs.build_final_review(rv["s2"], [n], f"Not a bot {n}", user_key=UK)
    rcs.append_history(res["history_entry"], user_key=UK)
    assert rv["unmarked_candidate"] not in {i["handle"] for i in rf.collect_in_review(UK, rv["s2"], rv["root"])}
