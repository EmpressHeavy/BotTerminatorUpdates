"""v3.5.24: optional tip prompt. Counter and cadence only. Nothing here touches X or the network.

First prompt on the 10th counted use after setup, then at most every 7 days.
Maybe later keeps that gap. Remind me monthly, or dismissing the prompt, switches to 30 days.
There is no forever off switch, and setup never counts or shows.
"""
import datetime as dt
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import daily_routine
import tip_prompt as tip

T0 = dt.datetime(2026, 11, 2, 18, 0, tzinfo=dt.timezone.utc)
UK = "demo_owner"
PNG_SHA256 = "37f19ecd03e4a6242df39231e11deea662dc16cee297cc9bd96a562bb8747cec"


def _finish(root, uk=UK):
    done = tip.mark_setup_complete(uk, root=root)
    assert done["show"] is False and done["blocks"] is False
    return done


def _show_first(root, uk=UK, now=T0):
    _finish(root, uk)
    last = None
    for _ in range(9):
        last = tip.record_use(uk, kind="scan", root=root, now=now)
    assert last["show"] is False and last["uses"] == 9
    shown = tip.record_use(uk, kind="scan", root=root, now=now)
    assert shown["show"] is True and shown["uses"] == 10
    return shown


def _state(root, uk=UK):
    return json.loads(tip.state_path(uk, root).read_text(encoding="utf-8"))


def test_prompt_text_links_and_card_are_exact():
    assert tip.PROMPT == ("Wow you seem to be using Bot Terminator a lot lately! "
                          "Would you mind sending my creator a tip? 🪙")
    assert [item["url"] for item in tip.LINKS] == [
        "https://buy.stripe.com/aFacN40Mw0Arcz02VubMQ00",
        "https://cash.app/$EmpressHeavy",
        "https://venmo.com/u/EmpressHeavy",
        "https://x.com/HeavyMetalShip",
    ]
    assert tip.LINKS[3]["handle"] == "@HeavyMetalShip"
    card = tip.card()
    assert [o["label"] for o in card["options"]] == ["Maybe later", "Remind me monthly"]
    assert [o["value"] for o in card["options"]] == ["Maybe later", "Remind me monthly"]
    assert card["prompt"] == tip.PROMPT and card["allowCustom"] is False and card["multiSelect"] is False
    view = tip.presentation()
    assert view["text"] == tip.PROMPT and view["blocks"] is False
    assert "stays free" in view["note"]
    assert view["image_relative"] == "assets/tip/stripe.png"
    assert view["card"]["options"][1]["label"] == "Remind me monthly"
    src = (ROOT / "src" / "tip_prompt.py").read_text(encoding="utf-8")
    assert "Don't ask again" not in src and "opt_out" not in src


def test_stripe_qr_is_a_pregenerated_png():
    path = tip.image_path()
    assert path == ROOT / "assets" / "tip" / "stripe.png"
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == PNG_SHA256
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert width >= 200 and height >= 200


def test_setup_does_not_count_or_show(tmp_path):
    for _ in range(12):
        got = tip.record_use(UK, kind="scan", root=tmp_path, now=T0)
    assert got == {"counted": False, "show": False, "reason": "setup", "uses": 0, "cadence": "weekly",
                   "last_answer": None, "next_eligible": None, "prompt": None, "blocks": False}
    assert not tip.state_path(UK, tmp_path).exists()
    _finish(tmp_path)
    blocked = tip.record_use(UK, kind="scan", root=tmp_path, now=T0, during_setup=True)
    assert blocked["counted"] is False and blocked["show"] is False and blocked["reason"] == "setup"
    assert _state(tmp_path)["uses"] == 0


def test_tenth_use_shows_then_the_same_day_does_not(tmp_path):
    shown = _show_first(tmp_path)
    assert shown["reason"] == "shown" and shown["blocks"] is False
    assert shown["prompt"]["text"] == tip.PROMPT
    assert shown["cadence"] == "weekly"
    again = tip.record_use(UK, kind="session", root=tmp_path, now=T0)
    assert again["counted"] is True and again["show"] is False and again["uses"] == 11
    assert again["reason"] == "cooldown" and again["prompt"] is None
    assert _state(tmp_path)["last_kind"] == "session"
    raw = tip.state_path(UK, tmp_path).read_text(encoding="utf-8")
    assert "stripe" not in raw.lower() and "http" not in raw.lower()


def test_maybe_later_keeps_a_seven_day_gap(tmp_path):
    _show_first(tmp_path)
    ans = tip.handle_answer(UK, "Maybe later", root=tmp_path, now=T0)
    assert ans["ok"] is True and ans["cadence"] == "weekly" and ans["show"] is False
    assert "week" in ans["message"]
    early = tip.record_use(UK, kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=7, seconds=-1))
    assert early["show"] is False and early["reason"] == "cooldown"
    due = tip.record_use(UK, kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=7))
    assert due["show"] is True and due["cadence"] == "weekly" and due["blocks"] is False


def test_remind_me_monthly_switches_to_thirty_days(tmp_path):
    _show_first(tmp_path, "demo_month")
    ans = tip.handle_answer("demo_month", "Remind me monthly!", root=tmp_path, now=T0)
    assert ans["ok"] is True and ans["action"] == "monthly" and ans["cadence"] == "monthly"
    assert "month" in ans["message"]
    week = tip.record_use("demo_month", kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=7))
    assert week["show"] is False and week["cadence"] == "monthly"
    almost = tip.record_use("demo_month", kind="session", root=tmp_path,
                            now=T0 + dt.timedelta(days=30, seconds=-1))
    assert almost["show"] is False
    due = tip.record_use("demo_month", kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=30))
    assert due["show"] is True and due["cadence"] == "monthly"


def test_dismiss_matches_the_monthly_gap(tmp_path):
    _show_first(tmp_path, "demo_dismiss")
    ans = tip.dismiss("demo_dismiss", root=tmp_path, now=T0)
    assert ans["ok"] is True and ans["action"] == "dismissed" and ans["cadence"] == "monthly"
    assert tip.record_use("demo_dismiss", kind="scan", root=tmp_path,
                          now=T0 + dt.timedelta(days=7))["show"] is False
    assert tip.record_use("demo_dismiss", kind="scan", root=tmp_path,
                          now=T0 + dt.timedelta(days=30))["show"] is True
    # a typed wave-off is the same switch
    _show_first(tmp_path, "demo_skip", now=T0 + dt.timedelta(days=40))
    skip = tip.handle_answer("demo_skip", "no thanks", root=tmp_path)
    assert skip["cadence"] == "monthly" and skip["action"] == "dismissed"


def test_maybe_later_does_not_undo_monthly(tmp_path):
    _show_first(tmp_path, "demo_stay")
    tip.handle_answer("demo_stay", "Remind me monthly", root=tmp_path, now=T0)
    later = tip.handle_answer("demo_stay", "remind me later", root=tmp_path, now=T0)
    assert later["action"] == "maybe_later" and later["cadence"] == "monthly"
    assert "month" in later["message"]
    assert tip.record_use("demo_stay", kind="scan", root=tmp_path,
                          now=T0 + dt.timedelta(days=7))["show"] is False
    assert tip.record_use("demo_stay", kind="scan", root=tmp_path,
                          now=T0 + dt.timedelta(days=30))["show"] is True


def test_asking_to_stop_is_not_a_permanent_opt_out(tmp_path):
    _show_first(tmp_path, "demo_stop")
    ans = tip.handle_answer("demo_stop", "Don't ask again", root=tmp_path, now=T0)
    assert ans["cadence"] == "monthly" and ans["blocks"] is False
    raw = tip.state_path("demo_stop", tmp_path).read_text(encoding="utf-8")
    assert "opt_out" not in raw and "forever" not in raw
    assert tip.record_use("demo_stop", kind="scan", root=tmp_path,
                          now=T0 + dt.timedelta(days=29))["show"] is False
    again = tip.record_use("demo_stop", kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=30))
    assert again["show"] is True


def test_unrecognized_answer_leaves_the_weekly_gap(tmp_path):
    _show_first(tmp_path)
    before = _state(tmp_path)
    ans = tip.handle_answer(UK, "hello there", root=tmp_path, now=T0)
    assert ans["ok"] is False and ans["reason"] == "unrecognized" and ans["cadence"] == "weekly"
    assert _state(tmp_path) == before
    assert tip.record_use(UK, kind="scan", root=tmp_path, now=T0 + dt.timedelta(days=7))["show"] is True


def test_owners_do_not_share_a_counter(tmp_path):
    _show_first(tmp_path, "demo_a")
    other = tip.record_use("demo_b", kind="session", root=tmp_path, now=T0)
    assert other["reason"] == "setup" and other["uses"] == 0
    _finish(tmp_path, "demo_b")
    one = tip.record_use("demo_b", kind="session", root=tmp_path, now=T0)
    assert one["uses"] == 1 and one["show"] is False
    assert _state(tmp_path, "demo_a")["uses"] == 10
    assert tip.state_path("demo_a", tmp_path) != tip.state_path("demo_b", tmp_path)
    assert str(tip.state_path("demo_a", tmp_path).relative_to(tmp_path)) == "data/users/demo_a/tip_prompt.json"


def test_counter_file_is_owner_only(tmp_path):
    _finish(tmp_path)
    tip.record_use(UK, kind="scan", root=tmp_path, now=T0)
    mode = os.stat(tip.state_path(UK, tmp_path)).st_mode & 0o777
    assert mode == 0o600


def test_mark_setup_complete_does_not_reset_uses(tmp_path):
    _finish(tmp_path)
    for _ in range(3):
        tip.record_use(UK, kind="scan", root=tmp_path, now=T0)
    again = tip.mark_setup_complete(UK, root=tmp_path)
    assert again["uses"] == 3 and again["show"] is False
    assert _state(tmp_path)["uses"] == 3


def test_during_setup_does_not_show_a_prompt_that_would_otherwise_be_due(tmp_path):
    _show_first(tmp_path)
    later = T0 + dt.timedelta(days=8)
    blocked = tip.record_use(UK, kind="scan", root=tmp_path, now=later, during_setup=True)
    assert blocked["show"] is False and blocked["counted"] is False and blocked["uses"] == 10
    assert _state(tmp_path)["last_prompt_at"].startswith("2026-11-02")
    opened = tip.record_use(UK, kind="scan", root=tmp_path, now=later)
    assert opened["show"] is True and opened["uses"] == 11


def test_absolute_seven_days_across_a_time_zone(tmp_path):
    pt = ZoneInfo("America/Los_Angeles")
    start = dt.datetime(2026, 11, 2, 18, 30, tzinfo=pt)
    _show_first(tmp_path, "demo_tz", now=start)
    stored = _state(tmp_path, "demo_tz")["last_prompt_at"]
    assert stored.endswith("+00:00")
    assert tip.record_use("demo_tz", kind="scan", root=tmp_path,
                          now=start + dt.timedelta(days=7, seconds=-1))["show"] is False
    assert tip.record_use("demo_tz", kind="scan", root=tmp_path,
                          now=start + dt.timedelta(days=7))["show"] is True


def test_bad_kind_and_a_broken_store_do_not_raise(tmp_path):
    bad = tip.record_use(UK, kind="nope", root=tmp_path, now=T0)
    assert bad["reason"] == "bad_kind" and bad["show"] is False and bad["blocks"] is False
    path = tip.state_path("demo_store", tmp_path)
    path.parent.mkdir(parents=True)
    path.mkdir()
    broken = tip.record_use("demo_store", kind="scan", root=tmp_path, now=T0)
    assert broken["reason"] == "store_unavailable" and broken["show"] is False and broken["blocks"] is False
    assert tip.dismiss("demo_store", root=tmp_path)["reason"] == "store_unavailable"
    with pytest.raises(ValueError):
        tip.record_use("Bad Key", kind="scan", root=tmp_path)


def test_scan_step_is_last_and_does_not_gate():
    steps = daily_routine.scan_steps({})
    assert steps[0].startswith("preflight")
    assert steps[-1] == daily_routine.TIP_STEP
    assert "tip_prompt.record_use" in steps[-1] and "never block" in steps[-1].lower()
    assert "first-run setup" in steps[-1] and "Subscribe" not in steps[-1] and "license" not in steps[-1]
    listed = daily_routine.scan_steps({"lists": {"enabled": True}})
    assert listed[-1] == daily_routine.TIP_STEP
    assert any(s.startswith("lists:") for s in listed[:-1])


def _assert_skill(text: str):
    section = text.split("# Optional tip prompt", 1)[1].split("# Automatic updates", 1)[0]
    assert tip.PROMPT in section
    assert "Maybe later" in section and "Remind me monthly" in section
    assert "Don't ask again" not in section
    for url in ("https://buy.stripe.com/aFacN40Mw0Arcz02VubMQ00", "https://cash.app/$EmpressHeavy",
                "https://venmo.com/u/EmpressHeavy", "https://x.com/HeavyMetalShip"):
        assert url in section
    assert "@HeavyMetalShip" in section and "assets/tip/stripe.png" in section
    assert "mark_setup_complete" in section and "10th" in section
    assert "7 days" in section and "30 days" in section
    assert "first-run setup" in section and "stays free" in section
    assert "Latest version only" in text
    assert "never an older tag or commit" in text


def test_instructions_keep_the_prompt_and_the_latest_version_rule():
    _assert_skill((ROOT / "docs/skills/bot-terminator-getting-started.md").read_text(encoding="utf-8"))
    top = ROOT.parent / "skills" / "bot-terminator-getting-started" / "SKILL.md"
    upgrade = ROOT.parent / "UPGRADE.md"
    if not upgrade.exists():
        return
    _assert_skill(top.read_text(encoding="utf-8"))
    voice = (ROOT.parent / "docs" / "voice-and-phrases.md").read_text(encoding="utf-8")
    assert tip.PROMPT in voice
    rules = (ROOT.parent / "docs" / "bot-rules.md").read_text(encoding="utf-8")
    assert tip.PROMPT in rules and "30 days" in rules and "Latest version only" in rules
    text = upgrade.read_text(encoding="utf-8")
    assert "Latest version only" in text
    assert "Never offer or install an older version" in text
    assert "tip prompt" in text.lower()
    assert "never block or delay a scan" in text.lower()
