"""Graveyard returns card flow: notice, disclaimer, links list, chunked block cards, answer recording."""
import io, json, sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import graveyard_return_cards as grc
import graveyard_returns as gr
import build_candidate_cards as bcc
import storage as st
from removal_test_adapter import DryTestAdapter
from test_graveyard_returns import env, UK, set_cfg, hist  # noqa: F401  (reuse the scan->remove->rescan fixture)

TZ = ZoneInfo("America/Los_Angeles")


def fake(n):
    return [{"handle": f"demo_{i:02d}", "x_user_id": str(2000000000 + i), "removed_at": "2026-10-03T12:00:00-07:00",
             "returned_at": "2026-10-16T19:00:00-07:00", "previous_handle": None} for i in range(1, n + 1)]


def test_no_returnees_no_card():
    f = grc.build_flow([])
    assert f == {"messages": [], "cards": [], "numbering": {"accounts": [], "cards": {}}}
    assert grc.notice_text(0) is None


def test_singular_notice_and_exact_disclaimer():
    f = grc.build_flow(fake(1), tz=TZ)
    assert f["messages"][0] == "1 bot has reattached to your account, and I have it recorded in the Graveyard."
    assert f["messages"][1] == ("Heads up: these accounts are repeat offenders. I removed them before and they "
                                "followed you again. This round won't just remove them as followers. They'll be "
                                "blocked so they can't come back and reattach.")
    assert grc.notice_text(7) == "7 bots have reattached to your account, and I have them recorded in the Graveyard."


def test_five_returnees_one_card_with_mark_all():
    f = grc.build_flow(fake(5), tz=TZ)
    assert len(f["cards"]) == 1
    c = f["cards"][0]
    assert c["multiSelect"] is True and c["allowCustom"] is False and len(c["options"]) == 6
    assert c["options"][-1] == {"label": "Mark all for blocking", "value": "mark_all", "style": "danger"}
    assert c["prompt"] == ("Graveyard returns (1 of 1): block these repeat followers? "
                           "Unmarked accounts will be kept in review.")
    # every card shows post/follower/following counts (beta feedback 2026-10-20)
    assert c["options"][0]["label"] == "1. @demo_01 — posts/followers/following: Not available — removed Oct 3, followed again"


def test_twelve_returnees_cards_5_5_2_continuous_numbering():
    f = grc.build_flow(fake(12), tz=TZ)
    assert [len(c["options"]) - 1 for c in f["cards"]] == [5, 5, 2]
    assert all(len(c["options"]) <= grc.MAX_OPTIONS for c in f["cards"])
    assert f["numbering"]["cards"] == {"1": [1, 2, 3, 4, 5], "2": [6, 7, 8, 9, 10], "3": [11, 12]}
    assert f["cards"][2]["options"][0]["label"].startswith("11. @demo_11")
    assert f["cards"][1]["prompt"].startswith("Graveyard returns (2 of 3):")
    lines = f["messages"][2].splitlines()
    assert len(lines) == 12 and lines[10].startswith("11. [@demo_11](https://x.com/demo_11)")


def test_renamed_and_missing_dates():
    r = fake(2); r[0]["previous_handle"] = "old_name"; r[1]["removed_at"] = None; r[1]["returned_at"] = ""
    f = grc.build_flow(r, tz=TZ)
    l1, l2 = f["messages"][2].splitlines()
    assert l1 == ("1. [@demo_01](https://x.com/demo_01) — removed Oct 3, came back Oct 16 (new handle, was @old_name)")
    assert l2 == "2. [@demo_02](https://x.com/demo_02) — removed Not available, came back Not available"
    assert f["cards"][0]["options"][0]["label"].endswith("followed again (new handle)")
    assert "Not available" in f["cards"][0]["options"][1]["label"]


def test_parse_answer():
    nums = [6, 7, 8, 9, 10]
    assert grc.parse_answer(["7. @x — removed Oct 3, followed again", "9"], nums) == [7, 9]
    assert grc.parse_answer(["Mark all for blocking"], nums) == nums
    assert grc.parse_answer(["mark_all"], nums) == nums
    assert grc.parse_answer([], nums) == [] and grc.parse_answer(None, nums) == []
    assert grc.parse_answer(["2", "11"], nums) == []          # numbers off this card are ignored


def test_snapshot_flow_records_authorization_and_unmarked_never_blocked(env):
    flow = grc.build_flow_for_snapshot(UK, env["s2"], env["root"])
    assert flow["messages"][0].startswith("5 bots have reattached")
    assert "new handle, was @demo_01" in flow["messages"][2]
    p = grc.numbering_path(UK, env["s2"], env["root"])
    assert p.exists() and oct(p.stat().st_mode & 0o777) == "0o600"
    res = grc.record_card_answer(UK, env["s2"], 1, ["2. @demo_02 — removed", "4"], root=env["root"])
    assert res["authorized"] == [2, 4] and res["kept_in_review"] == [1, 3, 5]
    assert {a["handle"] for a in grc.kept_in_review(UK, env["s2"], env["root"])} == {"demo_01_renamed", "demo_03", "demo_11"}
    a = DryTestAdapter()
    s = gr.run_blocks(UK, env["s2"], a, root=env["root"], sleep=lambda x: None, out=io.StringIO())
    blocked = [c[1] for c in a.calls if c[0] == "block"]
    rets = {r["n"]: r["handle"] for r in flow["numbering"]["accounts"]}
    assert s["blocked"] == 2 and blocked == [rets[2], rets[4]]
    assert "GRAVEYARD_RETURN_KEPT_IN_REVIEW" in [e["status"] for e in hist(env)]


def test_mark_all_and_empty_answer(env):
    grc.build_flow_for_snapshot(UK, env["s2"], env["root"])
    assert grc.record_card_answer(UK, env["s2"], 1, [], root=env["root"])["authorized"] == []
    with pytest.raises(Exception, match="no recorded authorization"):
        gr.run_blocks(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda x: None, out=io.StringIO())
    assert grc.record_card_answer(UK, env["s2"], 1, ["Mark all for blocking"], root=env["root"])["authorized"] == [1, 2, 3, 4, 5]
    assert gr.run_blocks(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda x: None,
                         out=io.StringIO())["blocked"] == 5


def test_auto_block_shows_notice_but_no_cards(env):
    set_cfg(env, graveyard_return_action="auto_block")
    f = grc.build_flow_for_snapshot(UK, env["s2"], env["root"])
    assert f["messages"][0].startswith("5 bots") and f["messages"][1] == grc.DISCLAIMER and f["cards"] == []


def test_removal_cards_unchanged(env):
    c = bcc.build_cards_for_snapshot(UK, env["s2"], env["root"])
    assert c["card_ui"]["select_all_label"] == "Mark all for termination"
    assert {a["handle"] for a in c["accounts"]} == {"demo_13", "demo_14"}
    assert all(len(v) <= 5 for v in c["cards"].values())
