"""v3.5.0 records: per-user terminator.db, append-only, write-through hooks, backups, restore, upgrade import."""
import json
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import new_user, records, preflight, storage as st, graveyard_returns as gr  # noqa: E402

A, B = "demo_a", "demo_b"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md", "templates/records_schema.sql"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    for uk in (A, B):
        new_user.create_user(uk, "@" + uk, daily_cap=10, scan_time="09:00", root=tmp_path)
    return tmp_path


def cfg(root, uk=A):
    return json.loads((st.user_data_root(uk, root) / "config.json").read_text())


def test_new_user_gets_own_db_and_records_section(root):
    p = records.db_path(A, root)
    assert p.exists() and p.parent == st.user_data_root(A, root)
    assert (p.stat().st_mode & 0o777) == 0o600
    assert cfg(root)["records"]["backup"]["method"] == "pending"  # v3.5.2: not chosen yet, never "skip"
    assert records.db_path(B, root) != p


def test_setup_message_and_card():
    assert records.SETUP_MESSAGE.startswith("Keeping your records safe")
    card = records.setup_card()
    assert len(card["options"]) <= 6
    assert records.parse_setup_answer("GitHub backup (recommended)") == "github"
    assert records.parse_setup_answer("skip for now") == "remind"


def test_append_only_triggers(root):
    records.record_removal(A, "botty", "11", root=root, sync=False)
    records.sync_allowlist(A, [{"handle": "k", "x_user_id": "1"}], root=root, sync=False)
    records.record_scan(A, "s1", 1, root=root, sync=False)
    c = sqlite3.connect(records.db_path(A, root))
    for sql in ("UPDATE removals SET handle='x'", "DELETE FROM removals", "DELETE FROM graveyard",
                "UPDATE allowlist SET op='add'", "DELETE FROM scans"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.close()


def test_hooks_write_through_and_isolation(root):
    gr.append_graveyard(A, root, {"event": "REMOVED", "handle": "spam1", "x_user_id": "101", "at": "2026-10-25T10:00:00-07:00"})
    st.save_always_keep([{"handle": "friend", "x_user_id": "7"}], root, user_key=A)
    st.save_snapshot("s1", [{"handle": "x", "x_user_id": "9"}], {}, {}, root, user_key=A)
    c = records.counts(A, root)
    assert c["removed"] == 1 and c["graveyard"] == 1 and c["allowlist_now"] == 1 and c["scans"] == 1 and c["followers"] == 1
    assert records.counts(B, root)["removals"] == 0
    st.save_always_keep([], root, user_key=A)  # remove = a new row, never an edit
    c = records.counts(A, root)
    assert c["allowlist_now"] == 0 and c["allowlist"] == 2


def test_hook_failure_never_breaks_caller(root, monkeypatch):
    monkeypatch.setattr(records, "record_graveyard_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    gr.append_graveyard(A, root, {"event": "REMOVED", "handle": "z", "x_user_id": "5"})
    assert "records write failed" in records.pending(A, root)["needs_attention"]["error"]


def test_restore_after_wipe(root, tmp_path):
    records.record_removal(A, "b1", "1", root=root, sync=False); records.record_removal(A, "b2", "2", action="blocked", root=root, sync=False)
    z = records.export_zip(A, tmp_path / "out.zip", root)
    before = records.counts(A, root)
    records.db_path(A, root).unlink()
    records.init_db(A, root)
    assert records.counts(A, root)["removals"] == 0
    records.restore_from_file(A, z, root)
    assert records.counts(A, root) == before
    records.restore_from_file(A, z, root)  # idempotent
    assert records.counts(A, root) == before


class FakeRunner:
    def __init__(self, vis="PRIVATE", push_codes=(0,)):
        self.vis, self.push_codes, self.calls = vis, list(push_codes), []

    def __call__(self, cmd, cwd=None, **kw):
        self.calls.append(cmd)
        out, code = "", 0
        if cmd[:3] == ["gh", "repo", "view"]:
            out = self.vis
        elif cmd[:3] == ["git", "remote", "get-url"]:
            out = "https://github.com/demo/my-bot-terminator-backup.git"
        elif cmd[:2] == ["git", "push"]:
            code = self.push_codes.pop(0) if self.push_codes else 1
        return types.SimpleNamespace(returncode=code, stdout=out, stderr="boom" if code else "")


def _gh_cfg(root):
    c = cfg(root); c["records"] = records.set_backup(c, "github", repo="demo/my-bot-terminator-backup")["records"]
    return c


def test_github_push_rechecks_private_before_every_push(root):
    r = FakeRunner(push_codes=(1, 0))
    res = records.after_write(A, root, _gh_cfg(root), runner=r)
    assert res["ok"] is True
    idx = [i for i, c in enumerate(r.calls) if c[:2] in (["gh", "repo"], ["git", "push"])]
    kinds = [r.calls[i][0] for i in idx]
    assert kinds == ["gh", "git", "gh", "git"]  # visibility check precedes each push attempt


def test_public_repo_refused_and_owner_told(root):
    r = FakeRunner(vis="PUBLIC")
    res = records.after_write(A, root, _gh_cfg(root), runner=r)
    assert res["ok"] is False and res.get("refused")
    assert not any(c[:2] == ["git", "push"] for c in r.calls)
    assert "tell_owner" in records.pending(A, root)["needs_attention"]


def test_push_failure_retries_then_tells_owner(root):
    r = FakeRunner(push_codes=(1, 1))
    res = records.after_write(A, root, _gh_cfg(root), runner=r)
    assert res["ok"] is False and sum(c[:2] == ["git", "push"] for c in r.calls) == 2
    assert records.pending(A, root)["needs_attention"]["tell_owner"]


def test_cloud_and_download_methods(root):
    c = cfg(root); c["records"] = records.set_backup(c, "cloud_csv", service="Dropbox")["records"]
    records.record_removal(A, "q", "3", root=root, sync=False)
    res = records.after_write(A, root, c)
    assert res["upload"]["files"] and records.pending(A, root)["upload"]
    records.mark_uploaded(A, root)
    assert "upload" not in records.pending(A, root)
    c["records"] = records.set_backup(c, "download")["records"]
    records.after_write(A, root, c)
    rem = records.download_reminder(A, root)
    assert rem and Path(rem["file"]).exists() and records.download_reminder(A, root) is None


def test_preflight_google_only_for_sheets(root):
    c = cfg(root)
    assert preflight.needs_google(c) is False
    c["records"]["backup"]["method"] = "sheets"
    assert preflight.needs_google(c) is True
    legacy = dict(c); legacy.pop("records")
    assert preflight.needs_google(legacy) is True


def test_upgrade_card_paths():
    assert [o if isinstance(o, str) else o for o in records.upgrade_card()["options"]]
    assert records.handle_upgrade_answer("No")["action"] == "fresh_start"
    for a in ("Yes", "Not sure"):
        r = records.handle_upgrade_answer(a)
        assert r["action"] == "find_records" and any(s.get("message") == records.EXPORT_REQUEST for s in r["steps"])
    assert records.handle_upgrade_answer("hmm")["action"] == "ask_again"


def test_import_legacy_files_and_sheet(root, tmp_path):
    old = tmp_path / "old"; (old / "history").mkdir(parents=True); (old / "snapshots" / "s0").mkdir(parents=True)
    (old / "graveyard.jsonl").write_text(json.dumps({"event": "REMOVED", "handle": "g1", "x_user_id": "21", "at": "2026-01-01T00:00:00Z"}) + "\n")
    (old / "always_keep.json").write_text(json.dumps({"accounts": [{"handle": "pal", "x_user_id": "8"}]}))
    (old / "snapshots" / "s0" / "candidates.json").write_text("[1,2,3]")
    sheet = {"Actions": [["When", "Action", "Handle", "X user ID"], ["2026-02-01", "Removed", "@s2", "22"]],
             "List Graveyard": [["When (with time zone)", "Action", "List name", "List ID"], ["2026-02-02", "Left", "spam", "L1"]]}
    r = records.import_legacy(A, root, old_root=old, sheet_values=sheet)
    a = r["after"]
    assert a["removed"] == 2 and a["allowlist_now"] == 1 and a["scans"] == 1 and a["lists_left"] == 1
    assert "2 removed" in r["message"]
    again = records.import_legacy(A, root, old_root=old, sheet_values=sheet)
    assert again["after"] == a  # idempotent


# ---------- v3.5.1 ----------
def test_new_setup_never_offers_sheets():
    labels = records.setup_card()["options"]
    assert not any("sheet" in l.lower() for l in labels) and len(labels) == 3
    assert records.parse_setup_answer("google sheets") != "sheets"


def test_migration_card_and_move(root):
    c = cfg(root); c["sheets"] = {"spreadsheet_id": "demo-sheet"}; c["records"]["backup"]["method"] = "sheets"
    assert records.needs_migration(c) and records.needs_migration_offer(c)
    card = records.migration_card()
    assert card["options"] == ["Got it, move my records"] and "Keep Sheets" not in str(card)
    for w in ("bulky", "slow", "tokens", "never delete"):
        assert w in card["question"]
    r0 = records.handle_migration_answer(A, "Keep Sheets for now", root)
    assert r0["action"] == "migrate" and "old copy" in r0["message"]
    sheet = {"Actions": [["When", "Action", "Handle", "X user ID"], ["2026-02-01", "Removed", "@s2", "22"]]}
    r = records.migrate_from_sheets(A, c, sheet, root=root)  # copy first, no backup picked yet
    assert r["counts"]["removed"] == 1 and r["config"]["records"]["backup"]["method"] == "pending"
    assert r["next"]["card"]["options"] and "fallback_file" not in r["next"]  # v3.5.7: no unsolicited file
    assert r["config"]["sheets"]["spreadsheet_id"] == "demo-sheet"  # never deleted
    assert not records.needs_migration(r["config"])
    assert not preflight.needs_google(r["config"]) if hasattr(preflight, "needs_google") else True
    r2 = records.migrate_from_sheets(A, c, sheet, "download", root=root)  # re-run: no duplicates
    assert r2["counts"]["removed"] == 1 and r2["config"]["records"]["backup"]["method"] == "download"
    log = (st.user_data_root(A, root) / "records" / "migration_log.jsonl").read_text().splitlines()
    assert [json.loads(l)["event"] for l in log] == ["notified", "migrated", "migrated"]
    with pytest.raises(ValueError):
        records.migrate_from_sheets(A, c, sheet, "sheets", root=root)


# ---------- v3.5.2: backup can't be skipped ----------
def test_no_skip_anywhere():
    assert "skip" not in records.SETUP_MESSAGE.lower()
    assert records.setup_card()["options"] == ["GitHub backup (recommended)", "My cloud storage (CSV)", "Send me the file (CSV)"]
    with pytest.raises(ValueError):
        records.set_backup({}, "skip")


def test_skip_reply_reasks_without_a_file(root):
    r = records.handle_setup_answer(A, "skip for now", root)
    assert r["action"] == "remind" and "fallback_file" not in r and r["card"]["options"]
    assert records.handle_setup_answer(A, "GitHub backup (recommended)", root)["action"] == "set"


def test_pending_reminder_until_set(root):
    c = cfg(root)
    assert records.needs_backup_choice(c)
    rem = records.backup_reminder(A, root, c)
    assert rem and "reminder" in rem["message"].lower() and "fallback_file" not in rem
    records.after_write(A, root, c)
    assert not records.pending(A, root).get("download_due")  # v3.5.7: pending sends no file
    assert records.download_reminder(A, root) is None
    c["records"] = records.set_backup(c, "download")["records"]
    assert records.backup_reminder(A, root, c) is None


def test_migration_requires_real_method(root):
    c = cfg(root)
    for bad in ("skip", "pending", "sheets"):
        with pytest.raises(ValueError):
            records.migrate_from_sheets(A, c, {}, bad, root=root)
