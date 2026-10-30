"""Protections must win over extreme bot-like signals (Review Mode defaults)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from classify import ActivityFingerprint, Candidate, classify  # noqa: E402
from product_config import ProtectionPolicy  # noqa: E402
from protections import apply_protections  # noqa: E402


def _extreme_bot(**kwargs) -> Candidate:
    base = dict(
        user_id="999001",
        username="ElonMusk298472",
        name="Fake Elon Musk Official",
        followers_count=2,
        following_count=9000,
        post_count=500,
        account_age_days=10,
        has_default_avatar=True,
        bio="",
        deep_inspected=True,
        account_country="Nigeria",
        activity=ActivityFingerprint(0, 0, 0, 100, sample_size=100),
        days_inactive=5,
        verified=False,
        followed_by_me=False,
        always_keep=False,
    )
    base.update(kwargs)
    return Candidate(**base)


def test_followed_account_never_bot_like_removal_candidate():
    c = _extreme_bot(followed_by_me=True)
    r = classify(c)
    assert r["stage"] == "protected"
    assert r["label"] == "PROTECTED / DO NOT REMOVE"
    assert r.get("bot_like") is False
    assert r.get("candidate") is False
    assert "REMOVE CANDIDATE" not in (r.get("label") or "")


def test_verified_excluded_never_bot_like_removal_candidate():
    c = _extreme_bot(verified=True, username="SomeVerifiedSpam", name="Spam")
    r = classify(c)
    assert r["stage"] == "protected"
    assert r["label"] == "KEEP"
    assert r.get("bot_like") is False
    assert r.get("candidate") is False
    assert "Verified" in " ".join(r.get("signals") or [])


def test_always_keep_never_bot_like_removal_candidate():
    c = _extreme_bot(always_keep=True, username="kept_spam_bot", name="Kept")
    r = classify(c)
    assert r["stage"] == "protected"
    assert r["label"] == "ALWAYS KEEP / DO NOT REMOVE"
    assert r.get("bot_like") is False
    assert r.get("candidate") is False


def test_unprotected_extreme_can_be_bot_like():
    c = _extreme_bot()
    r = classify(c)
    assert r.get("bot_like") is True
    assert "BOT-LIKE" in (r.get("label") or "")


def test_verified_exclusion_cannot_be_disabled():
    """v3.5.13 owner rule: verified is a hard pre-filter; the old config switch no longer turns it off."""
    c = _extreme_bot(verified=True, username="ver_spam", name="Spam")
    policy = ProtectionPolicy(exclude_verified_from_removal=False)
    d = apply_protections(c, policy)
    assert d is not None and d.gate == "verified"
    r = classify(c, policy=policy)
    assert r.get("bot_like") is False and r.get("candidate") is False
