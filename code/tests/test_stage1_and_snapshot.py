from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_snapshot import build_snapshot, candidate_from_raw  # noqa: E402
from checkpoints import (  # noqa: E402
    checkpoint_classify_freeze,
    checkpoint_list_batch,
    ensure_checkpoints,
    usernames_to_skip,
)
from classify import Candidate, classify  # noqa: E402
from stage1_data import normalize_list_or_api_record, stage1_field_status  # noqa: E402


def test_stage1_defers_when_cheap_fields_missing():
    c = Candidate(user_id="Not available", username="listonly", name="List Only", bio="hi")
    r = classify(c)
    # Missing cheap fields escalate; final label is conservative REVIEW until enriched.
    assert r.get("escalate") is True
    assert r.get("stage1_deferred") is True or r.get("stage1_status") == "STAGE1_DEFER_MISSING_FIELDS"
    assert r.get("label") == "REVIEW"
    joined = " ".join(r.get("signals") or [])
    assert "STAGE1_DEFER_MISSING_FIELDS" in joined


def test_stage1_field_status_and_api_normalize():
    assert stage1_field_status({})["stage1_ready"] is False
    api = normalize_list_or_api_record({
        "id": "12345",
        "username": "apiuser",
        "public_metrics": {"followers_count": 10, "following_count": 20, "tweet_count": 3},
        "created_at": "2020-01-01T00:00:00Z",
    })
    assert api["user_id"] == "12345"
    assert api["followers_count"] == 10
    assert api["_stage1_status"]["stage1_ready"] is True
    bad = normalize_list_or_api_record({"username": "x", "user_id": "not-a-number"})
    assert bad["user_id"] == "Not available"


def test_candidate_user_id_never_username():
    c = candidate_from_raw({"username": "OnlyHandle", "name": "X"})
    assert c.user_id == "Not available"
    assert c.username == "OnlyHandle"
    c2 = candidate_from_raw({"username": "h", "id": "42"})
    assert c2.user_id == "42"


def test_snapshot_schema_review_index_and_meta(tmp_path: Path):
    raw = [{"username": "a1", "name": "A", "verified": False, "you_follow_them": False}]
    c = candidate_from_raw(raw[0])
    result = classify(c)
    directory = build_snapshot(
        raw,
        [(c, result)],
        root=tmp_path,
        user_key="example_owner",
        snapshot_id="snap_test_schema_001",
        account_handle=None,
        scan_started="2026-09-30T10:00:00-07:00",
        scan_completed="2026-09-30T10:05:00-07:00",
        operating_mode="review",
    )
    meta = json.loads((directory / "meta.json").read_text())
    assert meta["scan_started"].startswith("2026-09-30")
    assert meta["scan_completed"].startswith("2026-09-30")
    assert meta["schema_version"] == 2
    assert meta["account"] is None
    cands = json.loads((directory / "candidates.json").read_text())
    assert cands[0]["user_id"] == "Not available"
    assert cands[0]["review_number"] == 1
    idx = json.loads((directory / "review_index.json").read_text())
    assert idx["immutable"] is True
    assert idx["accounts"][0]["permanent_review_number"] == 1


def test_checkpoints_atomic_resume(tmp_path: Path):
    uk = "example_owner"
    ensure_checkpoints(tmp_path, user_key=uk)
    checkpoint_list_batch(batch_index=0, usernames=["Alice", "bob"], unique_count=2, root=tmp_path, user_key=uk)
    skip = usernames_to_skip(tmp_path, user_key=uk, phase="list")
    assert "alice" in skip and "bob" in skip
    checkpoint_classify_freeze(snapshot_id="snap_x", root=tmp_path, user_key=uk)
    assert (tmp_path / "data/users/example_owner/checkpoints.json").is_file()
    assert not (tmp_path / "data/checkpoints.json").exists()
    cp = ensure_checkpoints(tmp_path, user_key=uk)
    assert cp["last_snapshot_id"] == "snap_x"
    assert cp["classify_freeze"]["status"] == "frozen"
