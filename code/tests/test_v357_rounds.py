"""v3.5.7 round-based review: synthetic accounts and the TEST-ONLY adapter only."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import build_candidate_cards as bcc, card_text as ct, record_chat_selection as rcs, records, review_rounds as rr7
import removal_runner as rr
from removal_test_adapter import DryTestAdapter
from test_removal_runner import env, UK, hist  # noqa: F401  (fixture)


def acct(i, label):
    return {"user_id": str(9000 + i), "handle": f"synth{i}", "label": label, "post_count": i, "followers": 10,
            "following": 900, "joined": "2026-10-01", "signals": ["Unverified", "Zero posts"], "verified_type": "none"}


def test_rounds_order_bots_first_and_round_card():
    accts = [acct(i, "REVIEW") for i in range(4)] + [acct(10 + i, "BOT-LIKE / REMOVE CANDIDATE") for i in range(3)]
    r = bcc.build_cards(accts)
    assert [a["handle"] for a in r["accounts"]][:3] == ["synth10", "synth11", "synth12"]
    rd = r["render"]
    assert [x["round"] for x in rd] == [1, 2] and rd[0]["of"] == 2
    s1, s2 = rd[0]["card_spec"], rd[1]["card_spec"]
    assert s1["title"] == "Round 1 of 2: which should I terminate?" and s1["multiSelect"] and not s1["allowCustom"]
    assert s1["options"][-1] == {"label": "Mark all 5 for termination", "value": "mark_all", "style": "danger"}
    assert len(s2["options"]) == 3 and s2["options"][-1]["label"] == "Mark all 2 for termination"
    msg = rd[0]["round_message"]
    assert "[@synth10](https://x.com/synth10)" in msg and "likely bot" in msg and "worth a closer look" in msg
    assert "joined 2026-10-01" in msg and "Zero posts" in msg and "900 following" in msg


def test_card_answer_only_no_typed_extras():
    assert rcs.parse_answer(["2", "4"], [1, 2, 3, 4, 5]) == ([2, 4], "card")
    assert rcs.parse_answer(["mark_all"], [6, 7]) == ([6, 7], "Select all")
    assert rcs.parse_answer("Mark all 2 for termination", [6, 7]) == ([6, 7], "Select all")
    assert rcs.parse_answer(["7", "12"], [6, 7])[0] == [7]  # numbers outside the round are ignored
    assert rcs.parse_answer("1. @synth1 — 2 posts · 3 followers · 4 following", [1, 2, 3, 4])[0] == [1]


def test_run_round_terminates_picks_and_reports(env, monkeypatch):
    monkeypatch.setattr(records, "after_write", lambda uk, root=None, cfg=None, **k: {"method": "github", "ok": True})
    nums = env["cards"]["cards"]["1"]
    sleeps = []
    out = rr7.run_round(UK, env["sid"], 1, [str(nums[0]), str(nums[2])], DryTestAdapter(), root=env["root"],
                        sleep=sleeps.append)
    assert out["selected"] == sorted([nums[0], nums[2]]) and sleeps == [rr.PACING_SECONDS]
    assert sum(l.startswith("✅") for l in out["checklist"]) == 2 and sum("kept in review" in l for l in out["checklist"]) == 3
    assert out["backup"]["ok"] and out["report"].startswith("Round 1 of")
    assert (env["dir"] / "graveyard.jsonl").read_text().count("REMOVED") == 2


def test_run_round_stops_for_the_day_on_warning(env, monkeypatch):
    monkeypatch.setattr(records, "after_write", lambda uk, root=None, cfg=None, **k: {})
    nums = env["cards"]["cards"]["1"]
    out = rr7.run_round(UK, env["sid"], 1, ["mark_all"], DryTestAdapter(results=[rr.RemovalResult("warning", "X warning")]),
                        root=env["root"])
    assert out["day_stopped"] and out["next_round"] is None and "stopped for today" in out["report"]


def test_no_unsolicited_file_and_no_old_paths():
    src = "\n".join(p.read_text() for p in (ROOT / "src").glob("*.py"))
    assert "fallback_file" not in src and "typed numbers" not in src and "links first" not in src
    assert "Round" in ct.round_title(1, 1)
