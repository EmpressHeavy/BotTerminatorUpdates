"""v3.1.0: card taps run the list removal now (Automatic Mode), each list written to the List Graveyard the moment its
task finishes (success, failure, unverified, skipped or stopped), Book change log, protected/already-blocked skips,
default-off list setup, runbook. Made-up demo lists only; a test adapter, never X."""
import io, json, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st, lists_scan as ls, list_cards as lc, list_runner as lr, removal_runner as rr
import list_flow as lf, sheet_layout as sl, new_user, daily_routine, rules_book
import build_monthly_settings_card as mc
from removal_runner import RemovalResult
from test_lists import env, ListAdapter, UK, RAW, hist  # noqa: F401  (env is a fixture)

SID_COL, RESULT_COL, ENTRY_COL = 7, 6, 8


def _select(env, nums):
    lc.build_cards(UK, env["sid"], env["root"])
    return lf.handle_answer(UK, env["sid"], [str(n) for n in nums] + [lc.REMOVE_BTN], card=1, root=env["root"])


def _cfg(env, **kw):
    p = env["dir"] / "config.json"
    c = json.loads(p.read_text()); c.update(kw); p.write_text(json.dumps(c))


class EventAdapter(ListAdapter):
    def __init__(self, events, **kw):
        super().__init__(**kw); self.events = events

    def block(self, r):
        self.events.append(f"block:{r['list_id']}"); return super().block(r)

    def unblock(self, r):
        self.events.append(f"unblock:{r['list_id']}"); return super().unblock(r)


def test_tap_authorizes_immediate_execution_in_automatic_mode(env):
    r = _select(env, [1, 2])
    assert r["recorded"] and r["execute_now"] and not r["awaiting_confirmation"]
    assert [t["list_id"] for t in r["tasks"]] == ["101", "102"]
    assert rr.removals_today(rr._history(UK, env["root"]), "2000-01-01", rr._tz(env["cfg"])) == 0   # nothing ran yet


def test_manual_mode_waits_for_confirmation(env):
    _cfg(env, operating_mode="review")
    r = _select(env, [1])
    assert r["recorded"] and r["awaiting_confirmation"] and not r["execute_now"]


def test_graveyard_row_written_immediately_after_each_list(env):
    events = []
    _select(env, [1, 2])
    plans = []

    def write_sheet(plan):
        assert plan["tool"] == "append_rows" and plan["arguments"]["sheet"] == "List Graveyard"
        assert plan["arguments"]["cells"] == "A2:I" and len(plan["arguments"]["values"]) == 1
        plans.append(plan); events.append("sheet:" + plan["arguments"]["values"][0][3].lstrip("'"))

    books = []
    res = lf.run_now(UK, env["sid"], EventAdapter(events), write_sheet=write_sheet,
                     write_book=lambda steps: (books.append(steps), events.append("book")), root=env["root"],
                     sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="SHEET_X", book_document_id="DOC_X")
    assert len(res["left"]) == 2
    # list 101 is fully written BEFORE list 102 is touched
    assert events == ["block:101", "unblock:101", "sheet:101", "book", "block:102", "unblock:102", "sheet:102", "book"]
    row = plans[0]["arguments"]["values"][0]
    assert row[1].startswith("LIST_SOFT_BLOCKED") and row[2] == "Spammers and scammers" and row[4] == "@demo_owner_a"
    assert "verified" in row[RESULT_COL] and row[SID_COL] == env["sid"] and row[ENTRY_COL]
    assert plans[0]["arguments"]["spreadsheetId"] == "SHEET_X"
    assert books[0][1]["tool"] == "insert_text" and books[0][1]["args"]["text"].startswith("\n- 2026-") \
        and "Spammers and scammers" in books[0][1]["args"]["text"]
    assert lf.unsynced(UK, env["root"]) == []


def test_failed_and_unverified_removals_are_logged_with_actual_result(env):
    _select(env, [1, 2, 3])
    rows = []
    a = ListAdapter(stuck={"101"})               # clicks work but the list stays on the memberships page
    res = lf.run_now(UK, env["sid"], a, write_sheet=lambda p: rows.append(p["arguments"]["values"][0]), root=env["root"],
                     sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="S")
    assert res["stopped"]["reason"] == "not confirmed" and len(rows) == 1
    assert rows[0][1].startswith("LIST_SOFTBLOCK_NOT_CONFIRMED") and rows[0][RESULT_COL].startswith("NOT verified")
    assert res["actions_today"] == 2                                          # both clicks happened: counts 2


def test_unblock_failure_and_x_warning_are_logged_too(env):
    _select(env, [1, 2])
    rows = []
    a = ListAdapter(results=[RemovalResult("ok", ""), RemovalResult("error", "dialog did not close")])
    res = lf.run_now(UK, env["sid"], a, write_sheet=lambda p: rows.append(p["arguments"]["values"][0]), root=env["root"],
                     sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="S")
    assert [r[1].split(":")[0] for r in rows] == ["LIST_UNBLOCK_FAILED"] and "BLOCKED" in rows[0][RESULT_COL]
    assert res["stopped"]["reason"] == "unblock failed"


def test_warning_logs_stopped_row_and_locks_day(env):
    _select(env, [1, 2])
    rows = []
    a = ListAdapter(results=[RemovalResult("warning", "X says slow down")])
    res = lf.run_now(UK, env["sid"], a, write_sheet=lambda p: rows.append(p["arguments"]["values"][0]), root=env["root"],
                     sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="S")
    assert res["stopped"] and rows[0][1].startswith("LIST_STOPPED") and "warning" in rows[0][RESULT_COL]
    assert any(e.get("locks_day") for e in hist(env))
    with pytest.raises(rr.RefusedError):
        lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())


def test_writer_failure_stops_run_before_next_list_and_catch_up_fills_in(env):
    _select(env, [1, 2])
    a = ListAdapter()

    def boom(plan):
        raise OSError("connector down")

    res = lf.run_now(UK, env["sid"], a, write_sheet=boom, root=env["root"], sleep=lambda s: None, out=io.StringIO(),
                     spreadsheet_id="S")
    assert res["stopped"]["reason"] == "log write failed" and [c for c in a.calls if c[0] == "block"] == [("block", "@demo_owner_a")]
    assert [e["list_id"] for e in lf.unsynced(UK, env["root"])] == ["101"]     # saved locally, not written
    got = []
    assert lf.catch_up(UK, env["root"], write_sheet=lambda p: got.append(p), write_book=lambda b: None,
                         spreadsheet_id="S") == 1
    assert len(got) == 1 and lf.unsynced(UK, env["root"]) == []


def test_protected_owner_is_skipped_even_when_authorized(env):
    _select(env, [1, 2])
    _cfg(env, protected_handles=["demo_owner_a"])
    rows = []
    a = ListAdapter()
    res = lf.run_now(UK, env["sid"], a, write_sheet=lambda p: rows.append(p["arguments"]["values"][0]), root=env["root"],
                     sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="S")
    assert ("block", "@demo_owner_a") not in a.calls and ("block", "@demo_owner_b") in a.calls
    assert rows[0][1].startswith("LIST_SKIPPED_PROTECTED_OWNER") and rows[1][1].startswith("LIST_SOFT_BLOCKED")
    assert res["actions_today"] == 2


def test_owner_already_blocked_is_logged_and_never_unblocked(env):
    _select(env, [1])
    a = ListAdapter(); a.blocked.add("@demo_owner_a")
    rows = []
    lf.run_now(UK, env["sid"], a, write_sheet=lambda p: rows.append(p["arguments"]["values"][0]), root=env["root"],
               sleep=lambda s: None, out=io.StringIO(), spreadsheet_id="S")
    assert a.calls == [] and rows[0][1].startswith("LIST_SKIPPED_OWNER_ALREADY_BLOCKED")


def test_block_unblock_wait_is_ten_seconds_and_cap_counts_two(env):
    _select(env, [1])
    sleeps = []
    res = lr.run_list_removals(UK, env["sid"], ListAdapter(), root=env["root"], sleep=sleeps.append, out=io.StringIO())
    assert sleeps == [10.0] and lr.SOFT_BLOCK_WAIT_SECONDS == 10.0 and res["actions_today"] == 2


# ---------- step mode (the bot drives its own browser) ----------
OK = {"status": "ok"}


def _obs(**kw):
    o = {"on_list_before": True, "owner_blocked_before": False, "block": OK, "unblock": OK,
         "on_list_after": False, "owner_blocked_after": False}
    o.update(kw); return o


def test_step_mode_one_list_returns_plans_and_next_task_waits(env):
    _select(env, [1, 2])
    t = lf.next_task(UK, env["sid"], env["root"])
    assert t["list"]["list_id"] == "101" and t["protected_owner"] is None and t["remaining"] == 2 and t["wait_seconds"] == 0
    r = lf.leave_list(UK, env["sid"], "101", _obs(), root=env["root"], spreadsheet_id="S", book_document_id="D")
    assert r["entry"]["status"] == "LIST_SOFT_BLOCKED" and r["sheet_plan"]["arguments"]["sheet"] == "List Graveyard"
    assert r["book_plan"][1]["tool"] == "insert_text" and r["stopped"] is None and r["actions_today"] == 2
    assert [e["list_id"] for e in lf.unsynced(UK, env["root"])] == ["101"]          # until the bot confirms the write
    lf.mark_written(UK, r["entry"]["entry_id"], env["root"], sheet=True, book=True)
    assert lf.unsynced(UK, env["root"]) == []
    t2 = lf.next_task(UK, env["sid"], env["root"])
    assert t2["list"]["list_id"] == "102" and 0 < t2["wait_seconds"] <= 10


def test_step_mode_applies_the_same_checks(env):
    ids = [t["list_id"] for t in _select(env, [1, 2, 3, 4])["tasks"]]
    assert ids[:2] == ["101", "102"] and len(ids) == 4
    _cfg(env, protected_handles=["demo_owner_a"])
    assert lf.next_task(UK, env["sid"], env["root"])["protected_owner"]
    r = lf.leave_list(UK, env["sid"], "101", {}, root=env["root"], spreadsheet_id="S")          # no X observation needed
    assert r["entry"]["status"] == "LIST_SKIPPED_PROTECTED_OWNER" and r["sheet_plan"] and r["book_plan"] is None
    r = lf.leave_list(UK, env["sid"], "102", _obs(owner_blocked_before=True), root=env["root"], spreadsheet_id="S")
    assert r["entry"]["status"] == "LIST_SKIPPED_OWNER_ALREADY_BLOCKED"
    r = lf.leave_list(UK, env["sid"], ids[2], _obs(on_list_after=True), root=env["root"], spreadsheet_id="S")
    assert r["entry"]["status"] == "LIST_SOFTBLOCK_NOT_CONFIRMED" and r["book_plan"] and r["stopped"]
    r = lf.leave_list(UK, env["sid"], ids[3], _obs(block={"status": "rate_limited", "message": "wait"}), root=env["root"], spreadsheet_id="S")
    assert r["entry"]["status"] == "LIST_STOPPED" and r["entry"]["locks_day"]


def test_step_mode_unknown_state_never_acts_and_bad_keys_refused(env):
    _select(env, [1])
    with pytest.raises(ValueError):
        lf.ObservedAdapter({"surprise": 1})
    r = lf.leave_list(UK, env["sid"], "101", {"on_list_before": None}, root=env["root"], spreadsheet_id="S")
    assert r["entry"]["status"] == "LIST_STOPPED" and r["stopped"]


def test_step_mode_refuses_unauthorized_list_and_second_run(env):
    _select(env, [1])
    r = lf.leave_list(UK, env["sid"], "104", _obs(), root=env["root"], spreadsheet_id="S")     # not selected
    assert r["entry"] is None and r["left"] == []
    with rr.run_lock(UK, env["root"], "list", env["sid"]):
        with pytest.raises(rr.RefusedError, match="in progress"):
            lf.leave_list(UK, env["sid"], "101", _obs(), root=env["root"])


def test_frozen_snapshot_rechecked_at_execution(env):
    _select(env, [1])
    body = env["dir"] / "lists" / env["sid"] / "lists.json"
    body.chmod(0o644); body.write_text(body.read_text().replace("Spammers", "Edited"))
    with pytest.raises(rr.RefusedError, match="changed"):
        lf.leave_list(UK, env["sid"], "101", _obs(), root=env["root"])


# ---------- keep ----------
def test_keep_all_writes_kept_lists_plan_once(env):
    lc.build_cards(UK, env["sid"], env["root"])
    r = lf.handle_answer(UK, env["sid"], [lc.KEEP_BTN], card=1, root=env["root"])
    assert r["recorded"] and not r["execute_now"] and r["tasks"] == []
    p = r["kept_plan"]
    assert p["sheet"]["arguments"]["sheet"] == "Kept Lists" and len(p["sheet"]["arguments"]["values"]) == 4
    assert p["sheet"]["arguments"]["cells"] == "A2:E"
    lf.kept_written(UK, p["keys"], env["root"])
    assert lf.kept_plan(UK, env["root"]) is None


# ---------- cards, setup, monthly, Book, docs ----------
def test_pre_card_warns_when_user_follows_owner_only_there(env):
    cards = lc.build_cards(UK, env["sid"], env["root"])
    msg = cards[0]["links_message"]
    assert msg.count("You follow this owner") == 1 and "also unfollow them" in msg
    assert "You follow this owner" not in json.dumps(cards[0]["card_spec"])


def test_setup_asks_lists_default_off_and_creates_list_tabs(tmp_path):
    assert "default: no" in new_user.SETUP_QUESTIONS[3]
    import shutil
    shutil.copytree(ROOT / "config", tmp_path / "config"); shutil.copytree(ROOT / "templates", tmp_path / "templates")
    p = new_user.create_user("demo_setup", "@demo_h", daily_cap=10, scan_time="09:00", root=tmp_path)
    assert json.loads(p.read_text())["lists"]["enabled"] is False
    tabs = new_user.setup_plans(json.loads(p.read_text()), tmp_path)["sheet"][0]["args"]["sheet_titles"]
    assert {"Kept Lists", "Protected Lists", "List Graveyard"} <= set(tabs)
    assert "--lists" in (ROOT / "src/new_user.py").read_text() and 'default="no"' in (ROOT / "src/new_user.py").read_text()


def test_monthly_card_and_routine_mention_lists():
    c = mc.build(None, lists_enabled=False)
    assert len(c["buttons"]) <= mc.MAX_OPTIONS and "list" in c["buttons"][1].lower()
    assert any("List checks: OFF" in x for x in c["extra_companion_lines"])
    assert any("List checks: ON" in x for x in mc.build(None, lists_enabled=True)["extra_companion_lines"])
    assert [x for x in mc.build(None)["extra_companion_lines"] if "List checks" in x] == []
    steps = " ".join(daily_routine.routine_spec({"daily_scan": {"time": "09:00"}, "lists": {"enabled": True}})["steps"])
    assert "scope card" in steps and "List Graveyard" in steps and "docs/list_runbook.md" in steps
    off = " ".join(daily_routine.routine_spec({"daily_scan": {"time": "09:00"}})["steps"])
    assert "list" not in off.lower()


def test_book_template_and_runbook_cover_the_live_flow():
    book = (ROOT / "templates/bot_terminator_book.md").read_text()
    for x in ("off by default", "about 10 seconds", "lists/memberships", "List Graveyard tab the moment", "Change log",
              "already follow a list's owner", "2 toward your daily cap"):
        assert x in book, x
    rb = (ROOT / "docs/list_runbook.md").read_text()
    for x in ("lists/memberships", "Owner already blocked => stop", "Wait about 10 seconds", "immediately",
              "never in a", "LIST_SOFTBLOCK_NOT_CONFIRMED", "**2**", "list_flow.leave_list", "Observed facts"):
        assert x in rb, x
    assert rr.PACING_SECONDS == 10
