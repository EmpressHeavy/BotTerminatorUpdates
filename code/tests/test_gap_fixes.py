"""Fresh-install gap fixes (2026-10-16): empty scan, archive import, review sheet rows/CSV/API,
card answer file, Always Keep persistence, demo data. Made-up data only."""
import csv, json, subprocess, sys
from preflight_helpers import confirmed
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import storage as st
import run_classify_pipeline as rp
import import_x_archive as ixa
import populate_review_sheet as prs
import review_sheet_writer as rsw
import build_candidate_cards as bcc
import record_chat_selection as rcs

ARCH = ROOT / "tests/fixtures/synthetic_x_archive"
DEMO = json.loads((ROOT / "tests/fixtures/demo_followers.json").read_text())["records"]
UK = "demo_user"


def _user(root: Path, uk: str = UK):
    d = st.user_data_root(uk, root); d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps({"user_key": uk, "runtime": "grokbot", "connections": confirmed(), "owner_x_handle": "@demo_owner",
                                               "data_root_relative": f"data/users/{uk}"}))
    return d


def _scan(root: Path):
    d = _user(root) / "scan_raw"; d.mkdir(exist_ok=True)
    (d / "batch_000.json").write_text(json.dumps(DEMO))
    return rp.run_pipeline(root, user_key=UK, write_checkpoint=False)


@pytest.fixture
def rcs_root(tmp_path):
    old = rcs.ROOT; rcs.ROOT = tmp_path
    yield tmp_path
    rcs.ROOT = old


# 2. empty scan
def test_empty_scan_raises_and_saves_nothing(tmp_path):
    _user(tmp_path)
    with pytest.raises(rp.EmptyScanError):
        rp.run_pipeline(tmp_path, user_key=UK)
    assert not (st.user_data_root(UK, tmp_path) / "snapshots").exists()
    assert not (st.user_data_root(UK, tmp_path) / "last_scan_report.json").exists()


def test_empty_scan_cli_exit_code(tmp_path, capsys):
    _user(tmp_path)
    assert rp.main(["--user", UK, "--root", str(tmp_path)]) == 2
    assert "No follower records" in capsys.readouterr().err


# 3. archive import CLI
def test_import_archive_writes_scan_raw(tmp_path):
    _user(tmp_path)
    assert ixa.main(["--user", UK, "--root", str(tmp_path), str(ARCH / "follower_and_sensitive.zip")]) == 0
    out = st.user_data_root(UK, tmp_path) / "scan_raw" / "batch_000.json"
    recs = json.loads(out.read_text())
    assert len(recs) == 2 and {"username", "user_id", "name"} <= set(recs[0])
    # second import goes to the next batch number; then the scan runs on it
    assert ixa.main(["--user", UK, "--root", str(tmp_path), str(ARCH / "follower_and_sensitive.zip")]) == 0
    assert (out.parent / "batch_001.json").exists()
    r = rp.run_pipeline(tmp_path, user_key=UK, write_checkpoint=False)
    assert len(json.loads((Path(r["snapshot_dir"]) / "candidates.json").read_text())) == 4


def test_import_archive_without_follower_file(tmp_path):
    _user(tmp_path)
    assert ixa.main(["--user", UK, "--root", str(tmp_path), str(ARCH / "no_follower_file.zip")]) == 1
    assert not (st.user_data_root(UK, tmp_path) / "scan_raw").exists()


def test_import_module_cli_runs():
    p = subprocess.run([sys.executable, "-m", "src.import_x_archive", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0 and "--user" in p.stdout


# 4. review sheet
def test_build_rows_on_normal_scan_and_csv(tmp_path):
    r = _scan(tmp_path)
    rows = prs.build_rows(r["snapshot_dir"], "DEMO-A", "2026-10-16", 4)
    handles = [row[4] for row in rows]
    assert len(rows) >= 4
    assert not any("demo_09" in h or "demo_10" in h for h in handles)  # followed / verified never queued
    out = rsw.write_rows_csv(rows, tmp_path / "queue.csv")
    data = list(csv.reader(out.open(encoding="utf-8")))
    assert data[0] == rsw.REVIEW_QUEUE_HEADER and len(data) == len(rows) + 1


def test_label_short_derived_for_old_snapshots():
    assert prs.classification({"label": "BOT-LIKE / REMOVE CANDIDATE"}) == "BOT-LIKE"
    assert prs.route({"label": "REVIEW", "verified_type": "none"}) == "In review"
    assert prs.route({"label": "REVIEW", "verified": True}) == "PROTECTED"


def test_sheet_api_mocked():
    svc = mock.MagicMock()
    svc.spreadsheets().create().execute.return_value = {"spreadsheetId": "SHEET_FAKE"}
    sid = rsw.create_or_open_sheet(service=svc)
    assert sid == "SHEET_FAKE"
    res = rsw.write_rows_to_sheet([["", "BT-X-001"]], spreadsheet_id=sid, service=svc)
    kw = svc.spreadsheets().values().append.call_args.kwargs
    assert kw["valueInputOption"] == "USER_ENTERED" and kw["insertDataOption"] == "INSERT_ROWS"
    assert kw["range"] == "'In review'!A3:R" and kw["body"]["values"][0] == rsw.REVIEW_QUEUE_HEADER
    assert res["rows_written"] == 1


def test_sheet_api_requires_user_credentials(monkeypatch):
    monkeypatch.delenv(rsw.CREDENTIALS_ENV, raising=False)
    monkeypatch.delenv(rsw.OAUTH_CLIENT_ENV, raising=False)
    with pytest.raises(RuntimeError, match=rsw.CREDENTIALS_ENV):
        rsw.create_or_open_sheet()


# 5. card answer file, end to end
def test_cards_write_chat_numbering_and_record_selection(rcs_root):
    r = _scan(rcs_root)
    sid = Path(r["snapshot_dir"]).name
    res = bcc.build_cards_for_snapshot(UK, sid, rcs_root, batch_id="DEMO-A")
    m = json.loads((Path(r["snapshot_dir"]) / "chat_numbering.json").read_text())
    assert [a["chat_no"] for a in m["accounts"]] == [a["chat_no"] for a in res["accounts"]]
    assert {"chat_no", "card", "handle", "user_id", "review_id", "tab", "sheet_row"} <= set(m["accounts"][0])
    assert not {"demo_09", "demo_10"} & {a["handle"] for a in m["accounts"]}
    nums = res["cards"]["1"]
    b = rcs.build(sid, 1, nums, "1, 2", user_key=UK)
    assert b["selected"] == [1, 2] and b["history_entry"]["owner_x_handle"] == "@demo_owner"
    rcs.append_history(b["history_entry"], user_key=UK)
    assert st.history_path(rcs_root, user_key=UK).read_text().count("\n") == 1


# 6. Always Keep persistence
def test_final_review_always_keep_saved_with_backup(rcs_root):
    r = _scan(rcs_root)
    sid = Path(r["snapshot_dir"]).name
    res = bcc.build_cards_for_snapshot(UK, sid, rcs_root)
    nums = res["cards"]["1"]
    fr = rcs.build_final_review(sid, nums[:2], "Always Keep 1; rest leave", user_key=UK)
    out = rcs.commit_final_review(fr, user_key=UK)
    keep = st.load_always_keep(rcs_root, user_key=UK)
    assert len(keep) == 1 and keep[0]["user_id"] == res["accounts"][0]["user_id"] and keep[0]["key"] == "user_id"
    assert out["always_keep"]["backup"] and Path(out["always_keep"]["backup"]).exists()
    # repeat is de-duplicated
    assert rcs.save_always_keep_additions(fr["always_keep_add"], user_key=UK)["added"] == []
    # handle fallback when no numeric id
    rcs.save_always_keep_additions([{"handle": "demo_noid", "x_user_id": "Not available"}], user_key=UK)
    assert st.load_always_keep(rcs_root, user_key=UK)[-1]["key"] == "handle"
    # next scan respects it: the kept account is no longer a card candidate
    res2 = bcc.build_cards_for_snapshot(UK, sid, rcs_root)
    assert res["accounts"][0]["handle"] not in {a["handle"] for a in res2["accounts"]}


# 8. demo data
def test_demo_data_bot_like_and_protections(tmp_path):
    r = _scan(tmp_path)
    c = {x["username"]: x for x in json.loads((Path(r["snapshot_dir"]) / "candidates.json").read_text())}
    assert sum(x["label"].startswith("BOT-LIKE") for x in c.values()) >= 3
    assert all(u.startswith("demo_") for u in c)
    cards = bcc.build_cards([dict(x, handle=x["username"]) for x in c.values()])
    picked = {a["handle"] for a in cards["accounts"]}
    assert "demo_09" not in picked and "demo_10" not in picked  # followed, verified
    assert {"demo_01", "demo_02", "demo_03"} <= picked


# 1. setup helper
def test_new_user_helper(tmp_path):
    import shutil, stat, new_user
    (tmp_path / "config").mkdir(); shutil.copy(ROOT / "config/default_user_config.json", tmp_path / "config")
    p = new_user.create_user("newuser_test", "newuser_example", daily_cap=10, scan_time="09:00", lists_enabled=False, root=tmp_path)
    cfg = json.loads(p.read_text())
    assert cfg["owner_x_handle"] == "@newuser_example" and cfg["data_root_relative"] == "data/users/newuser_test"
    assert cfg["operating_mode"] == "automatic"
    assert (p.parent / "scan_raw").is_dir() and stat.S_IMODE((p.parent / "scan_raw").stat().st_mode) == 0o755
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o755 and stat.S_IMODE(p.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        new_user.create_user("newuser_test", "x", daily_cap=10, scan_time="09:00", lists_enabled=False, root=tmp_path)
    with pytest.raises(ValueError):
        new_user.create_user("other", "", daily_cap=10, scan_time="09:00", lists_enabled=False, root=tmp_path)


# 7. checksum names only the file
def test_build_script_checksum_has_bare_filename(tmp_path):
    out = tmp_path / "bt.tgz"
    p = subprocess.run(["bash", str(ROOT / "tools/build_package.sh"), str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    line = (tmp_path / "bt.tgz.sha256").read_text().split()
    assert line[1] == "bt.tgz" and "/" not in line[1]
    assert subprocess.run(["sha256sum", "-c", "bt.tgz.sha256"], cwd=tmp_path, capture_output=True).returncode == 0


# Permissions (owner decision 2026-10-16 6:52 PM PT)
def test_permission_modes(rcs_root):
    import stat
    r = _scan(rcs_root)
    sid = Path(r["snapshot_dir"]).name
    res = bcc.build_cards_for_snapshot(UK, sid, rcs_root)
    b = rcs.build(sid, 1, res["cards"]["1"], "1", user_key=UK); rcs.append_history(b["history_entry"], user_key=UK)
    fr = rcs.build_final_review(sid, res["cards"]["1"][1:2], "Always Keep 2", user_key=UK)
    rcs.commit_final_review(fr, user_key=UK)
    st.append_journal("note", rcs_root, user_key=UK)
    rows = prs.build_rows(r["snapshot_dir"], "D", "2026-10-16", 4)
    rsw.write_rows_csv(rows, st.reports_path(rcs_root, user_key=UK) / "queue.csv")
    base = st.user_data_root(UK, rcs_root)
    mode = lambda p: stat.S_IMODE(p.stat().st_mode)
    for d in [base] + [p for p in base.rglob("*") if p.is_dir()]:
        assert mode(d) == 0o755, d
    assert mode(base / "journal.md") == 0o644
    assert not (Path(r["snapshot_dir"]) / "review.html").exists()  # v3.5.5: no HTML review file
    assert mode(st.reports_path(rcs_root, user_key=UK) / "queue.csv") == 0o644
    for f in ["config.json", "always_keep.json", "history/history.jsonl", "last_scan_report.json",
              "scan_raw/batch_000.json"]:
        assert mode(base / f) == 0o600, f
    for f in ["candidates.json", "meta.json", "selections.json", "review_index.json", "metrics.json", "chat_numbering.json"]:
        assert mode(Path(r["snapshot_dir"]) / f) == 0o600, f
    assert all(mode(p) == 0o600 for p in (base / "backups/always_keep").iterdir())
