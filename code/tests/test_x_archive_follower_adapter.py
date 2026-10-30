"""Synthetic ZIP tests for the X account-archive follower adapter.

Fixtures under tests/fixtures/synthetic_x_archive are labeled
SYNTHETIC_NOT_REAL_USER_DATA. They are not a real X archive.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from x_archive_follower_adapter import (  # noqa: E402
    diff_archive_loads,
    hand_records_to_existing_pipeline,
    load_x_archive_followers,
)

FIXTURES = ROOT / "tests" / "fixtures" / "synthetic_x_archive"
ACCOUNT = "@synthetic_archive_owner"
SECRETS = (
    "DM_SECRET_TOKEN_do_not_retain_9f3a",
    "TWEET_SECRET_TOKEN_do_not_retain_aa11",
    "PERSONALIZATION_SECRET_TOKEN_bb22",
    "AD_SECRET_TOKEN_cc33",
    "CONTACT_SECRET_TOKEN_dd44",
    "LOCATION_SECRET_TOKEN_ee55",
    "MEDIA_SECRET_TOKEN_ff66",
    "UNRELATED_SECRET_TOKEN_gg77",
    "SCHEMA_GUESS_SECRET_jj00",
)


def test_follower_file_found():
    result = load_x_archive_followers(FIXTURES / "follower_and_sensitive.zip", ACCOUNT)
    assert result["status"] == "OK"
    assert result["account_handle"] == ACCOUNT
    assert result["provenance"]["account_handle_origin"] == "caller_parameter"
    assert result["provenance"]["schema"] == "UNKNOWN"
    assert result["provenance"]["export_timestamp"] == "2026-02-01T00:00:00Z"
    assert result["provenance"]["export_timestamp_key"] == "export_timestamp"
    assert result["record_count"] == 2
    handles = {row["handle"] for row in result["records"]}
    assert handles == {"synth_full", "synth_sparse"}
    assert "data/follower.json" in result["files_accessed"]
    assert "data/manifest.json" in result["files_accessed"]
    assert all(row["source"] == "X_ACCOUNT_ARCHIVE" for row in result["records"])


def test_sensitive_files_ignored_and_contents_not_loaded():
    calls = []
    original = zipfile.ZipFile.read

    def wrapped(self, name, pwd=None):
        calls.append(name)
        return original(self, name, pwd)

    zipfile.ZipFile.read = wrapped
    try:
        result = load_x_archive_followers(
            FIXTURES / "follower_and_sensitive.zip", ACCOUNT
        )
    finally:
        zipfile.ZipFile.read = original

    blob = json.dumps(result)
    for secret in SECRETS:
        assert secret not in blob
    ignored = {item["path"]: item["category"] for item in result["files_ignored"]}
    assert ignored["data/direct-messages.js"] == "direct_message"
    assert ignored["data/tweets.js"] == "tweet"
    assert ignored["data/personalization.js"] == "personalization"
    assert ignored["data/ad-impressions.js"] == "ad"
    assert ignored["data/contact.js"] == "contact"
    assert ignored["data/location.js"] == "location"
    assert ignored["data/media/photo.jpg"] == "media"
    assert "data/account-notes.txt" in result["files_not_accessed"]
    read_names = set(calls)
    assert "data/direct-messages.js" not in read_names
    assert "data/tweets.js" not in read_names
    assert "data/personalization.js" not in read_names
    assert "data/ad-impressions.js" not in read_names
    assert "data/media/photo.jpg" not in read_names
    assert read_names <= {"data/manifest.json", "data/follower.json"}


def test_missing_metrics_stay_not_available():
    result = load_x_archive_followers(FIXTURES / "follower_and_sensitive.zip", ACCOUNT)
    sparse = next(row for row in result["records"] if row["handle"] == "synth_sparse")
    full = next(row for row in result["records"] if row["handle"] == "synth_full")
    assert sparse["missing"]["public_metrics"] == "Not available"
    assert "public_metrics" not in sparse
    assert sparse.get("public_metrics") != 0
    assert "followers_count" not in sparse
    assert sparse["missing"]["verified"] == "Not available"
    assert "verified" not in sparse
    assert sparse.get("verified") is not False
    assert sparse.get("protected") is not False
    assert sparse.get("you_follow_them") is not False
    assert full["verified"] is False  # present in the file; not invented
    assert full["public_metrics"] == {"followers_count": 4}
    assert "following_count" not in full["public_metrics"]
    assert 0 not in full["public_metrics"].values()
    # archive export time fills source_timestamp only because the manifest had one
    assert sparse["source_timestamp"] == "2026-02-01T00:00:00Z"
    assert sparse["source_timestamp_origin"] == "archive_export"


def test_no_follower_file_is_blocked_without_reading_other_json():
    calls = []
    original = zipfile.ZipFile.read

    def wrapped(self, name, pwd=None):
        calls.append(name)
        return original(self, name, pwd)

    zipfile.ZipFile.read = wrapped
    try:
        result = load_x_archive_followers(FIXTURES / "no_follower_file.zip", ACCOUNT)
    finally:
        zipfile.ZipFile.read = original

    assert result["status"] == "BLOCKED"
    assert result["block_reason"] == "NO_RECOGNIZABLE_FOLLOWER_FILE"
    assert result["records"] == []
    blob = json.dumps(result)
    assert "TWEET_ONLY_SECRET_hh88" not in blob
    assert "DM_ONLY_SECRET_ii99" not in blob
    assert "data/tweets.js" not in calls
    assert "data/direct-messages.js" not in calls


def test_unrecognized_keys_do_not_guess_fields():
    result = load_x_archive_followers(
        FIXTURES / "unrecognized_follower_keys.zip", ACCOUNT
    )
    assert result["status"] == "BLOCKED"
    assert result["block_reason"] == "UNRECOGNIZED_FOLLOWER_SCHEMA"
    assert result["records"] == []
    assert "accountId" in result["observed_follower_keys"]
    assert "screenName" in result["observed_follower_keys"]
    blob = json.dumps(result)
    assert "SCHEMA_GUESS_SECRET_jj00" not in blob
    assert "not_a_contract_key" not in blob
    assert "555" not in blob


def test_delta_new_disappeared_unchanged_preserves_timestamps():
    baseline = load_x_archive_followers(FIXTURES / "delta_baseline.zip", ACCOUNT)
    current = load_x_archive_followers(FIXTURES / "delta_current.zip", ACCOUNT)
    delta = diff_archive_loads(baseline, current)
    assert delta["status"] == "OK"
    assert delta["not_a_bot_terminator_removal"] is True
    assert delta["disappeared_meaning"] == "ABSENT_FROM_LATER_ARCHIVE"
    assert delta["cause"] == "UNKNOWN"
    assert delta["baseline_export_timestamp"] == "2026-04-01T00:00:00Z"
    assert delta["current_export_timestamp"] == "2026-05-01T00:00:00Z"

    new_ids = [item["identity"] for item in delta["new_identities"]]
    gone_ids = [item["identity"] for item in delta["disappeared"]]
    same_ids = [item["identity"] for item in delta["unchanged"]]
    changed_ids = [item["identity"] for item in delta["changed"]]
    assert new_ids == ["id:3"]
    assert gone_ids == ["id:1"]
    assert same_ids == ["id:4"]
    assert changed_ids == ["id:2"]

    gone = delta["disappeared"][0]
    assert gone["not_a_bot_terminator_removal"] is True
    assert gone["state"] == "disappeared"
    assert "removal" not in gone["state"]
    assert gone["baseline_source_timestamp"] == "2026-04-01T00:00:00Z"
    assert gone["current_source_timestamp"] == "Not available"
    assert gone["record"]["source_timestamp"] == "2026-04-01T00:00:00Z"
    assert "removed_at" not in gone

    same = delta["unchanged"][0]
    assert same["record"]["source_timestamp"] == "2026-04-01T00:00:00Z"
    assert same["current_record"]["source_timestamp"] == "2026-05-01T00:00:00Z"
    assert same["baseline_source_timestamp"] == "2026-04-01T00:00:00Z"
    assert same["current_source_timestamp"] == "2026-05-01T00:00:00Z"

    changed = delta["changed"][0]
    assert "display_name" in changed["changed_fields"]
    assert changed["record"]["display_name"] == "Beta"
    assert changed["current_record"]["display_name"] == "Beta Two"
    assert changed["record"]["source_timestamp"] == "2026-04-01T00:00:00Z"
    assert changed["current_record"]["source_timestamp"] == "2026-05-01T00:00:00Z"

    # inputs were not rewritten
    assert baseline["records"][0]["source_timestamp"] == "2026-04-01T00:00:00Z"


def test_pipeline_handoff_does_not_classify():
    result = load_x_archive_followers(FIXTURES / "follower_and_sensitive.zip", ACCOUNT)
    seen = {}

    def pipeline(records):
        seen["count"] = len(records)
        return {"accepted": len(records)}

    out = hand_records_to_existing_pipeline(result["records"], pipeline)
    assert out == {"accepted": 2}
    assert seen["count"] == 2
    source = (ROOT / "src" / "x_archive_follower_adapter.py").read_text()
    assert "classify(" not in source
    # No per-user handle (from any user's own config) may be hard-coded in shared code.
    for cfg in (ROOT / "config").glob("dev_user_*.json"):
        h = (json.loads(cfg.read_text()).get("owner_x_handle") or "").lstrip("@")
        assert not h or h.lower() not in source.lower()
    assert "import classify" not in source


def test_account_handle_required():
    try:
        load_x_archive_followers(FIXTURES / "follower_and_sensitive.zip", "  ")
    except ValueError as exc:
        assert "account_handle" in str(exc)
    else:
        raise AssertionError("empty account_handle should fail")
