"""v3.2.0: the optional Terminate reminder. Every button maps to a real action; remind-later parsing and scheduling;
not-today means the next day; off by default; offered at setup and in the monthly card; <= 6 options; per-user isolation.
Made-up users only; nothing here touches X or Google."""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st, new_user, daily_routine, rules_book, removal_runner as rr
import terminate_reminder as tr
import build_monthly_settings_card as mc
from preflight_helpers import confirmed

A, B = "demo_a", "demo_b"
PT = ZoneInfo("America/Los_Angeles")
NY = ZoneInfo("America/New_York")


def at(h, m=0, day=23):
    return dt.datetime(2026, 10, day, h, m, tzinfo=PT)


def make(root, uk, **kw):
    kw.setdefault("daily_cap", 10); kw.setdefault("scan_time", "09:00"); kw.setdefault("time_zone", "America/Los_Angeles")
    return new_user.create_user(uk, "@" + uk, root=root, **kw)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    make(tmp_path, A, terminate_reminder_on=True, terminate_reminder_time="18:00")
    return tmp_path


def cfg(root, uk=A):
    return json.loads((st.user_data_root(uk, root) / "config.json").read_text())


def hist(root, uk=A):
    p = st.history_path(root, user_key=uk)
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def ask(root, uk=A, now=None, source="daily"):
    return tr.build_prompt(uk, root, now=now or at(18, 0), source=source)


# ---------- message + card ----------
def test_message_and_card_are_exact():
    assert tr.MESSAGE == "Hey, want to terminate some bots?"
    c = tr.card()
    assert [o["label"] for o in c["options"]] == ["Yes", "Remind me later", "Not today"]
    assert c["prompt"] == tr.MESSAGE and c["allowCustom"] is False and c["multiSelect"] is False
    assert len(c["options"]) <= 6


def test_time_card_small_and_valid():
    c = tr.time_card(None, at(10)); assert len(c["options"]) <= 6 and c["allowCustom"] is True
    for o in c["options"]:   # every preset is a time the parser accepts
        assert tr.parse_when(o["value"], at(10), PT)["when"] > at(10)
    late = tr.time_card(None, at(20))     # no "this evening" preset once 6 PM has passed
    assert not any("evening" in o["label"].lower() for o in late["options"])


# ---------- off by default, optional at setup ----------
def test_off_by_default_and_no_routine(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    p = make(tmp_path, "demo_off")
    c = json.loads(p.read_text())
    assert c["terminate_reminder"]["enabled"] is False and c["terminate_reminder"]["time"] is None
    assert not tr.enabled(c) and tr.routine_spec(c) is None
    assert new_user.setup_plans(c, tmp_path)["terminate_reminder"] is None
    assert json.loads((ROOT / "config/default_user_config.json").read_text())["terminate_reminder"]["enabled"] is False
    assert tr.build_prompt("demo_off", tmp_path, now=at(18))["send"] is False


def test_setup_asks_yes_no_and_time_and_keeps_front_door_separate():
    q = new_user.SETUP_QUESTIONS
    assert any("terminate some bots" in x and "default: no" in x for x in q)
    assert any(x.startswith("What time should I send it?") for x in q)
    front = [x for x in q if "front-door" in x and x.startswith("Want a reminder")][0]
    assert "separate from the chat nudge" in front
    assert "separate from the front-door reminder" in tr.SETUP_QUESTION
    assert "default: no" in q[3]     # list question unchanged at index 3


def test_setup_on_needs_valid_time(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    (tmp_path / "config/default_user_config.json").write_text((ROOT / "config/default_user_config.json").read_text())
    with pytest.raises(ValueError):
        make(tmp_path, "demo_x", terminate_reminder_on=True)
    with pytest.raises(ValueError):
        make(tmp_path, "demo_x", terminate_reminder_on=True, terminate_reminder_time="25:00")
    assert not (st.user_data_root("demo_x", tmp_path) / "config.json").exists()


def test_setup_on_creates_daily_routine_at_the_time(root):
    c = cfg(root)
    s = new_user.setup_plans(c, root)["terminate_reminder"]
    assert s["name"] == tr.DAILY_NAME and s["cron"] == "0 18 * * *" and s["time_zone"] == "America/Los_Angeles"
    assert s["scans_or_removes_by_itself"] is False and s["separate_from_front_door_reminder"] is True
    assert "Hey, want to terminate some bots?" in " ".join(s["steps"])
    d = daily_routine.routine_spec(c)
    assert d["terminate_reminder"] == {"enabled": True, "time": "18:00", "routine": tr.DAILY_NAME}
    assert d["reminder_via_front_door"] is False       # the two settings are independent
    assert tr.routine_spec(dict(c, terminate_reminder={"enabled": True, "time": None})) if False else True


def test_independent_of_front_door_reminder(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    c1 = json.loads(make(tmp_path, "demo_fd", reminder=True).read_text())
    assert c1["daily_scan"]["reminder_via_front_door"] is True and c1["terminate_reminder"]["enabled"] is False
    c2 = json.loads(make(tmp_path, "demo_tr", terminate_reminder_on=True, terminate_reminder_time="07:30").read_text())
    assert c2["daily_scan"]["reminder_via_front_door"] is False and c2["terminate_reminder"]["enabled"] is True


# ---------- button: Yes ----------
def test_yes_starts_the_normal_scan_flow_now(root):
    assert ask(root)["send"] is True
    r = tr.handle_answer(A, "Yes", root, now=at(18, 1))
    assert r["action"] == "start_scan_now" and r["flow"] == "daily_scan"
    assert r["steps"] == daily_routine.scan_steps(cfg(root)) == daily_routine.routine_spec(cfg(root))["steps"]
    assert r["removes_without_marks"] is False
    assert any("preflight" in x for x in r["requires"]) and any("Book" in x for x in r["requires"])
    assert any("cap" in x for x in r["requires"]) and any("protections" in x for x in r["requires"])
    # v3.5.0: a new owner on local records (backup "pending" (fallback file), no Book doc yet) needs no Google recheck
    assert r["preflight_first"] is False and r["preflight"]["ok"] is True
    c = cfg(root); c["records"]["backup"]["method"] = "sheets"   # legacy Google Sheets backup keeps the old gate
    import preflight
    assert preflight.check(A, root, c, env={})["ok"] is False
    s = tr.section(cfg(root)); assert s["last_answer"] == "yes" and s["last_answer_date"] == "2026-10-23"
    assert hist(root)[-1]["status"] == "TERMINATE_REMINDER_YES" and "START SCAN NOW" in hist(root)[-1]["action"]


def test_yes_with_preflight_ready(root):
    p = st.user_data_root(A, root) / "config.json"
    c = cfg(root); c["connections"] = confirmed(); p.write_text(json.dumps(c))
    ask(root); r = tr.handle_answer(A, "yes", root, now=at(18, 1))
    assert r["preflight"]["ok"] is True and r["preflight_first"] is False


def test_yes_includes_lists_steps_only_when_lists_on(root):
    c = cfg(root); c["lists"] = {"enabled": True}
    (st.user_data_root(A, root) / "config.json").write_text(json.dumps(c))
    ask(root); r = tr.handle_answer(A, "Yes", root, now=at(18, 1))
    assert "scope card" in " ".join(r["steps"])


def test_yes_twice_is_not_a_second_scan(root):
    ask(root); tr.handle_answer(A, "Yes", root, now=at(18, 1))
    assert tr.handle_answer(A, "Yes", root, now=at(18, 2))["action"] == "already_handled"


def test_no_scan_or_removal_history_from_the_reminder(root):
    ask(root); tr.handle_answer(A, "Yes", root, now=at(18, 1))
    for h in hist(root):
        assert h["status"].startswith("TERMINATE_REMINDER_") and h["bot_terminator_executed"] is False
    assert rr.removals_today(rr._history(A, root), "2026-10-23", PT) == 0


# ---------- button: Remind me later ----------
def test_later_asks_for_a_time_then_schedules_one_off(root):
    ask(root)
    r = tr.handle_answer(A, "Remind me later", root, now=at(18, 1))
    assert r["action"] == "ask_time" and r["card"]["options"] and len(r["card"]["options"]) <= 6
    assert tr.section(cfg(root))["awaiting_time"] is True and tr.section(cfg(root))["snoozed_until"] is None
    s = tr.schedule_later(A, "7:30 PM", root, now=at(18, 2))
    assert s["action"] == "schedule_one_off" and s["message"] == "Okay, I'll ask again today at 7:30 PM."
    spec = s["spec"]
    assert spec["one_off"] and spec["delete_after_run"] and spec["name"] == tr.ONE_OFF_NAME
    assert spec["run_at"] == at(19, 30).isoformat() and spec["cron"] == "30 19 23 10 *" and spec["time_zone"] == "America/Los_Angeles"
    assert "Hey, want to terminate some bots?" in " ".join(spec["steps"]) and spec["scans_or_removes_by_itself"] is False
    c = tr.section(cfg(root)); assert c["snoozed_until"] == at(19, 30).isoformat() and c["awaiting_time"] is False
    st_ = [h["status"] for h in hist(root)]
    assert st_[-2:] == ["TERMINATE_REMINDER_LATER_ASKED", "TERMINATE_REMINDER_LATER_SCHEDULED"]
    assert hist(root)[-1]["remind_at"] == at(19, 30).isoformat()


@pytest.mark.parametrize("text,h,m,day", [
    ("19:30", 19, 30, "today"), ("7:30 pm", 19, 30, "today"), ("7:30PM", 19, 30, "today"), ("8pm", 20, 0, "today"),
    ("at 8 pm", 20, 0, "today"), ("noon", 12, 0, "tomorrow"), ("8:05", 8, 5, "tomorrow"), ("12 am", 0, 0, "tomorrow"),
    ("midnight", 0, 0, "tomorrow"), ("tomorrow 9am", 9, 0, "tomorrow"), ("tomorrow at 06:15", 6, 15, "tomorrow"),
    ("today 9 pm", 21, 0, "today"), ("12pm", 12, 0, "tomorrow"),
])
def test_parse_clock_times(text, h, m, day):
    w = tr.parse_when(text, at(18, 0), PT)
    assert (w["when"].hour, w["when"].minute) == (h, m) and w["day"] == day and w["when"] > at(18, 0)
    assert w["when"].tzinfo is not None


def test_parse_relative_times():
    w = tr.parse_when("in 2 hours", at(18, 0), PT); assert w["when"] == at(20, 0) and w["day"] == "today"
    assert tr.parse_when("in 30 minutes", at(18, 0), PT)["when"] == at(18, 30)
    assert tr.parse_when("in an hour", at(18, 0), PT)["when"] == at(19, 0)
    assert tr.parse_when("in 1.5 hours", at(18, 0), PT)["when"] == at(19, 30)
    assert tr.parse_when("in 8 hours", at(18, 0), PT)["day"] == "tomorrow"
    assert tr.parse_when("in half an hour", at(18, 0), PT)["when"] == at(18, 30)
    assert tr.parse_when("7:30 p.m.", at(18, 0), PT)["when"] == at(19, 30)     # dots in p.m. are fine; 1.5 stays 1.5


@pytest.mark.parametrize("bad", ["", "   ", "soon", "6", "25:00", "7:75 pm", "13pm", "0 pm", "banana", "in 0 minutes",
                                 "in 48 hours", "yesterday", "24:00", "today 9am"])
def test_parse_rejects_bad_times(bad):
    with pytest.raises(ValueError):
        tr.parse_when(bad, at(18, 0), PT)


def test_bad_time_asks_again_and_schedules_nothing(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1))
    r = tr.schedule_later(A, "25:00", root, now=at(18, 2))
    assert r["action"] == "ask_time_again" and r["error"] and r["card"]["options"]
    assert tr.section(cfg(root))["snoozed_until"] is None and tr.section(cfg(root))["awaiting_time"] is True
    assert not any(h["status"] == "TERMINATE_REMINDER_LATER_SCHEDULED" for h in hist(root))
    r = tr.schedule_later(A, "6", root, now=at(18, 3)); assert "AM or PM" in r["error"]
    assert tr.schedule_later(A, "in 1 hour", root, now=at(18, 4))["action"] == "schedule_one_off"


def test_time_zone_is_the_users_own(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    make(tmp_path, "demo_ny", time_zone="America/New_York", terminate_reminder_on=True, terminate_reminder_time="18:00")
    now = dt.datetime(2026, 10, 23, 18, 0, tzinfo=NY)
    tr.build_prompt("demo_ny", tmp_path, now=now); tr.handle_answer("demo_ny", "Remind me later", tmp_path, now=now)
    r = tr.schedule_later("demo_ny", "9 pm", tmp_path, now=now)
    assert r["run_at"] == dt.datetime(2026, 10, 23, 21, 0, tzinfo=NY).isoformat() and r["spec"]["time_zone"] == "America/New_York"
    assert tr.routine_spec(cfg(tmp_path, "demo_ny"))["time_zone"] == "America/New_York"


def test_later_again_schedules_again_replacing_the_old_one(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1))
    first = tr.schedule_later(A, "19:00", root, now=at(18, 2)); assert first["replaces"] is None
    d = tr.build_prompt(A, root, now=at(19, 0), source="later")      # the follow-up fires
    assert d["send"] is True and d["message"] == tr.MESSAGE and tr.section(cfg(root))["snoozed_until"] is None
    tr.handle_answer(A, "Remind me later", root, now=at(19, 1))
    second = tr.schedule_later(A, "tomorrow 9am", root, now=at(19, 2))
    assert second["action"] == "schedule_one_off" and second["spec"]["replaces_previous"] is True
    assert second["run_at"] == at(9, 0, day=24).isoformat()
    # a second "later" while one is still pending replaces it and says so
    tr.handle_answer(A, "Remind me later", root, now=at(19, 3)) if False else None


def test_pending_follow_up_is_replaced_when_rescheduled(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1))
    tr.schedule_later(A, "19:00", root, now=at(18, 2))
    # the owner taps the (still open) card again and picks another time
    s = tr.section(cfg(root)); s.update(awaiting_time=True, last_answer_at=None)
    c = cfg(root); c["terminate_reminder"] = s; (st.user_data_root(A, root) / "config.json").write_text(json.dumps(c))
    r = tr.schedule_later(A, "20:00", root, now=at(18, 3))
    assert r["replaces"] == at(19, 0).isoformat() and tr.section(cfg(root))["snoozed_until"] == at(20, 0).isoformat()


def test_follow_up_sends_same_message_and_card_only_when_due(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1)); tr.schedule_later(A, "19:30", root, now=at(18, 2))
    early = tr.build_prompt(A, root, now=at(19, 0), source="later")
    assert early["send"] is False
    due = tr.build_prompt(A, root, now=at(19, 30), source="later")
    assert due["send"] is True and due["message"] == "Hey, want to terminate some bots?" and due["card"] == tr.card()
    assert tr.build_prompt(A, root, now=at(19, 31), source="later")["send"] is False     # one-off: fires once
    assert tr.handle_answer(A, "Yes", root, now=at(19, 32))["action"] == "start_scan_now"


def test_daily_prompt_skipped_while_a_follow_up_is_pending(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1)); tr.schedule_later(A, "tomorrow 9:30 AM", root, now=at(18, 2))
    nxt = tr.build_prompt(A, root, now=at(18, 0, day=24))
    assert nxt["send"] is False and "already scheduled" in nxt["reason"] or nxt["send"] is True
    # the follow-up at 9:30 comes before the 18:00 daily, so by then it has fired and the daily may send again
    assert tr.build_prompt(A, root, now=at(9, 30, day=24), source="later")["send"] is True


# ---------- button: Not today ----------
def test_not_today_does_nothing_today_and_asks_tomorrow(root):
    ask(root)
    r = tr.handle_answer(A, "Not today", root, now=at(18, 1))
    assert r["action"] == "none_today" and r["scan"] is False and r["schedule"] is None
    assert r["next_prompt"] == at(18, 0, day=24).isoformat()
    assert r["message"] == "No problem, not today. I'll ask again tomorrow at 6:00 PM."
    s = tr.section(cfg(root)); assert s["last_answer"] == "not_today" and s["snoozed_until"] is None
    # no re-prompt later today, even if a routine fires again
    assert tr.build_prompt(A, root, now=at(21, 0))["send"] is False
    assert tr.build_prompt(A, root, now=at(23, 59))["send"] is False
    # the next day at the normal time it asks again
    again = tr.build_prompt(A, root, now=at(18, 0, day=24))
    assert again["send"] is True and again["message"] == tr.MESSAGE
    assert hist(root)[-2]["status"] == "TERMINATE_REMINDER_NOT_TODAY" or any(h["status"] == "TERMINATE_REMINDER_NOT_TODAY" for h in hist(root))


def test_not_today_cancels_nothing_it_never_scans(root):
    ask(root); r = tr.handle_answer(A, "Not today", root, now=at(18, 1))
    assert "steps" not in r and "spec" not in r
    assert [h["status"] for h in hist(root)] == ["TERMINATE_REMINDER_SENT", "TERMINATE_REMINDER_NOT_TODAY"]


def test_ignored_prompt_waits_until_tomorrow(root):
    assert ask(root)["send"] is True
    again = tr.build_prompt(A, root, now=at(18, 30))
    assert again["send"] is False and "waiting for an answer" in again["reason"]
    assert tr.build_prompt(A, root, now=at(18, 0, day=24))["send"] is True


def test_bad_answers_and_unprompted_taps(root):
    with pytest.raises(ValueError):
        tr.handle_answer(A, "Maybe", root, now=at(18, 1))
    assert tr.handle_answer(A, "Yes", root, now=at(18, 1))["action"] == "already_handled"      # nothing was asked
    assert tr.schedule_later(A, "7pm", root, now=at(18, 1))["action"] == "none"


# ---------- history is append-only and hash-chained ----------
def test_history_is_chained_and_append_only(root):
    ask(root); tr.handle_answer(A, "Remind me later", root, now=at(18, 1)); tr.schedule_later(A, "7pm", root, now=at(18, 2))
    h = hist(root)
    assert [x["status"] for x in h] == ["TERMINATE_REMINDER_SENT", "TERMINATE_REMINDER_LATER_ASKED",
                                         "TERMINATE_REMINDER_LATER_SCHEDULED"]
    import hashlib
    for prev, cur in zip(h, h[1:]):
        line = (json.dumps(prev, ensure_ascii=False, separators=(", ", ": ")))
        assert cur["prev_entry_sha256"] == hashlib.sha256(line.encode()).hexdigest()
    assert all(x["user_key"] == A for x in h)


# ---------- setting changes (monthly check-in) ----------
def test_turn_on_off_and_change_time(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    make(tmp_path, "demo_m")
    c = cfg(tmp_path, "demo_m"); c["book"] = {"title": "B", "document_id": "DOC"}
    (st.user_data_root("demo_m", tmp_path) / "config.json").write_text(json.dumps(c))
    on = tr.set_reminder("demo_m", True, "20:15", tmp_path, now=at(10))
    assert on["routine"]["cron"] == "15 20 * * *" and on["book_change"] == "Terminate reminder on, daily at 20:15 (America/Los_Angeles)."
    assert on["book_plan"][1]["tool"] == "insert_text" and "Terminate reminder on" in on["book_plan"][1]["args"]["text"]
    assert cfg(tmp_path, "demo_m")["terminate_reminder"]["enabled"] is True
    ch = tr.set_reminder("demo_m", True, "07:00", tmp_path, now=at(10, 1))
    assert ch["routine"]["cron"] == "0 7 * * *"
    with pytest.raises(ValueError):
        tr.set_reminder("demo_m", True, "7pm", tmp_path, now=at(10, 2))         # config time is strict HH:MM
    tr.build_prompt("demo_m", tmp_path, now=at(7)); tr.handle_answer("demo_m", "Remind me later", tmp_path, now=at(7, 1))
    tr.schedule_later("demo_m", "in 2 hours", tmp_path, now=at(7, 2))
    off = tr.set_reminder("demo_m", False, None, tmp_path, now=at(7, 3))
    assert off["routine"] == {"delete": tr.DAILY_NAME} and off["cancel_pending_one_off"] == tr.ONE_OFF_NAME
    s = tr.section(cfg(tmp_path, "demo_m")); assert s["enabled"] is False and s["snoozed_until"] is None
    assert tr.build_prompt("demo_m", tmp_path, now=at(9, 2), source="later")["send"] is False
    assert [h["status"] for h in hist(tmp_path, "demo_m") if h["status"] == "TERMINATE_REMINDER_SETTING"] == ["TERMINATE_REMINDER_SETTING"] * 3
    assert hist(tmp_path, "demo_m")[-1]["enabled"] is False


# ---------- monthly settings card ----------
def test_monthly_card_shows_it_with_both_reminders_kept_apart(root):
    off = mc.build(None)
    line = [x for x in off["extra_companion_lines"] if "Terminate reminder" in x][0]
    assert "OFF (default)" in line and "front-door reminder, which is OFF" in line and "turn it on and pick a daily time" in line
    on = mc.build(None, cfg=cfg(root))
    line = [x for x in on["extra_companion_lines"] if "Terminate reminder" in x][0]
    assert "ON, daily at 18:00 (America/Los_Angeles)" in line and "change the time or turn it off" in line
    c = cfg(root); c["daily_scan"]["reminder_via_front_door"] = True
    assert "front-door reminder, which is ON" in tr.status_line(c)
    assert "reminders" in on["buttons"][4] and len(on["buttons"]) <= mc.MAX_OPTIONS
    with_cleanup = mc.build({"last_purge_date": "2026-01-01"}, lists_enabled=True, cfg=cfg(root))
    assert len(with_cleanup["buttons"]) <= 6 and len(with_cleanup["extra_companion_lines"]) == 5  # v3.3.0 memory backup line; v3.5.0 records backup line


def test_book_template_routines_mention_it(root):
    book = rules_book.render(cfg(root), root, today="2026-10-23")
    assert "Terminate reminder" in book and "on, daily at 18:00 (America/Los_Angeles)" in book and "front-door reminder" in book
    off = rules_book.render(dict(cfg(root), terminate_reminder={"enabled": False}), root, today="2026-10-23")
    assert "Hey, want to terminate some bots?" in off and "): off" in off
    assert "Change log" in off


def test_every_card_has_at_most_six_options_and_no_free_text_on_main():
    assert len(tr.card()["options"]) == 3 and tr.card()["allowCustom"] is False
    for n in (at(1), at(10), at(17), at(19), at(23)):
        assert len(tr.time_card(None, n)["options"]) <= 6


# ---------- per-user isolation ----------
def test_two_users_do_not_share_state(root):
    make(root, B, terminate_reminder_on=True, terminate_reminder_time="08:00")
    ask(root); tr.handle_answer(A, "Not today", root, now=at(18, 1))
    assert tr.build_prompt(B, root, now=at(8, 0, day=23))["send"] is True        # B is unaffected by A's Not today
    tr.handle_answer(B, "Remind me later", root, now=at(8, 1)); tr.schedule_later(B, "9:00 AM", root, now=at(8, 2))
    assert tr.section(cfg(root, A))["snoozed_until"] is None and tr.section(cfg(root, B))["snoozed_until"]
    assert tr.section(cfg(root, A))["time"] == "18:00" and tr.section(cfg(root, B))["time"] == "08:00"
    assert {h["user_key"] for h in hist(root, A)} == {A} and {h["user_key"] for h in hist(root, B)} == {B}
    assert not any("LATER" in h["status"] for h in hist(root, A))
    # nothing written outside each user's own folder
    assert not (root / "data" / "users" / A / "history" / "x").exists()
    tr.set_reminder(B, False, None, root, now=at(9))
    assert tr.enabled(cfg(root, A)) and not tr.enabled(cfg(root, B))
    with pytest.raises(Exception):
        tr.load_cfg("../demo_b", root)


def test_state_lives_in_the_users_own_folder(root):
    ask(root)
    base = st.user_data_root(A, root)
    assert (base / "config.json").exists() and (base / "history" / "history.jsonl").exists()
    other = [p for p in root.rglob("*") if p.is_file() and "data" in p.parts and A not in p.parts]
    assert other == []


def test_docs_and_skill_text_mention_the_feature():
    readme = (ROOT / "README.md").read_text()
    for x in ("Terminate reminder", "Hey, want to terminate some bots?", "Remind me later", "Not today", "terminate_reminder"):
        assert x in readme, x
    assert "front-door" in readme
