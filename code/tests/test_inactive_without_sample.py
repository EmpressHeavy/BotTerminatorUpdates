"""Inactive detection without an activity sample + large-list chunked classification (offline, fake data)."""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_snapshot import candidate_from_raw
from classify import classify
import classify_batch as cb

DEMO = {r["username"]: r for r in json.loads((ROOT / "tests/fixtures/demo_followers.json").read_text())["records"]}
AS_OF = "2026-10-16T12:00:00+00:00"
INACTIVE = "INACTIVE / REMOVE CANDIDATE"
NOSAMPLE = {"original": 0, "replies": 0, "quotes": 0, "reposts": 0, "sample_size": 0, "insufficient": True}


def base(**kw):
    r = {"username": "fake_x", "name": "Fake", "user_id": "2000009999", "verified": False, "you_follow_them": False,
         "follows_you": True, "deep_inspected": True, "account_country_unavailable": True, "followers_count": 90,
         "following_count": 150, "post_count": 300, "account_age_days": 3200, "bio": "hello",
         "has_default_avatar": False, "profile_complete": True, "activity": dict(NOSAMPLE)}
    r.update(kw)
    return r


def lab(r, **kw):
    return classify(candidate_from_raw(r), as_of=AS_OF, **kw)


def test_demo_07_no_sample_is_inactive():
    res = lab(DEMO["demo_07"])
    assert res["label"] == INACTIVE and res["inactivity_basis"] == "profile_fields"


def test_old_last_post_date_without_sample_is_inactive():
    res = lab(base(last_post_at="2025-08-01T00:00:00Z"))
    assert res["label"] == INACTIVE and res["days_inactive"] >= 400
    assert lab(base(status_created_at="Wed Oct 10 20:19:24 +0000 2018"))["label"] == INACTIVE


def test_recent_last_post_date_is_not_inactive():
    assert lab(base(last_post_at="2026-10-01T00:00:00Z"))["label"] not in (INACTIVE,)


def test_zero_posts_old_account_is_review_not_inactive():
    res = lab(base(post_count=0))
    assert res["label"] == "REVIEW" and not res["inactive"]
    assert any("Zero posts" in s for s in res["signals"])


def test_zero_posts_plus_old_last_date_is_inactive():
    assert lab(base(post_count=0, last_post_at="2024-01-01T00:00:00Z"))["label"].endswith("INACTIVE / REMOVE CANDIDATE")


def test_low_post_rate_alone_is_review():
    res = lab(base(post_count=3))
    assert res["label"] == "REVIEW" and not res["inactive"]


def test_missing_date_fields_never_inactive_and_shown_not_available():
    res = lab(base())
    assert res["label"] in ("KEEP", "REVIEW") and not res["inactive"]
    assert res["days_inactive"] == "Not available"
    res2 = lab(base(post_count=None, account_age_days=None))
    assert not res2["inactive"] and res2["label"] == "REVIEW"


def test_future_or_bad_dates_ignored():
    assert not lab(base(last_post_at="2030-01-01T00:00:00Z"))["inactive"]
    assert not lab(base(last_post_at="garbage"))["inactive"]


def test_activity_sample_takes_precedence():
    active = {"original": 45, "replies": 40, "quotes": 5, "reposts": 10, "sample_size": 100}
    # sample present: legacy days-based rule only; a stale profile date is ignored
    assert lab(base(activity=active, last_post_at="2024-01-01T00:00:00Z"))["label"] == "KEEP"
    assert lab(DEMO["demo_04"])["label"] == "BOT-LIKE + INACTIVE / REMOVE CANDIDATE"


def test_switch_off_restores_legacy():
    assert lab(DEMO["demo_07"], inactivity_cfg={"use_profile_fields_without_sample": False})["label"] == "KEEP"


def test_protected_never_labelled_for_removal():
    for extra in ({"you_follow_them": True}, {"verified": True}):
        res = lab(base(last_post_at="2020-01-01T00:00:00Z", post_count=0, **extra))
        assert "REMOVE CANDIDATE" not in (res["label"] or "") and not res["candidate"]
    cand = candidate_from_raw(base(last_post_at="2020-01-01T00:00:00Z"), [{"user_id": "2000009999"}])
    assert "REMOVE CANDIDATE" not in (classify(cand, as_of=AS_OF)["label"] or "")


def test_fixture_regression_only_demo_07_changes():
    expected = {"demo_01": "BOT-LIKE / REMOVE CANDIDATE", "demo_02": "BOT-LIKE / REMOVE CANDIDATE",
                "demo_03": "BOT-LIKE / REMOVE CANDIDATE", "demo_04": "BOT-LIKE + INACTIVE / REMOVE CANDIDATE",
                "demo_05": "KEEP", "demo_06": "KEEP", "demo_07": INACTIVE, "demo_08": "KEEP",
                "demo_09": "PROTECTED / DO NOT REMOVE", "demo_10": "KEEP",
                "demo_11": "BOT-LIKE / REMOVE CANDIDATE", "demo_12": "KEEP"}
    assert {u: lab(r)["label"] for u, r in DEMO.items()} == expected


def _synthetic(n):
    out = []
    for i in range(n):
        r = base(username=f"synth_{i:05d}", user_id=str(3000000000 + i), name=f"Synthetic Person {i}")  # unique names (impersonation flag 2026-10-20)
        k = i % 5
        if k == 0: r["last_post_at"] = "2025-01-01T00:00:00Z"
        elif k == 1: r["post_count"] = 0
        elif k == 2: r["activity"] = {"original": 45, "replies": 40, "quotes": 5, "reposts": 10, "sample_size": 100}
        elif k == 3: r["you_follow_them"] = True; r["last_post_at"] = "2020-01-01T00:00:00Z"
        out.append(r)
    return out


def test_scale_10k_all_classified_with_checkpoint_resume(tmp_path):
    recs = _synthetic(10_000)
    prog = tmp_path / "classify_progress.json"
    t = time.perf_counter()
    part = cb.classify_in_chunks(recs, chunk_size=1000, progress_path=prog, as_of=AS_OF, stop_after_chunks=4)
    assert part["interrupted"] and prog.exists()
    assert part["not_evaluated"] == 6000  # unfinished shown as NOT EVALUATED, never KEEP
    assert all(r["label"] != "KEEP" for _, r in part["classifications"][4000:])
    full = cb.classify_in_chunks(recs, chunk_size=1000, progress_path=prog, as_of=AS_OF)
    assert full["resumed_chunks"] == 4 and full["classified"] == 10_000 and full["not_evaluated"] == 0
    assert not prog.exists()
    labels = [r["label"] for _, r in full["classifications"]]
    assert len(labels) == 10_000
    assert labels[0] == INACTIVE and labels[1] == "REVIEW" and labels[2] == "KEEP"
    assert labels[3] == "PROTECTED / DO NOT REMOVE"
    assert time.perf_counter() - t < 30


def test_stale_progress_for_other_input_is_not_reused(tmp_path):
    prog = tmp_path / "p.json"
    cb.classify_in_chunks(_synthetic(20), chunk_size=5, progress_path=prog, as_of=AS_OF, stop_after_chunks=1)
    res = cb.classify_in_chunks(_synthetic(15), chunk_size=5, progress_path=prog, as_of=AS_OF)
    assert res["resumed_chunks"] == 0 and res["classified"] == 15


def test_bad_record_is_not_evaluated(monkeypatch):
    def boom(*a, **k): raise ValueError("x")
    monkeypatch.setattr(cb, "classify", boom)
    res = cb.classify_in_chunks([base()], as_of=AS_OF)
    assert res["classifications"][0][1]["label"] == cb.NOT_EVALUATED and res["not_evaluated"] == 1
