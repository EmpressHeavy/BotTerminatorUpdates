"""v3 lists feature. Made-up demo lists/owners only; a test-only adapter, never X."""
import datetime as dt, io, json, subprocess, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st
import lists_scan as ls
import list_cards as lc
import list_runner as lr
import removal_runner as rr
import sheet_layout, daily_routine, rules_book
from removal_runner import RemovalResult
from preflight_helpers import confirmed

UK = "demo_lists"
RAW = [
    {"list_id": "101", "name": "Spammers and scammers", "description": "", "owner_handle": "demo_owner_a",
     "owner_id": "5001", "member_count": 40, "follower_count": 2},
    {"list_id": "102", "name": "Best AI bots", "description": "bot builders I love", "owner_handle": "demo_owner_b",
     "owner_id": "5002", "member_count": 12},
    {"list_id": "103", "name": "Gardening", "description": "people who grow food", "owner_handle": "demo_owner_c",
     "owner_id": "5003", "member_count": 300, "follower_count": 20},
    {"list_id": "104", "name": "Clowns to dogpile", "owner_handle": "demo_owner_d", "owner_id": "5004",
     "owner_i_follow": True, "owner_follows_me": True},
    {"list_id": "105", "name": "Suspicious accounts", "owner_handle": "demo_owner_e", "owner_id": "5005"},
]


class ListAdapter:
    def __init__(self, results=None, stuck=()):
        self.on = {r["list_id"]: True for r in RAW}
        self.blocked = set()
        self.results = list(results or [])
        self.stuck = set(stuck)
        self.calls = []

    def list_state(self, r):
        return {"on_list": self.on.get(r["list_id"])}

    def owner_state(self, r):
        return {"blocked": r["owner_handle"] in self.blocked}

    def _res(self):
        return self.results.pop(0) if self.results else RemovalResult("ok", "")

    def block(self, r):
        self.calls.append(("block", r["owner_handle"])); res = self._res()
        if res.status == "ok":
            self.blocked.add(r["owner_handle"])
            if r["list_id"] not in self.stuck:
                self.on[r["list_id"]] = False
        return res

    def unblock(self, r):
        self.calls.append(("unblock", r["owner_handle"])); res = self._res()
        if res.status == "ok":
            self.blocked.discard(r["owner_handle"])
        return res

    def __getattr__(self, n):
        raise AssertionError(f"forbidden adapter call {n}")


@pytest.fixture
def env(tmp_path):
    d = st.user_data_root(UK, tmp_path); d.mkdir(parents=True)
    cfg = {"user_key": UK, "runtime": "grokbot", "connections": confirmed(), "owner_x_handle": "@demo_me",
           "data_root_relative": f"data/users/{UK}", "time_zone": "America/Los_Angeles", "daily_removal_cap": 10,
           "lists": {"enabled": True}}
    (d / "config.json").write_text(json.dumps(cfg))
    snap = ls.build_snapshot(UK, tmp_path, records=RAW)
    return {"root": tmp_path, "sid": snap["snapshot_id"], "snap": snap, "dir": d, "cfg": cfg}


def hist(env):
    return [json.loads(l) for l in st.history_path(env["root"], user_key=UK).read_text().splitlines()]


def by_id(env):
    return {r["list_id"]: r for r in env["snap"]["lists"]}


def test_negative_classification(env):
    t = {k: v["tone"] for k, v in by_id(env).items()}
    assert t == {"101": "NEGATIVE", "102": "REVIEW", "103": "OK", "104": "REVIEW", "105": "REVIEW"}
    assert by_id(env)["104"]["watch"] and not by_id(env)["104"]["flagged"]     # mutual owner: watch, not flagged
    assert by_id(env)["104"]["description"] == "Not available"
    assert by_id(env)["102"]["follower_count"] == "Not available"


def test_report_lists_all_with_negative_separate(env):
    rep = ls.report(env["snap"]["lists"])
    assert rep.startswith("You're on 5 lists.")
    assert rep.index("Negative lists (1)") < rep.index("Needs your look / watched (3)") < rep.index("Other lists (1)")
    assert "Gardening" in rep


def test_cards_and_warning_only_in_pre_card_message(env):
    cards = lc.build_cards(UK, env["sid"], env["root"])
    # 5 lists, CARD_SIZE 4: batch of 4 lists + 2 action buttons = 6 options (chat widget max), then 1 list + 2 buttons
    assert [len(c["card_spec"]["options"]) for c in cards] == [6, 3] and lc.CARD_SIZE == 4
    spec = cards[0]["card_spec"]
    assert spec["multiSelect"] and spec["allowCustom"] is False and [o["label"] for o in spec["options"][-2:]] == [lc.REMOVE_BTN, lc.KEEP_BTN]
    assert cards[0]["links_message"].startswith(lc.SOFT_BLOCK_WARNING)
    assert lc.SOFT_BLOCK_WARNING not in json.dumps(spec) and "mutual" not in json.dumps(spec).lower()
    assert "Gardening" in json.dumps(cards)                                # every list is reviewed
    # nowhere else in the shipped package (docs, templates, other code)
    phrases = ("removes the owner as your follower", "ends any follow")
    for p in list((ROOT / "src").rglob("*.py")) + list((ROOT / "templates").rglob("*")) + [ROOT / "README.md"]:
        if p.name == "list_cards.py" or not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        assert not any(x in txt for x in phrases), p
    src = (ROOT / "src/list_cards.py").read_text()
    assert sum(src.count(x) for x in phrases) == 2      # only the single SOFT_BLOCK_WARNING constant


def _select(env, nums, done=True):
    cards = lc.build_cards(UK, env["sid"], env["root"])
    return lc.record_answer(UK, env["sid"], 1, [str(n) for n in nums] + ([lc.REMOVE_BTN] if done else []), root=env["root"])


def test_nothing_without_done(env):
    r = _select(env, [2], done=False)
    assert r["recorded"] is False
    with pytest.raises(rr.RefusedError, match="Remove me"):
        lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())


def test_soft_block_verified_paced_capped(env):
    _select(env, [1, 2])
    sleeps = []
    a = ListAdapter()
    res = lr.run_list_removals(UK, env["sid"], a, root=env["root"], sleep=sleeps.append, out=io.StringIO())
    assert len(res["left"]) == 2 and sleeps == [lr.SOFT_BLOCK_WAIT_SECONDS, rr.PACING_SECONDS, lr.SOFT_BLOCK_WAIT_SECONDS] and res["actions_today"] == 4
    assert [c[0] for c in a.calls] == ["block", "unblock", "block", "unblock"]
    h = [e for e in hist(env) if e["status"] == "LIST_SOFT_BLOCKED"]
    assert all(e["verified"] and e["cap_weight"] == 2 for e in h)
    rows = sheet_layout.list_rows(hist(env))
    assert len(rows) == 2 and rows[0][2] and rows[0][3] == "'101" and rows[0][7] == env["sid"]
    assert dt.datetime.fromisoformat(rows[0][0]).tzinfo is not None


def test_cap_counts_soft_block_as_two(env):
    env["cfg"]["daily_removal_cap"] = 3; (env["dir"] / "config.json").write_text(json.dumps(env["cfg"]))
    _select(env, [1, 2])
    res = lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    assert len(res["left"]) == 1 and res["stopped"]["reason"] == "daily cap"


def test_warning_stops_for_day(env):
    _select(env, [1, 2])
    a = ListAdapter(results=[RemovalResult("warning", "X warning")])
    res = lr.run_list_removals(UK, env["sid"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())
    assert res["stopped"]["reason"] == "warning" and a.calls == [("block", "@demo_owner_a")]
    with pytest.raises(rr.RefusedError, match="paused"):
        lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())


def test_unblock_failure_reported(env):
    _select(env, [1])
    a = ListAdapter(results=[RemovalResult("ok"), RemovalResult("error", "button missing")])
    res = lr.run_list_removals(UK, env["sid"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())
    assert res["stopped"]["reason"] == "unblock failed"
    assert any(e["status"] == "LIST_UNBLOCK_FAILED" for e in hist(env))


def test_not_confirmed_when_still_on_list(env):
    _select(env, [1])
    res = lr.run_list_removals(UK, env["sid"], ListAdapter(stuck={"101"}), root=env["root"], sleep=lambda s: None,
                               out=io.StringIO())
    assert res["stopped"]["reason"] == "not confirmed"
    assert not any(e["status"] == "LIST_SOFT_BLOCKED" for e in hist(env))


def test_lock_and_reconcile(env):
    _select(env, [1, 2])
    with rr.run_lock(UK, env["root"], "list", env["sid"]):
        with pytest.raises(rr.RefusedError, match="in progress"):
            lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    (env["dir"] / rr.LOCK_NAME).write_text("{}")         # crash left the lock
    a = ListAdapter(); a.on["101"] = False                # first one finished on X; second owner left blocked
    a.blocked.add("@demo_owner_b")
    r = lr.reconcile_interrupted_list_run(UK, env["sid"], a, root=env["root"], out=io.StringIO())
    assert r["reconciled"] == ["Spammers and scammers"] and r["owner_still_blocked"] == ["@demo_owner_b"]
    assert r["lock_cleared"] is False and a.calls == []


def test_return_detection_and_repeat_offender_card(env):
    _select(env, [1])
    lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    later = (dt.datetime.now().astimezone() + dt.timedelta(seconds=5)).isoformat()
    snap2 = ls.build_snapshot(UK, env["root"], records=[dict(RAW[0], list_id="201", name="Spam round two"), RAW[2]],
                              when=later)
    ret = lr.detect_returns(UK, snap2["snapshot_id"], env["root"])
    assert [r["owner_handle"] for r in ret] == ["@demo_owner_a"]
    assert any(e["status"] == "LIST_OWNER_RETURN_DETECTED" for e in hist(env))
    card = lc.build_repeat_offender_card(UK, ret)
    assert card["card_spec"]["options"][-1]["label"] == "Done" and "graveyard" in card["links_message"]
    assert lc.SOFT_BLOCK_WARNING not in json.dumps(card)
    assert lc.record_repeat_offender_answer(UK, snap2["snapshot_id"], ret, ["1"], root=env["root"])["recorded"] is False
    with pytest.raises(rr.RefusedError):
        lr.run_owner_blocks(UK, snap2["snapshot_id"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    lc.record_repeat_offender_answer(UK, snap2["snapshot_id"], ret, ["1", "Done"], root=env["root"])
    a = ListAdapter()
    res = lr.run_owner_blocks(UK, snap2["snapshot_id"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())
    assert res["blocked"] == ["@demo_owner_a"] and a.calls == [("block", "@demo_owner_a")]   # no unblock
    assert lr.detect_returns(UK, snap2["snapshot_id"], env["root"]) == []


def test_auto_block_mode_authorizes_returns(env):
    _select(env, [1])
    lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    env["cfg"]["graveyard_return_action"] = "auto_block"; (env["dir"] / "config.json").write_text(json.dumps(env["cfg"]))
    snap2 = ls.build_snapshot(UK, env["root"], records=[RAW[0]],
                              when=(dt.datetime.now().astimezone() + dt.timedelta(seconds=5)).isoformat())
    lr.detect_returns(UK, snap2["snapshot_id"], env["root"])
    res = lr.run_owner_blocks(UK, snap2["snapshot_id"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    assert res["blocked"] == ["@demo_owner_a"]


def test_routine_book_and_sheet_cover_lists():
    s = daily_routine.routine_spec({"daily_scan": {"time": "09:00"}, "lists": {"enabled": True}})
    assert any("lists you're on" in x for x in s["steps"])
    assert not any("list" in x.lower() and "lists:" in x for x in
                   daily_routine.routine_spec({"daily_scan": {"time": "09:00"}})["steps"])
    assert "List checks: on" in rules_book.render({"lists": {"enabled": True}, "daily_scan": {"time": "09:00"}})
    assert "List Graveyard" in sheet_layout.HEADERS and "Kept Lists" in sheet_layout.HEADERS
