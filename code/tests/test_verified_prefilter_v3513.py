"""v3.5.13: ANY verified account is excluded before classification and is never a suspect."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from about_account import parse_about_text  # noqa: E402
from build_candidate_cards import exclusion_reason  # noqa: E402
from classify import ActivityFingerprint, Candidate, classify  # noqa: E402
from protections import apply_protections, is_verified, verified_reason  # noqa: E402

SUSPECT_LABELS = ("REVIEW", "BOT-LIKE / REMOVE CANDIDATE", "BOT-LIKE + INACTIVE / REMOVE CANDIDATE",
                  "INACTIVE / REMOVE CANDIDATE")


def _bot(**kw) -> Candidate:
    base = dict(user_id="77001", username="money_pin_9921", name="Crypto Money", followers_count=3,
                following_count=8000, post_count=900, account_age_days=20, has_default_avatar=True, bio="",
                deep_inspected=True, activity=ActivityFingerprint(0, 0, 0, 100, sample_size=100),
                days_inactive=200, verified=False)
    base.update(kw)
    return Candidate(**base)


def _assert_not_suspect(r):
    assert r["label"] not in SUSPECT_LABELS
    assert r.get("candidate") is False and r.get("bot_like") is False
    assert r.get("removal_card_eligible") in (False, None)
    assert r.get("protection_gate") == "verified"


@pytest.mark.parametrize("text", [
    "Date joined\nMarch 2021\nVerified, since September 2026",
    "Verified since September 2026",
    "Verified\nSince September 2026",
    "Verified: Yes",
])
def test_about_page_verified_status_parsed(text):
    assert parse_about_text(text)["verified"] == "Yes"


def test_about_page_unverified_not_verified():
    assert parse_about_text("Verified\nNot verified")["verified"] != "Yes"
    assert not is_verified(_bot(about={"about_text": "Date joined\nMarch 2021"}))


def test_live_bug_paid_blue_from_about_page_never_review():
    # No checkmark seen in the list (verified=False), but the About page says Verified.
    c = _bot(about={"about_read": True, "verified": "Yes", "verified_detail": "since September 2026"})
    assert "About page" in verified_reason(c)
    _assert_not_suspect(classify(c))


def test_about_text_verified_comma_form():
    c = _bot(about="Date joined\nMarch 2021\nVerified, since September 2026")
    _assert_not_suspect(classify(c))


@pytest.mark.parametrize("vt", ["blue", "business", "government", "Blue"])
def test_every_verified_type_is_excluded(vt):
    _assert_not_suspect(classify(_bot(raw={"verified_type": vt})))


@pytest.mark.parametrize("key", ["is_blue_verified", "is_verified", "verified", "legacy_verified"])
def test_raw_verified_flags_excluded(key):
    _assert_not_suspect(classify(_bot(raw={key: True})))


def test_verified_gate_before_classification_no_scoring():
    d = apply_protections(_bot(verified=True))
    assert d is not None and d.gate == "verified" and d.stage == "protected"
    r = classify(_bot(verified=True))
    assert "bot_score" not in r or not r.get("bot_score")


def test_unverified_still_evaluated():
    r = classify(_bot(raw={"verified_type": "none"}))
    assert r.get("protection_gate") != "verified"
    assert r["label"] in SUSPECT_LABELS


def test_candidate_cards_exclude_about_verified():
    acct = {"handle": "x1", "user_id": "1", "label": "REVIEW", "verified_type": "none",
            "about": {"verified": "Yes"}}
    assert exclusion_reason(acct) == "verified"
    assert exclusion_reason({**acct, "about": {}, "is_blue_verified": True}) == "verified"
