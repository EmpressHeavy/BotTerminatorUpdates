"""v3.5.5: no Word/HTML review files; full-fidelity Sheet import; the standard records/ JSON mirror for GitHub."""
import csv
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import new_user, records, sheet_mirror as sm, storage as st  # noqa: E402
from test_records import FakeRunner, _gh_cfg, cfg  # noqa: E402

A, B = "demo_a", "demo_b"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md", "templates/records_schema.sql"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    for uk in (A, B):
        new_user.create_user(uk, "@" + uk, daily_cap=10, scan_time="09:00", root=tmp_path)
    return tmp_path


def _csv(rows):
    b = io.StringIO(); csv.writer(b, lineterminator="\n").writerows(rows); return b.getvalue()


QUEUE = [["SELECT ALL ELIGIBLE", "", "CLEAR ALL"], ["Selecting is NOT approval."],
         ["Select", "Review ID", "Account", "X user ID", "X Profile", "Classification", "Reason", "Notes", "Notes"],
         ["false", "BT-1-R01", "@spam_one", "1001", "https://x.com/spam_one", "Needs your look", "new, no posts", "a", "b"]]
GRAVE = [["Source tab", "Review ID", "Handle", "X user ID", "Removal / action time (PT)", "Snapshot ID / sha256"],
         ["TERMINATED HISTORY", "BT-1-R02", "@spam_two", "1002", "2026-10-20 10:00 PT", "snap_demo_20261020"],
         ["TERMINATED HISTORY", "BT-1-R03", "", "1003", "2026-10-20 10:01 PT", "snap_demo_20261020"]]
KEEP = [["Source tab", "Review ID", "X Profile / Handle", "X user ID", "Reason"],
        ["Kept", "BT-1-R04", "@friendly", "1004", "real"]]
KEEP_F = [KEEP[0], ["Kept", "BT-1-R04", '=HYPERLINK("https://x.com/friendly","@friendly")', "1004", "real"]]
WATCH = [["Handle", "X user ID", "Notes"]]


def _read(tabs):
    return {"ranges": [{"sheet": t, "range": f"'{t}'!A1:Z", "content": _csv(r)} for t, r in tabs.items()]}


DISP = _read({"REVIEW QUEUE": QUEUE, "GRAVEYARD": GRAVE, "KEEPERS": KEEP, "Re-follow Watch": WATCH})
FORM = _read({"REVIEW QUEUE": QUEUE, "GRAVEYARD": GRAVE, "KEEPERS": KEEP_F, "Re-follow Watch": WATCH})


def test_no_word_or_html_review_anywhere():
    for f in ("src/generate_review_docx.py", "src/render_review.py", "templates/review.html"):
        assert not (ROOT / f).exists(), f
    req = (ROOT / "requirements.txt").read_text().lower()
    assert "docx" not in req and "lxml" not in req
    for p in list((ROOT / "src").rglob("*.py")) + [ROOT / "README.md"]:
        t = p.read_text(encoding="utf-8").lower()
        assert ".docx" not in t and "python-docx" not in t and "review.html" not in t, p


def test_snapshot_writes_no_html(root):
    import build_snapshot as bs
    assert not hasattr(bs, "render_review")
    assert "render_review" not in (ROOT / "src/build_snapshot.py").read_text()


def test_import_every_tab_full_fidelity_and_idempotent(root):
    res = sm.import_sheet(A, DISP, FORM, root=root)
    assert {t: v["sheet_rows"] for t, v in res.items()} == {"REVIEW QUEUE": 1, "GRAVEYARD": 2, "KEEPERS": 1, "Re-follow Watch": 0}
    assert all(v["match"] for v in res.values()) and res["REVIEW QUEUE"]["header_row"] == 3
    again = sm.import_sheet(A, DISP, FORM, root=root)
    assert sum(v["added"] for v in again.values()) == 0
    assert sm.tab_counts(A, root) == {"REVIEW QUEUE": 1, "GRAVEYARD": 2, "KEEPERS": 1}
    assert sm.tab_counts(B, root) == {}


def test_mirror_files_columns_links_and_xrefs(root, tmp_path):
    sm.import_sheet(A, DISP, FORM, tab_order=["REVIEW QUEUE", "GRAVEYARD", "KEEPERS", "Re-follow Watch"], root=root)
    records.record_scan(A, "snap_demo_20261020", 2, root=root, sync=False)
    idx = sm.export_mirror(A, tmp_path / "out", root)
    base = tmp_path / "out" / "records"
    assert idx["format"] == sm.FORMAT and (base / "README.md").exists()
    q = json.loads((base / "sheet/01_review_queue.json").read_text())
    assert q["columns"] == QUEUE[2] and q["column_keys"][-1] == "Notes (2)" and q["preamble"] == QUEUE[:2]
    row = q["rows"][0]
    assert row["row"] == 4 and row["values"]["Reason"] == "new, no posts"
    assert row["refs"]["x_user_id"] == "1001" and row["refs"]["x_url"] == "https://x.com/spam_one"
    k = json.loads((base / "sheet/03_keepers.json").read_text())["rows"][0]
    assert k["formulas"]["X Profile / Handle"].startswith("=HYPERLINK") and "https://x.com/friendly" in k["refs"]["links"]
    acc = json.loads((base / "xref/accounts.json").read_text())
    assert {r["file"] for r in acc["1002"]} >= {"sheet/02_graveyard.json"}
    snaps = json.loads((base / "xref/snapshots.json").read_text())
    assert len(snaps["snap_demo_20261020"]["sheet_rows"]) == 2 and "scan" in snaps["snap_demo_20261020"]
    assert "\n  " in (base / "index.json").read_text()  # pretty-printed
    assert sm.verify_mirror(A, tmp_path / "out", root)["ok"]


def test_rebuild_sheet_and_restore_db_from_mirror(root, tmp_path):
    sm.import_sheet(A, DISP, FORM, root=root)
    records.record_removal(A, "spam_two", "1002", at="2026-10-20T10:00:00-07:00", root=root, sync=False)
    sm.export_mirror(A, tmp_path / "out", root)
    grid = sm.sheet_values_from_mirror(tmp_path / "out")
    assert grid["KEEPERS"][1][2].startswith("=HYPERLINK") and grid["REVIEW QUEUE"][:3] == QUEUE[:3]
    assert grid["GRAVEYARD"] == GRAVE
    res = sm.restore_from_mirror(B, tmp_path / "out", root)
    assert res["tab_counts"] == sm.tab_counts(A, root)
    assert records.counts(B, root)["removals"] == records.counts(A, root)["removals"] == 1


def test_migration_copies_every_tab(root):
    out = records.migrate_from_sheets(A, cfg(root), DISP, sheet_formulas=FORM, root=root)
    assert {t: v["stored"] for t, v in out["tabs"].items()}["GRAVEYARD"] == 2
    assert out["counts"]["sheet_rows"] == 4 and out["counts"]["sheet_tabs"] == 4


def test_github_backup_pushes_standard_mirror(root):
    sm.import_sheet(A, DISP, FORM, root=root)
    r = FakeRunner(push_codes=(0,))
    assert records.after_write(A, root, _gh_cfg(root), runner=r)["ok"]
    work = st.user_data_root(A, root) / "records" / "backup_repo"
    assert (work / "records/index.json").exists() and (work / "records/dump.sql").exists()
    assert not list(work.glob("*.csv"))  # old flat CSV layout replaced by records/
    assert (work / "records/sheet/01_review_queue.json").exists()


def test_github_restore_reads_mirror(root, tmp_path, monkeypatch):
    sm.import_sheet(A, DISP, FORM, root=root)
    sm.export_mirror(A, tmp_path / "src", root)
    import shutil, types

    def runner(cmd, cwd=None, **kw):
        if cmd[:3] == ["gh", "repo", "clone"]:
            shutil.copytree(tmp_path / "src", cmd[4])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    res = records.restore_from_github(B, "demo/my-bot-terminator-backup", root, runner=runner)
    assert res["ok"] and res["tab_counts"] == {"REVIEW QUEUE": 1, "GRAVEYARD": 2, "KEEPERS": 1}


def test_sheet_tables_append_only(root):
    import sqlite3
    sm.import_sheet(A, DISP, FORM, root=root)
    c = sqlite3.connect(records.db_path(A, root))
    for sql in ("UPDATE sheet_rows SET cells='[]'", "DELETE FROM sheet_rows", "DELETE FROM sheet_tabs"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)


def test_links_message_shows_age_last_post_and_signals():
    import card_text as ct
    a = {"handle": "spam_one", "post_count": 0, "followers": 1, "following": 900, "label_short": "new, no posts",
         "created_at": "2026-10-01T00:00:00Z", "signals": ["new account", "possible impersonation"]}
    m = ct.links_message("Likely bots:", [(1, a)])
    assert "https://x.com/spam_one" in m and "joined 2026-10-01" in m and "last post Not available" in m
    assert "possible impersonation" in m and "0 posts · 1 followers · 900 following" in m
    assert "joined" not in ct.links_message("t", [(1, {"handle": "x"})])  # unchanged when nothing extra is known


def test_legacy_import_accepts_one_multi_tab_read(root):
    """v3.5.6: found on the live migration; a single read_range of every tab must feed the Keepers/Graveyard import."""
    multi = _read({"GRAVEYARD": [["Source tab", "Handle", "X user ID", "Removal method / action", "Removal / action time (PT)"],
                                 ["TERMINATED HISTORY", "@spam_two", "1002", "REMOVE_FOLLOWER via native", "2026-10-20 10:00 PT"]],
                   "KEEPERS": KEEP,
                   "List Graveyard": [["When (with time zone)", "Action", "List name", "List ID", "Owner handle", "Owner ID", "Verified result"],
                                      ["2026-10-22T19:30:02-07:00", "LIST_SOFT_BLOCKED", "Demo list", "55", "@listowner", "", "verified"]]})
    out = records.migrate_from_sheets(A, cfg(root), multi, sheet_formulas=multi, root=root)
    c = out["counts"]
    assert c["removed"] == 1 and c["allowlist_now"] == 1 and c["lists_left"] == 1 and c["sheet_rows"] == 3
