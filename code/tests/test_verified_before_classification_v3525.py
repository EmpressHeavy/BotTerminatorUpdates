"""v3.5.25 (Hive Mind 2026-W47): a paid-verified follower must never come out as REVIEW.

Verified status is decided BEFORE any scoring, from every spelling a source might use (snake_case, camelCase,
nested X GraphQL objects, list-scrape badge fields, About page). The real pipeline entry point
(build_snapshot.candidate_from_raw -> classify) is exercised, not just the protections helper.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import classify as cl  # noqa: E402
from build_snapshot import candidate_from_raw  # noqa: E402
from build_candidate_cards import exclusion_reason  # noqa: E402
from classify import classify  # noqa: E402
from protections import is_verified  # noqa: E402

SUSPECT_LABELS = ("REVIEW", "BOT-LIKE / REMOVE CANDIDATE", "BOT-LIKE + INACTIVE / REMOVE CANDIDATE",
                  "INACTIVE / REMOVE CANDIDATE")

BOTTISH = dict(user_id="88001", username="crypto_pin_7710", name="Crypto Pin", followers_count=2,
               following_count=7000, post_count=1200, created_at="2026-10-20T00:00:00Z", has_default_avatar=True,
               bio="", days_inactive=300)

VERIFIED_SHAPES = [
    {"is_blue_verified": True},
    {"isBlueVerified": True},
    {"verified_type": "blue"},
    {"verifiedType": "Blue"},
    {"paid_verified": "yes"},
    {"blue_check": True},
    {"checkmark": "blue"},
    {"is_verified_organization": True},
    {"legacy": {"verified": True}},
    {"verification": {"verified": True}},
    {"verification_info": {"is_verified": True}},
    {"about": {"about_read": True, "verified": "Yes", "verified_detail": "since September 2026"}},
]


@pytest.mark.parametrize("shape", VERIFIED_SHAPES, ids=lambda s: next(iter(s)))
def test_paid_verified_never_review_through_pipeline(shape):
    cand = candidate_from_raw({**BOTTISH, **shape})
    assert is_verified(cand)
    r = classify(cand)
    assert r["label"] not in SUSPECT_LABELS
    assert r.get("protection_gate") == "verified"
    assert r.get("removal_card_eligible") in (False, None)


@pytest.mark.parametrize("shape", VERIFIED_SHAPES, ids=lambda s: next(iter(s)))
def test_verified_gate_runs_before_scoring(shape, monkeypatch):
    def boom(*a, **k):  # stage 2 scoring must never run for a verified account
        raise AssertionError("stage2 scoring ran for a verified account")
    monkeypatch.setattr(cl, "stage2_classify", boom)
    r = classify(candidate_from_raw({**BOTTISH, **shape}))
    assert r.get("protection_gate") == "verified"


@pytest.mark.parametrize("shape", VERIFIED_SHAPES, ids=lambda s: next(iter(s)))
def test_review_cards_drop_verified_even_if_old_label_is_review(shape):
    acct = {"handle": "crypto_pin_7710", "user_id": "88001", "label": "REVIEW", **shape}
    assert exclusion_reason(acct) == "verified"


@pytest.mark.parametrize("shape", [{"verified_type": "none"}, {"is_blue_verified": False}, {"isBlueVerified": False},
                                   {"verification": {"verified": False}}, {"checkmark": ""}])
def test_unverified_shapes_still_evaluated(shape):
    r = classify(candidate_from_raw({**BOTTISH, **shape}))
    assert r.get("protection_gate") != "verified"
