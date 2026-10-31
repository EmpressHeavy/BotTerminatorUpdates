"""v3.5.17: Hive Mind ON by default for Bot Terminator; off-card only on request; monthly toggle card."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import build_monthly_settings_card as mc  # noqa: E402
import hive_setup as hs  # noqa: E402

NOTICE = ("Just so you are aware, Bot Terminator is equipped with a system called Hive Mind, which gets end-user feedback "
          "to my creator so you don't have to reach out via social media and risk your feedback getting missed. Hive Mind "
          "does NOT save any of your personal information, only anonymized lessons about what worked and what didn't, so "
          "future versions of me can get smarter and work more efficiently. I send those lessons about once a week on my own. :)")
PROMPT = ("Why leave this on? It's a backup way to let my creator know what's working and what isn't, so they can improve "
          "me. Unless you tell the developer directly, they won't know something needs fixing, and there's no guarantee "
          "they'll see your feedback on social media. (We really hope they do, so may the algorithm be in your favor \U0001f3b2) "
          "Your personal info is never shared, and you can turn it off anytime.")
SKILL = (ROOT / "docs/skills/bot-terminator-getting-started.md").read_text()
HSKILL = (ROOT / "docs/skills/hive-mind.md").read_text()


def test_exact_texts():
    assert hs.NOTICE == NOTICE and hs.OFF_PROMPT == PROMPT
    assert hs.off_request_card()["buttons"] == ["Keep Hive Mind on", "Turn off Hive Mind"]


def test_setup_is_on_without_question():
    p = hs.setup_plan("/x/brain.db", "America/Chicago")
    assert p["card"] is None and p["ask"] is False and p["message"] == NOTICE
    assert "MEM_DB=/x/brain.db hive on --bot bt" in p["steps"] and p["steps"][-1].endswith("hive status")
    r = p["create_routine"]
    assert r["name"] == "Hive Mind weekly share" and "hive auto" in r["content"] and r["silent_unless_error"]
    assert PROMPT not in p["message"]


def test_off_flow():
    assert hs.handle_off_answer("Keep Hive Mind on")["enabled"] is True
    assert hs.handle_off_answer("Keep Hive Mind on")["delete_routine"] is None
    off = hs.handle_off_answer("Turn off Hive Mind")
    assert off["steps"] == ["hive off"] and off["delete_routine"] == "Hive Mind weekly share" and off["enabled"] is False
    assert "\n" not in off["message"]
    on = hs.turn_on_plan()
    assert on["steps"][0] == "hive on --bot bt" and on["create_routine"]["name"] == "Hive Mind weekly share"


def test_monthly_toggle_card_and_routine():
    card = mc.build_toggle_card({}, True)
    assert card["multi_select"] and "Hive Mind: ON" in card["options"] and len(card["options"]) == 5
    assert all(PROMPT not in x for x in card["companion_lines"] + [card["prompt"]])
    assert "never your personal info" in card["companion_lines"][0] and "once a week" in card["companion_lines"][0]
    assert mc.apply_toggles(card, ["Hive Mind: ON"]) == {"hive_mind": False}
    assert mc.apply_toggles(card, []) == {}
    assert "Hive Mind: OFF" in mc.build_toggle_card({}, False)["options"]
    assert hs.monthly_routine_action(False, True) == {"delete_routine": "Hive Mind weekly share"}
    assert "create_routine" in hs.monthly_routine_action(True, False)
    assert hs.monthly_routine_action(True, True) == {}


def test_skills_match():
    for doc in (SKILL, HSKILL):
        assert NOTICE in doc and PROMPT in doc
        assert "One optional suggestion" not in doc and "Want it on?" not in doc
    assert "hive on --bot bt" in SKILL and "Hive Mind weekly share" in SKILL
    monthly = [l for l in SKILL.splitlines() if l.startswith("- **Monthly check-in (Hive Mind):**")][0]
    assert "build_toggle_card" in monthly and PROMPT not in monthly
