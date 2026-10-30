"""v3.5.8: X "About this account" page parser, signals, snapshot compatibility, card text and pacing."""
from src import card_text
from src.about_account import (NA, AboutReadPacer, about_from_record, about_read_queue, about_url,
                               connected_via_country, location_mismatch, parse_about_text)
from src.build_snapshot import candidate_from_raw, _ui_candidate
from src.classify import ActivityFingerprint, Candidate, classify, stage2_classify
from src.merge_enrichment import ENRICHMENT_KEYS
from src.read_pacing import PaceEvent

PAGE = """About this account
@sample_acct
Date joined
June 2013
Account based in
United States
Verified
Since March 2023
ID verified
Verified since May 2024
Username changes
4 username changes
Connected via
Bangladesh App Store"""

A11Y = """- heading "About this account" [level=2]
- StaticText "Date joined"
- StaticText "March 2021"
- StaticText "Account based in"
- StaticText "Nigeria"
- StaticText "Connected via"
- StaticText "Nigeria App Store"
"""


def test_parse_visible_text_all_fields():
    a = parse_about_text(PAGE)
    assert a["date_joined"] == "June 2013"
    assert a["account_based_in"] == "United States"
    assert a["verified"] == "Yes"
    assert a["id_verified"] == "Yes"
    assert a["username_changes"] == 4
    assert a["connected_via"] == "Bangladesh App Store"
    assert a["about_read"] is True


def test_parse_accessibility_tree_and_missing_fields_not_invented():
    a = parse_about_text(A11Y)
    assert a["account_based_in"] == "Nigeria" and a["connected_via"] == "Nigeria App Store"
    assert a["date_joined"] == "March 2021"
    for f in ("verified", "id_verified", "username_changes"):
        assert a[f] == NA


def test_parse_empty_and_inline_forms():
    assert all(v == NA for k, v in parse_about_text("").items() if k != "about_read")
    a = parse_about_text("Account based in: Canada\nUsername changes: none\nVerified: Not verified\nConnected via Web")
    assert a["account_based_in"] == "Canada" and a["username_changes"] == 0 and a["verified"] == "No"
    assert a["connected_via"] == "Web" and connected_via_country("Web") is None
    assert parse_about_text("Joined June 2013")["date_joined"] == "June 2013"


def test_mismatch_rules():
    assert location_mismatch(parse_about_text(PAGE))["store_country"] == "Bangladesh"
    assert location_mismatch(parse_about_text(A11Y)) is None
    assert location_mismatch({"account_based_in": "USA", "connected_via": "United States App Store"}) is None
    assert location_mismatch({"account_based_in": "Europe", "connected_via": "Germany App Store"}) is None
    assert location_mismatch({"account_based_in": NA, "connected_via": "Bangladesh App Store"}) is None
    assert location_mismatch({"account_based_in": "India", "connected_via": "Web"}) is None


def _cand(**kw):
    base = dict(user_id="9", username="sample_acct", name="Sample", followers_count=120, following_count=130,
                post_count=300, account_age_days=1500, bio="hi", has_default_avatar=False, deep_inspected=True,
                activity=ActivityFingerprint(40, 30, 10, 20, sample_size=100), days_inactive=2)
    base.update(kw)
    return Candidate(**base)


S1 = {"signals": [], "suspicion": 0}


def test_mismatch_alone_is_review_never_bot():
    r = stage2_classify(_cand(about=parse_about_text(PAGE.replace("ID verified\nVerified since May 2024\n", "")
                                                        .replace("4 username changes", "1 username change"))), S1)
    assert r["about_location_mismatch"] and r["bot_score"] == 1
    assert r["label"] == "REVIEW" and not r["bot_like"]
    assert any("not proof" in s for s in r["signals"])


def test_mismatch_plus_other_signals_can_be_bot_like():
    about = {"account_based_in": "United States", "connected_via": "Bangladesh App Store", "username_changes": 7}
    r = stage2_classify(_cand(about=about), {"signals": [], "suspicion": 1})
    assert r["bot_score"] == 4 and r["bot_like"]


def test_username_changes_signal():
    r = stage2_classify(_cand(about={"username_changes": 3}), S1)
    assert r["bot_score"] == 1 and any("3 username changes" in s for s in r["signals"])
    r = stage2_classify(_cand(about={"username_changes": 2}), S1)
    assert r["bot_score"] == 0


def test_id_verified_is_strong_keep():
    about = {"id_verified": "Yes", "account_based_in": "United States", "connected_via": "Bangladesh App Store",
             "username_changes": 8}
    r = stage2_classify(_cand(about=about), {"signals": [], "suspicion": 3})
    assert r["id_verified"] and not r["bot_like"] and r["label"] != "BOT-LIKE / REMOVE CANDIDATE"


def test_location_alone_never_counts():
    r = stage2_classify(_cand(account_country="Nigeria", about={"account_based_in": "Nigeria"}), S1)
    assert r["bot_score"] == 0 and r["label"] == "KEEP"
    r2 = stage2_classify(_cand(account_country="Nigeria"), {"signals": [], "suspicion": 1})
    assert r2["bot_score"] == 2  # watched country adds weight only alongside another signal


def test_about_fills_account_country():
    r = stage2_classify(_cand(about=parse_about_text(A11Y)), S1)
    assert r["account_country_display"] == "Nigeria"


def test_old_snapshot_records_still_load():
    c = candidate_from_raw({"username": "old_acct", "user_id": "12", "account_country_unavailable": True})
    assert c.about["about_read"] is False and all(c.about[f] == NA for f in ("connected_via", "id_verified"))
    r = classify(c)
    ui = _ui_candidate(c, r)
    assert ui["about_connected_via"] == NA and ui["account_country"] == NA


def test_new_records_carry_about_fields():
    c = candidate_from_raw({"username": "new_acct", "user_id": "13", "about_text": PAGE})
    assert c.about["connected_via"] == "Bangladesh App Store"
    c2 = candidate_from_raw({"username": "flat", "user_id": "14", "about_username_changes": "5",
                             "about_id_verified": True})
    assert c2.about["username_changes"] == 5 and c2.about["id_verified"] == "Yes"
    assert {"about", "about_text"} <= set(ENRICHMENT_KEYS)
    assert about_from_record({})["about_read"] is False


def test_card_stats_line_shows_only_available():
    acct = {"handle": "sample_acct", "post_count": 3, "followers": 4, "following": 900, "label": "BOT-LIKE",
            "about_account_based_in": "United States", "about_connected_via": "Bangladesh App Store",
            "about_username_changes": 4, "about_id_verified": NA, "about_verified": "No",
            "about_date_joined": "June 2013"}
    line = card_text.round_line(1, acct)
    assert "based in United States · connected via Bangladesh App Store · 4 username changes" in line
    assert "joined June 2013" in line and "ID verified" not in line and "Not available" not in line.split("—")[2]
    bare = {"handle": "x1", "post_count": 1, "followers": 1, "following": 1}
    assert card_text.stats_text(bare) == card_text.counts_text(bare)
    assert "ID verified" in card_text.about_text({"about": {"id_verified": "Yes"}})


def test_read_queue_only_stage1_survivors():
    items = [("keep_me", {"escalate": False, "label": "KEEP"}),
             ("prot", {"escalate": False, "label": "PROTECTED / DO NOT REMOVE"}),
             ("@sus", {"escalate": True}), ("sus", {"escalate": True}), ("done", {"escalate": True, "about_read": True})]
    assert about_read_queue(items) == ["sus"]
    assert about_url("@sus") == "https://x.com/sus/about"


def test_pacer_spacing_and_429_stop():
    p = AboutReadPacer()
    assert p.wait_before_next() == 0.0
    p.record("a")
    w = p.wait_before_next()
    assert 8.0 <= w <= 12.0
    for i in range(19):
        p.record(f"b{i}")
    assert p.wait_before_next() == p.burst_pause_s
    st = p.record("c", PaceEvent.RATE_LIMIT_429)
    assert not st["stop"] and p.wait_before_next() == p.cooldown_429_s
    st = p.record("c", PaceEvent.RATE_LIMIT_429)
    assert st["stop"] and not p.can_continue()
    assert p.plan(["a", "c", "z"]) == ["c", "z"]
