"""Beta feedback fixes (2026-10-20). Made-up demo accounts only."""
import datetime as dt, io, json, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import classify as cl
import card_text as ct
import protections as pr
import removal_runner as rr
import inactive_mutuals as im
import new_user, rules_book, sheet_layout, daily_routine
import storage as st
from removal_runner import RemovalResult
from removal_test_adapter import DryTestAdapter
from test_removal_runner import env, select, run, hist, set_cfg, UK  # noqa: F401  (fixture reuse)


def bot(**kw):
    base = dict(user_id="9001", username="jane83920174", name="Jane", followers_count=3, following_count=900,
                post_count=1, account_age_days=30, has_default_avatar=True, bio="", deep_inspected=True,
                activity=cl.ActivityFingerprint(0, 0, 0, 1, sample_size=1), days_inactive=1)
    base.update(kw)
    return cl.Candidate(**base)


# 1. classifier
def test_number_handle_is_hint_only_never_proof():
    h = cl.handle_bio_screen(bot())
    assert h["number_style_handle"] and h["hints"][0].startswith("Hint only")
    assert not cl.handle_bio_screen(bot(username="janedoe"))["number_style_handle"]


@pytest.mark.parametrize("raw", [{"replies_to_others": 12}, {"followed_by_verified": True},
                                 {"known_followers_count": 4}])
def test_real_people_with_number_handles_are_kept(raw):
    r = cl.classify(bot(raw=raw))
    assert r["removal_card_eligible"] is False and not r["label"].startswith("BOT")


def test_number_handle_person_with_normal_numbers_kept():
    r = cl.classify(bot(username="maria19842023", followers_count=180, following_count=210, post_count=1400,
                        has_default_avatar=False, bio="nurse, mom",
                        activity=cl.ActivityFingerprint(30, 40, 5, 25, sample_size=100)))
    assert r["removal_card_eligible"] is False


def test_fails_b_and_c_goes_on_card():
    r = cl.classify(bot())
    assert r["removal_card_eligible"] is True
    assert r["person_check"]["bot_number_signs"] and not r["person_check"]["real_replies"]


def test_missing_numbers_never_clear_an_account():
    ev = cl.person_check(bot(post_count=None))
    assert ev["numbers_complete"] is False


# 8. impersonation
def test_celebrity_manager_flag():
    r = cl.classify(bot(name="Elon Musk Manager", username="elonmgr_desk", raw={"replies_to_others": 50}))
    assert r["impersonation_flag"] is True and r["removal_card_eligible"] is True   # flag overrides (b)


def test_friend_impersonation_flag():
    friends = [{"handle": "sunnybaker", "name": "Sunny Baker", "user_id": "77"}]
    s = cl._impersonation_signals("Sunny Baker", "sunnybaker_2", "", friends, "88")
    assert any("someone you follow" in x for x in s)
    assert not cl._impersonation_signals("Sunny Baker", "sunnybaker", "", friends, "77")  # the friend herself


# 7 + 12. cards
def test_counts_and_card_text():
    a = {"handle": "x1", "post_count": 2, "followers_count": 3, "following_count": 900}
    assert ct.counts_text(a) == "2 posts · 3 followers · 900 following"
    assert "Not available" in ct.counts_text({"handle": "x2"})
    assert ct.prompt("Pick bots.").endswith(ct.REVIEW_NOTE) and ct.CARD_SIZE == 5


def test_rendered_cards(env):
    import build_candidate_cards as bcc
    res = bcc.build_cards_for_snapshot(UK, env["sid"], env["root"])
    for c in res["render"].values() if isinstance(res["render"], dict) else res["render"]:
        spec = c["card_spec"]
        assert spec["multiSelect"] and spec["allowCustom"] is False
        assert spec["prompt"].endswith("Unmarked accounts will be kept in review.")
        assert spec["options"][-1]["label"] == f"Mark all {len(spec['options']) - 1} for termination"
        assert spec["options"][-1]["style"] == "danger" and spec["title"] == f"Round {c['round']} of {c['of']}: which should I terminate?"
        assert len(spec["options"]) <= 6 and all("following" in o["label"] for o in spec["options"][:-1])
        assert c["links_message"]


# 2. protection recheck
def test_recheck_interaction_and_keepers():
    fresh = {"user_id": "5", "handle": "a", "i_follow": False, "verified_type": "none"}
    assert "interaction" in pr.execution_protection_reason(dict(fresh, recent_interaction=True), require_interaction=True)
    assert "treated as protected" in pr.execution_protection_reason(fresh, require_interaction=True)
    assert "Keepers" in pr.execution_protection_reason(dict(fresh, recent_interaction=False),
                                                       keepers=[{"handle": "a", "x_user_id": "5"}],
                                                       require_interaction=True)
    assert pr.execution_protection_reason(dict(fresh, recent_interaction=False), require_interaction=True) is None
    assert "you follow" in pr.execution_protection_reason(dict(fresh, i_follow=True, recent_interaction=False),
                                                          require_interaction=True)


def test_runner_skips_recent_interaction(env):
    sel = select(env)
    a = DryTestAdapter(fresh={sel[0]: {"recent_interaction": True}})
    run(env, a)
    assert ("remove", sel[0]) not in a.calls


# 5. lock + reconcile
def test_one_run_at_a_time(env):
    select(env)
    with rr.run_lock(UK, env["root"], "removal", env["sid"]):
        with pytest.raises(rr.RefusedError, match="check each account on X"):
            run(env, DryTestAdapter())
    run(env, DryTestAdapter())  # lock released


def test_reconcile_after_interruption(env):
    sel = select(env)
    a = DryTestAdapter(); a.removed.add(sel[0])        # removed on X before the crash, never logged
    with rr.run_lock(UK, env["root"], "removal", env["sid"]):
        pass
    p = st.user_data_root(UK, env["root"]) / rr.LOCK_NAME
    p.write_text(json.dumps({"kind": "removal", "pid": 0}))   # stale lock left by a crash
    out = rr.reconcile_interrupted_run(UK, env["sid"], a, root=env["root"], out=io.StringIO())
    assert any(e.get("status") == "REMOVED" and e.get("handle", "").lstrip("@") == sel[0] for e in hist(env))
    assert ("remove", sel[0]) not in a.calls and out is not None


# 6. confirm on X
def test_removal_logged_only_when_confirmed(env):
    sel = select(env)

    class Sticky(DryTestAdapter):
        def remove(self, account):
            self.calls.append(("remove", account["handle"].lstrip("@")))
            return RemovalResult("ok", "said ok")             # but the account still follows
    run(env, Sticky())
    h = hist(env)
    assert any(e.get("status") == "REMOVAL_NOT_CONFIRMED" for e in h)
    assert not any(e.get("status") == "REMOVED" for e in h)


def test_removed_entries_confirmed(env):
    select(env); run(env, DryTestAdapter())
    rem = [e for e in hist(env) if e.get("status") == "REMOVED"]
    assert rem and all(e.get("confirmed_on_x") for e in rem)


# 3. inactive mutuals
def _mutuals(env, n=5):
    d = st.snapshot_dir(env["sid"], env["root"], user_key=UK)
    rows = json.loads((d / "candidates.json").read_text())
    for i in range(n):
        rows.append({"handle": f"oldfriend{i}", "user_id": f"300000000{i}", "inactive_mutual": True,
                     "mutual_days_inactive": 400, "followed_by_me": True, "post_count": 10,
                     "followers_count": 50, "following_count": 60})
    (d / "candidates.json").write_text(json.dumps(rows))


def test_inactive_mutuals_card_few_per_day_and_explicit(env):
    _mutuals(env)
    c = im.build_card(UK, env["sid"], env["root"], today="2026-10-20")
    assert len(c["accounts"]) == 3 and c["card_spec"]["prompt"].endswith(ct.REVIEW_NOTE)
    assert im.build_card(UK, env["sid"], env["root"], today="2026-10-20")["accounts"] == []   # daily limit
    assert len(im.build_card(UK, env["sid"], env["root"], today="2026-10-21")["accounts"]) == 2
    r = im.record_answer(UK, env["sid"], ["1"], root=env["root"])
    assert len(r["authorized"]) == 1
    auth = rr.authorized_accounts(hist(env), env["sid"])
    assert any(a["inactive_mutual_ok"] for a in auth)


def test_mutuals_never_on_removal_cards(env):
    import build_candidate_cards as bcc
    _mutuals(env)
    res = bcc.build_cards_for_snapshot(UK, env["sid"], env["root"])
    assert "oldfriend0" not in json.dumps(res.get("cards"))


# 4. setup
def test_setup_cap_required_and_bounded(tmp_path):
    import shutil
    (tmp_path / "config").mkdir(); shutil.copy(ROOT / "config/default_user_config.json", tmp_path / "config")
    (tmp_path / "templates").mkdir(); shutil.copy(ROOT / "templates/bot_terminator_book.md", tmp_path / "templates")
    for bad in (0, 101, "x", None):
        with pytest.raises(ValueError):
            new_user.create_user("u1", "h", daily_cap=bad, scan_time="09:00", lists_enabled=False, root=tmp_path)
    with pytest.raises(ValueError):
        new_user.create_user("u1", "h", daily_cap=10, scan_time="9am", lists_enabled=False, root=tmp_path)
    with pytest.raises(TypeError):
        new_user.create_user("u1", "h", root=tmp_path)
    p = new_user.create_user("u1", "h", daily_cap=25, scan_time="08:30", lists_enabled=True, reminder=True, root=tmp_path)
    cfg = json.loads(p.read_text())
    assert cfg["daily_removal_cap"] == 25 and cfg["daily_scan"] == {"time": "08:30", "reminder_via_front_door": True}
    assert "e.g. 10" in new_user.SETUP_QUESTIONS[0] and rr.daily_cap({"daily_removal_cap": 500}) == 100
    plans = new_user.setup_plans(cfg, tmp_path)
    assert plans["routine"]["cron"] == "30 8 * * *" and plans["routine"]["removes_without_marks"] is False
    assert plans["book"][0]["args"]["title"] == "Bot Terminator Book"


# 10. book + sheet
def test_book_template_sections_and_change_log(tmp_path):
    text = rules_book.render({"owner_x_handle": "@demo_owner", "daily_removal_cap": 10,
                              "daily_scan": {"time": "09:00"}})
    for s in rules_book.SECTIONS:
        assert f"## {s}" in text
    assert "{" not in text
    plan = rules_book.rule_change_plan("doc1", "Daily cap 10 -> 20", today="2026-10-21")
    assert plan[-1]["tool"] == "insert_text" and "index" not in plan[-1]["args"]
    assert "2026-10-21: Daily cap 10 -> 20" in plan[-1]["args"]["text"]
    with pytest.raises(ValueError):
        rules_book.rule_change_plan("doc1", " ")


def test_sheet_layout_tabs():
    steps = sheet_layout.setup_plan()
    assert steps[0]["args"]["sheet_titles"] == ["Actions", "Keepers", "In review", "List Graveyard", "Kept Lists", "Protected Lists"]
    rows = sheet_layout.action_rows([{"status": "REMOVED", "entry_id": "e1", "handle": "@a", "confirmed_on_x": True},
                                     {"status": "REMOVED", "entry_id": "e2"}, {"status": "CHAT_SELECTION"}],
                                    already_logged={"e2"})
    assert len(rows) == 1 and rows[0][8] == "yes"


# 11. routine
def test_routine_requires_valid_time():
    with pytest.raises(ValueError):
        daily_routine.routine_spec({"daily_scan": {"time": "25:00"}})
    s = daily_routine.routine_spec({"daily_scan": {"time": "07:05"}})
    assert s["cron"] == "5 7 * * *" and len([x for x in s["steps"] if x.startswith("card")]) == 2
