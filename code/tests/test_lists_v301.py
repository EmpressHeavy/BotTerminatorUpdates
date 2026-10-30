"""v3.0.1: calibration, batches, deep inspection, mutual, links, watch, scope card, Protected Lists.
Made-up generic demo lists/owners only; never X."""
import io, json, sys, datetime as dt
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st, lists_scan as ls, list_cards as lc, list_runner as lr, removal_runner as rr, sheet_layout
from preflight_helpers import confirmed
from test_lists import ListAdapter

UK = "demo_v301"


@pytest.fixture
def root(tmp_path):
    d = st.user_data_root(UK, tmp_path); d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"user_key": UK, "runtime": "grokbot", "connections": confirmed(),
        "owner_x_handle": "@demo_me", "data_root_relative": f"data/users/{UK}", "time_zone": "America/Los_Angeles",
        "daily_removal_cap": 10, "lists": {"enabled": True}}))
    return tmp_path


def T(name, desc=""):
    return ls.classify_list({"name": name, "description": desc})


@pytest.mark.parametrize("name", ["I've got my eye on you!", "Reply guys", "Perfect family", "Rust", "AI", "Tesla",
                                  "friends", "watch list", "Watchlist", "People to watch", "Space"])
def test_playful_and_plain_names_are_ok(name):
    t = T(name)
    assert t["tone"] == ls.OK and not t["flagged"], name


@pytest.mark.parametrize("name,desc", [("Spam bot ring", ""), ("Scammers", ""), ("Blocklist", "mass block these"),
                                       ("Clowns to dogpile", ""), ("x", "accounts to harass"), ("Haters", "")])
def test_really_negative_is_flagged(name, desc):
    assert T(name, desc)["tone"] == ls.NEGATIVE


@pytest.mark.parametrize("name,desc", [("Bots", ""), ("Fake accounts?", ""), ("Anti-spam researchers", "spam research"),
                                       ("Bot builders", "")])
def test_ambiguous_is_review_not_flagged(name, desc):
    t = T(name, desc)
    assert t["tone"] == ls.REVIEW and t["watch"] and not t["flagged"]


def test_mutual_owner_negative_is_watch_not_flag():
    t = ls.normalize({"list_id": "9", "name": "Scammers", "owner_handle": "o", "owner_i_follow": True,
                      "owner_follows_me": True})
    assert t["tone"] == ls.REVIEW and t["watch"] and t["mutual"] is True and not t["flagged"]
    assert ls.mutual({"owner_i_follow": True, "owner_follows_me": False}) is False
    assert ls.mutual({}) == ls.NA


def rows(n, **kw):
    return [dict({"name": f"Topic {i}", "owner_handle": f"demo_owner_{i}", "member_count": i}, **kw) for i in range(n)]


def test_batches_cover_every_list_and_advance(root):
    snap = ls.build_snapshot(UK, root, records=rows(12))
    sid = snap["snapshot_id"]
    cards = lc.build_cards(UK, sid, root)
    assert [len(c["card_spec"]["options"]) - 2 for c in cards] == [4, 4, 4] and cards[0]["of"] == 3
    b = lc.next_batch(UK, sid, root); assert b["card"] == 1
    assert lc.record_answer(UK, sid, 1, [lc.REMOVE_BTN], root=root)["skipped"]  # nothing picked: all skipped
    assert lc.next_batch(UK, sid, root)["card"] == 2
    r = lc.record_answer(UK, sid, 2, ["2", lc.REMOVE_BTN], root=root)
    assert r["authorized"] == ["Topic 3"]   # name order: 0,1,10,11 | 2,3,4,5 | 6,7,8,9 and r["next_card"] == 3
    assert lc.record_answer(UK, sid, 3, ["1"], root=root)["recorded"] is False   # no button -> no advance
    assert lc.next_batch(UK, sid, root)["card"] == 3
    lc.record_answer(UK, sid, 3, [lc.KEEP_BTN], root=root)
    assert lc.next_batch(UK, sid, root)["done"] is True


def test_owner_filled_from_list_page_and_plan_opens_every_list(root):
    memb = [{"name": "Rust"}, {"name": "AI", "followers_including": "12 followers including @someone"},
            {"name": "Gardening", "owner_handle": "demo_owner_g"}]
    plan = ls.inspection_plan(memb)
    assert len(plan) == 3 and plan[1]["owner_missing"] and "click row 2" in plan[1]["open"]
    insp = [{"row_index": 1, "url": "https://x.com/i/lists/777", "name": "AI", "description": "AI researchers",
             "owner_name": "Demo Person", "owner_handle": "demo_owner_ai", "member_count": 50,
             "sample_members": ["@demo_m1"], "owner_i_follow": False, "owner_follows_me": True}]
    snap = ls.build_snapshot(UK, root, records=memb, inspections=insp)
    ai = next(r for r in snap["lists"] if r["name"] == "AI")
    assert ai["list_id"] == "777" and ai["owner_handle"] == "@demo_owner_ai" and ai["deep_inspected"]
    assert ai["owner_url"] == "https://x.com/demo_owner_ai" and ai["mutual"] is False
    assert len(snap["lists"]) == 3


def test_links_message_renders_link_handle_members_mutual(root):
    snap = ls.build_snapshot(UK, root, records=[
        {"list_id": "1", "name": "Rust", "owner_handle": "demo_a", "owner_name": "Demo A", "member_count": 9,
         "owner_i_follow": True, "owner_follows_me": True},
        {"list_id": "2", "name": "Tesla", "owner_handle": "demo_b", "member_count": 4, "owner_i_follow": False}])
    msg = lc.build_cards(UK, snap["snapshot_id"], root)[0]["links_message"]
    assert "Rust — https://x.com/i/lists/1\n   Owner: @demo_a (Demo A) — https://x.com/demo_a" in msg
    assert "Members: 9 · You follow each other (mutual): yes" in msg and "mutual): no" in msg
    assert "watch: owner is a mutual" in msg and msg.count(lc.SOFT_BLOCK_WARNING) == 1


def test_watch_state_persists_and_rechecks(root):
    ls.build_snapshot(UK, root, records=[{"list_id": "1", "name": "Bots"}, {"list_id": "2", "name": "Rust"}],
                      when="2026-10-01T09:00:00-07:00")
    w = json.loads((st.user_data_root(UK, root) / "lists_watch.json").read_text())
    assert list(w) == ["1"]
    s2 = ls.build_snapshot(UK, root, records=[{"list_id": "1", "name": "Bots", "description": "spam bot ring"}],
                           when="2026-10-02T09:00:00-07:00")
    assert s2["rechecks"][0]["was"] == ls.REVIEW and s2["rechecks"][0]["now"] == ls.NEGATIVE


def test_frozen_snapshot_enforced(root):
    snap = ls.build_snapshot(UK, root, records=[{"list_id": "101", "name": "Spammers and scammers", "owner_handle": "demo_owner_a"}])
    sid = snap["snapshot_id"]
    lc.build_cards(UK, sid, root); lc.record_answer(UK, sid, 1, ["1", lc.REMOVE_BTN], root=root)
    p = st.user_data_root(UK, root) / "lists" / sid / "lists.json"
    body = json.loads(p.read_text()); body["lists"][0]["name"] = "changed"; p.write_text(json.dumps(body))
    with pytest.raises(rr.RefusedError, match="changed"):
        lr.run_list_removals(UK, sid, ListAdapter(), root=root, sleep=lambda s: None, out=io.StringIO())


def test_scope_card_recorded_and_enforced(root):
    card = ls.scope_card()
    assert [o["label"] for o in card["options"]] == ["Only lists from people I don't follow back", "Show all lists"]
    with pytest.raises(ValueError):
        ls.parse_scope("")
    recs = [{"list_id": "101", "name": "Spammers and scammers", "owner_handle": "demo_owner_a", "owner_i_follow": True},
            {"list_id": "102", "name": "Gardening", "owner_handle": "demo_owner_b", "owner_i_follow": False}]
    sc = ls.parse_scope("Only lists from people I don't follow back")
    snap = ls.build_snapshot(UK, root, records=recs, scope=sc)
    assert ls.load(UK, snap["snapshot_id"], root)["scope"] == ls.SCOPE_NOT_FOLLOWED
    cards = lc.build_cards(UK, snap["snapshot_id"], root)
    assert "Gardening" in json.dumps(cards) and "Spammers" not in json.dumps(cards)
    all_snap = ls.build_snapshot(UK, root, records=recs, scope=ls.SCOPE_ALL,
                                 when=(dt.datetime.now().astimezone() + dt.timedelta(seconds=3)).isoformat())
    assert "Spammers" in json.dumps(lc.build_cards(UK, all_snap["snapshot_id"], root))


def test_protected_lists_not_reinspected_and_released_on_unfollow(root):
    recs = [{"list_id": "1", "name": "Rust", "url": "https://x.com/i/lists/1", "owner_handle": "demo_f", "owner_i_follow": True},
            {"list_id": "2", "name": "Tesla", "url": "https://x.com/i/lists/2", "owner_handle": "demo_g", "owner_i_follow": False}]
    ls.build_snapshot(UK, root, records=recs)
    assert list(ls.load_protected(UK, root)) == ["1"]
    assert [p["name"] for p in ls.inspection_plan(recs, UK, root)] == ["Tesla"]       # protected not re-inspected
    assert ls.recheck_protected(UK, {"@demo_f": True}, root) == []
    rel = ls.recheck_protected(UK, {"@demo_f": False}, root, when="2026-10-22T15:00:00-07:00")
    assert rel[0]["status"] == "PROTECTED_LIST_RELEASED" and rel[0]["at"] == "2026-10-22T15:00:00-07:00"
    assert ls.load_protected(UK, root) == {}
    assert len(ls.inspection_plan(recs, UK, root)) == 2                                # back to normal review
    h = [json.loads(l) for l in st.history_path(root, user_key=UK).read_text().splitlines()]
    rows_ = sheet_layout.protected_rows(ls.load_protected(UK, root), h)
    assert rows_[0][3].startswith("Left") and rows_[0][6] == "2026-10-22T15:00:00-07:00"
    assert "Protected Lists" in sheet_layout.HEADERS
