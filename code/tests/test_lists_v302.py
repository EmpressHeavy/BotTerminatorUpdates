"""v3.0.2: two action buttons per batch, Kept Lists, final skipped card, List Graveyard, product names.
Made-up generic demo lists only; never X."""
import io, json, sys, datetime as dt
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st, lists_scan as ls, list_cards as lc, list_runner as lr, sheet_layout
from test_lists_v301 import root  # noqa: F401  (fixture)
from test_lists import ListAdapter

UK = "demo_v301"


def recs(n):
    return [{"list_id": str(100 + i), "name": f"Topic {chr(65 + i)}", "owner_handle": f"demo_owner_{i}", "owner_id": str(9000 + i),
             "member_count": i} for i in range(n)]


def hist(root):
    return [json.loads(l) for l in st.history_path(root, user_key=UK).read_text().splitlines()]


def test_card_buttons_and_wording(root):
    sid = ls.build_snapshot(UK, root, records=recs(7))["snapshot_id"]
    c = lc.build_cards(UK, sid, root)[0]
    labels = [o["label"] for o in c["card_spec"]["options"]]
    assert labels[-2:] == ["Remove me from these lists", "Keep all these lists"] and "Done" not in labels
    assert c["card_spec"]["multiSelect"] and lc.SOFT_BLOCK_WARNING not in json.dumps(c["card_spec"])
    assert c["links_message"].startswith(lc.SOFT_BLOCK_WARNING)


def test_remove_skips_unselected_keep_all_keeps_batch_and_both_advance(root):
    sid = ls.build_snapshot(UK, root, records=recs(7))["snapshot_id"]
    lc.build_cards(UK, sid, root)
    r = lc.record_answer(UK, sid, 1, ["2", lc.REMOVE_BTN], root=root)
    assert r["authorized"] == ["Topic B"] and r["skipped"] == ["Topic A", "Topic C", "Topic D"]
    assert r["kept"] == [] and lc.next_batch(UK, sid, root)["card"] == 2
    assert ls.load_kept(UK, root) == {}
    r2 = lc.record_answer(UK, sid, 2, ["1", lc.KEEP_BTN], root=root)      # selection ignored: keep all
    assert r2["kept"] == ["Topic E", "Topic F", "Topic G"] and r2["authorized"] == []
    assert lc.next_batch(UK, sid, root)["done"] is True
    assert lc.record_answer(UK, sid, 1, [lc.REMOVE_BTN, lc.KEEP_BTN], root=root)["recorded"] is False
    rows = sheet_layout.kept_rows(ls.load_kept(UK, root))
    assert rows[0][:3] == ["Topic E", "https://x.com/i/lists/104", "@demo_owner_4"] and rows[0][4] == sid
    assert sum(e["status"] == "LIST_KEPT" for e in hist(root)) == 3


def test_final_skipped_card_and_in_review(root):
    sid = ls.build_snapshot(UK, root, records=recs(3))["snapshot_id"]
    lc.build_cards(UK, sid, root)
    assert lc.final_skipped_card(UK, sid, root) is None                    # not after the last batch yet
    lc.record_answer(UK, sid, 1, [lc.REMOVE_BTN], root=root)                # all 3 skipped
    f = lc.final_skipped_card(UK, sid, root)
    assert f["card_spec"]["prompt"] == "Some lists were skipped during review. Keep these, or select ones to remove?"
    assert [o["label"] for o in f["card_spec"]["options"]][-2:] == ["Remove me from selected lists", "Keep all skipped lists"]
    r = lc.record_final_answer(UK, sid, ["3", lc.FINAL_REMOVE_BTN], root=root)
    assert r["authorized"] == ["Topic C"] and r["in_review"] == ["Topic A", "Topic B"] and r["kept"] == []
    assert lc.final_skipped_card(UK, sid, root) is None and ls.load_kept(UK, root) == {}
    res = lr.run_list_removals(UK, sid, ListAdapter(), root=root, sleep=lambda s: None, out=io.StringIO())
    assert [x for x in res["left"]] and any(e["status"] == "LIST_SOFT_BLOCKED" and e["list_id"] == "102" for e in hist(root))
    g = sheet_layout.list_rows(hist(root))
    assert g and g[0][2] == "Topic C" and sheet_layout.LISTS == "List Graveyard"


def test_final_keep_all_skipped(root):
    sid = ls.build_snapshot(UK, root, records=recs(2))["snapshot_id"]
    lc.build_cards(UK, sid, root); lc.record_answer(UK, sid, 1, [lc.REMOVE_BTN], root=root)
    assert lc.record_final_answer(UK, sid, [lc.FINAL_KEEP_BTN], root=root)["kept"] == ["Topic A", "Topic B"]
    assert len(ls.load_kept(UK, root)) == 2


def test_kept_not_reviewed_again_unless_owner_or_name_changes(root):
    sid = ls.build_snapshot(UK, root, records=recs(2), when="2026-10-01T09:00:00-07:00")["snapshot_id"]
    lc.build_cards(UK, sid, root); lc.record_answer(UK, sid, 1, [lc.KEEP_BTN], root=root)
    s2 = ls.build_snapshot(UK, root, records=recs(2), when="2026-10-02T09:00:00-07:00")
    assert lc.build_cards(UK, s2["snapshot_id"], root) == []
    changed = recs(2); changed[1]["owner_handle"] = "demo_new_owner"
    s3 = ls.build_snapshot(UK, root, records=changed, when="2026-10-03T09:00:00-07:00")
    assert [k["key"] for k in s3["kept_rechecks"]] == ["101"]
    assert "Topic B" in json.dumps(lc.build_cards(UK, s3["snapshot_id"], root))
    assert any(e["status"] == "KEPT_LIST_RECHECK" for e in hist(root))


def test_returnee_recheck_uses_graveyard_history(root):
    sid = ls.build_snapshot(UK, root, records=recs(1))["snapshot_id"]
    lc.build_cards(UK, sid, root); lc.record_answer(UK, sid, 1, ["1", lc.REMOVE_BTN], root=root)
    a = ListAdapter(); a.on["100"] = True
    lr.run_list_removals(UK, sid, a, root=root, sleep=lambda s: None, out=io.StringIO())
    assert any(e["status"] == "LIST_SOFT_BLOCKED" for e in hist(root))
    s2 = ls.build_snapshot(UK, root, records=[dict(recs(1)[0], list_id="900", name="Another")],
                           when=(dt.datetime.now().astimezone() + dt.timedelta(seconds=3)).isoformat())
    assert [r["owner_handle"] for r in lr.detect_returns(UK, s2["snapshot_id"], root)] == ["@demo_owner_0"]


@pytest.mark.parametrize("name,desc", [("Grok Bot Creators", "for Grok Bot creators and enthusiasts"),
                                       ("GrokBot builders", ""), ("Grok Bots", "")])
def test_grok_bot_is_a_product_name(name, desc):
    assert ls.classify_list({"name": name, "description": desc})["tone"] == ls.OK
    assert ls.classify_list({"name": "Grok Bot fans and spam bots", "description": ""})["tone"] != ls.OK
