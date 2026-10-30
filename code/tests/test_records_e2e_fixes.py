"""v3.5.4: fixes found by the 2026-10-25 end-to-end test against a real alpha-era account (synthetic data here)."""
import json
import sqlite3

import pytest

from src import records, preflight

UK = "e2euser"
LEGACY = {"user_key": UK, "x_handle": "@SomeOwner", "owner_x_handle": "@SomeOwner"}


def _db(tmp_path):
    return sqlite3.connect(records.db_path(UK, tmp_path))


def test_legacy_config_without_sheet_id_is_detected_via_search():
    assert records.needs_migration(LEGACY) is False  # nothing saved in the config
    q = records.legacy_sheet_search(LEGACY)
    assert q["name"] == "Bot Terminator Review - @SomeOwner"
    assert records.needs_migration(LEGACY, found_sheet_id="SHEETX") is True
    assert records.needs_migration({**LEGACY, "review_sheet_id": "S"}) is True
    assert records.legacy_sheet_search({**LEGACY, "review_sheet_id": "S"}) is None
    done = {**LEGACY, "records": {"backup": {"method": "pending"}}}
    assert records.needs_migration(done, found_sheet_id="SHEETX") is False


def test_rows_parse_csv_content_and_first_header_wins():
    rows = records._rows({"content": "Review ID,X user ID,Kept date (PT),,Review ID,X user ID\nR1,11,2026-10-01,,MIRROR,99\n,,,,,\n"})
    assert rows == [{"review id": "R1", "x user id": "11", "kept date (pt)": "2026-10-01"}]


def test_alpha_tabs_import_idempotent(tmp_path):
    vals = {
        "GRAVEYARD": {"content": "Source tab,Handle,X user ID,Removal / action time (PT),Removal method / action,Batch ID,Result\n"
                                 "REVIEW QUEUE,,101,2026-10-06 22:30 PT,REMOVE_FOLLOWER via X web,B1,SUCCESS\n"
                                 "REVIEW QUEUE,@blk,102,2026-10-07 10:00 PT,BLOCK via X web,B1,SUCCESS\n"},
        "KEEPERS": {"content": "Source tab,X Profile / Handle,X user ID,Kept date (PT),Review ID,X user ID\n"
                               "REVIEW QUEUE,@friend,201,2026-10-08,MIRROR,999\n"},
        "PROTECTED": {"content": "Source tab,X Profile / Handle,X user ID\nREVIEW QUEUE,@prot,301\n"},
    }
    cfg = {**LEGACY}
    out = records.migrate_from_sheets(UK, cfg, vals, None, root=tmp_path, found_sheet_id="SHEETX")
    assert out["config"]["records"]["backup"]["method"] == "pending"
    assert out["config"]["records"]["legacy_sheet_id"] == "SHEETX"
    assert preflight.needs_google(out["config"]) is False
    c = _db(tmp_path)
    acts = sorted(r[0] for r in c.execute("SELECT action FROM removals"))
    assert acts == ["blocked", "removed"]
    assert sorted(r[0] for r in c.execute("SELECT user_id FROM current_allowlist")) == ["201", "301"]
    n = c.execute("SELECT count(*) FROM allowlist").fetchone()[0]
    records.import_legacy(UK, tmp_path, sheet_values=vals)  # re-import: nothing duplicated
    assert c.execute("SELECT count(*) FROM allowlist").fetchone()[0] == n
    assert c.execute("SELECT count(*) FROM removals").fetchone()[0] == 2
    assert c.execute("SELECT count(*) FROM audit_log WHERE event='migrated_from_sheets'").fetchone()[0] == 1


def test_graveyard_tab_note_and_history_overlap(tmp_path):
    old = tmp_path / "old"; (old / "history").mkdir(parents=True)
    (old / "history" / "history.jsonl").write_text(json.dumps(
        {"status": "TERMINATED", "handle": "@gone", "x_user_id": "7", "terminated_at_iso": "2026-10-01T10:00:00-07:00"}) + "\n")
    records.import_legacy(UK, tmp_path, old_root=old)
    vals = {"GRAVEYARD": {"content": "Handle,X user ID,Removal / action time (PT),Removal method / action\n"
                                     ",7,Removed on Oct 1,AUTOMATIC_MODE_NATIVE_REMOVE (not a block)\n"
                                     ",8,Removed on Oct 1,AUTOMATIC_MODE_NATIVE_REMOVE (soft block not used)\n"}}
    records.import_legacy(UK, tmp_path, sheet_values=vals)
    r = sorted(_db(tmp_path).execute("SELECT user_id,action FROM removals").fetchall())
    assert r == [("7", "removed"), ("8", "removed")]


def test_terminated_history_imports(tmp_path):
    old = tmp_path / "old"; (old / "history").mkdir(parents=True)
    (old / "history" / "history.jsonl").write_text(json.dumps(
        {"status": "TERMINATED", "handle": "@gone", "x_user_id": "7", "terminated_at_iso": "2026-10-06T22:30:00-07:00",
         "batch_id": "B1", "removal_status": "SUCCESS"}) + "\n" + json.dumps({"status": "SESSION_START"}) + "\n")
    records.import_legacy(UK, tmp_path, old_root=old)
    r = _db(tmp_path).execute("SELECT user_id,handle,at,batch,result FROM removals").fetchall()
    assert r == [("7", "gone", "2026-10-06T22:30:00-07:00", "B1", "confirmed on X")]


def test_scan_records_candidates_metrics_audit_and_export(tmp_path):
    cands = [{"user_id": "1", "username": "a", "label": "REVIEW", "signals": ["x", "y"]},
             {"user_id": "2", "username": "b", "label": "BOT-LIKE / REMOVE CANDIDATE", "signals": []}]
    records.record_scan(UK, "snap1", 2, followers=cands, root=tmp_path)
    records.record_scan(UK, "snap1", 2, followers=cands, root=tmp_path)  # idempotent
    records.record_scan_metrics(UK, "snap1", {"total_examined": 2, "REVIEW": 1, "nested": {"no": 1}}, root=tmp_path)
    c = _db(tmp_path)
    assert c.execute("SELECT count(*) FROM candidates WHERE scan_id='snap1'").fetchone()[0] == 2
    assert c.execute("SELECT handle,reasons FROM followers WHERE user_id='1'").fetchone() == ("a", "x; y")
    assert dict(c.execute("SELECT metric,value FROM scan_metrics")) == {"total_examined": "2", "REVIEW": "1"}
    assert c.execute("SELECT count(*) FROM audit_log WHERE event='scan_recorded'").fetchone()[0] >= 1
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM candidates"); c.commit()
    c.rollback()
    z = records.export_zip(UK, tmp_path / "x.zip", root=tmp_path)
    import zipfile
    assert {"candidates.csv", "scan_metrics.csv", "audit_log.csv"} <= set(zipfile.ZipFile(z).namelist())
    records.restore_from_file(UK, z, root=tmp_path)
    assert c.execute("SELECT count(*) FROM candidates").fetchone()[0] == 2


def test_allowlist_sync_matches_by_identity_no_churn(tmp_path):
    vals = {"PROTECTED": {"content": "X Profile / Handle,X user ID\n@friend,201\n@SomeKeeper,(look up before use)\n"}}
    records.import_legacy(UK, tmp_path, sheet_values=vals)
    c = _db(tmp_path)
    assert c.execute("SELECT user_id FROM allowlist WHERE handle='SomeKeeper'").fetchone() == ("",)
    records.sync_allowlist(UK, [{"user_id": "201", "username": "Friend"}, {"username": "somekeeper"}], root=tmp_path)
    assert c.execute("SELECT count(*) FROM allowlist WHERE op='remove'").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM allowlist").fetchone()[0] == 2
