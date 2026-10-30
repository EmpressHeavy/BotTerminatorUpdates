"""v3.3.0: per-user SQLite memory. Empty per-user brain.db, mem commands, short transactions, no secrets,
strict isolation, optional private-repo backup (off by default, no tokens)."""
import json
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import storage as st, new_user, rules_book, memory as mem
import build_monthly_settings_card as mc

A, B = "demo_a", "demo_b"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "templates").mkdir()
    for f in ("config/default_user_config.json", "templates/bot_terminator_book.md", "templates/memory_schema.sql"):
        (tmp_path / f).write_text((ROOT / f).read_text())
    for uk in (A, B):
        new_user.create_user(uk, "@" + uk, daily_cap=10, scan_time="09:00", root=tmp_path)
    return tmp_path


def cfg(root, uk=A):
    return json.loads((st.user_data_root(uk, root) / "config.json").read_text())


def rows(root, uk, sql):
    return mem.q(uk, sql, root=root)[1]


def test_setup_creates_empty_private_db(root):
    p = mem.db_path(A, root)
    assert p == root / "data/users/demo_a/memory/brain.db" and p.exists()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600 and stat.S_IMODE(p.parent.stat().st_mode) == 0o755
    for t in mem.TABLES:
        assert rows(root, A, f"SELECT count(*) FROM {t}") == [(0,)], t
    assert rows(root, A, "SELECT count(*) FROM notes_fts") == [(0,)]
    assert rows(root, A, "SELECT name FROM sqlite_master WHERE name='fact_cur'") == [("fact_cur",)]


def test_config_defaults_backup_off(root):
    c = cfg(root)
    assert c["memory"]["enabled"] is True and c["memory"]["backup"] == {"enabled": False, "repo": None, "last_backup_at": None}
    d = json.loads((ROOT / "config/default_user_config.json").read_text())
    assert d["memory"]["backup"]["enabled"] is False
    assert mem.backup_plan(A, c, root)["steps"] == []


def test_setup_questions_and_plans(root):
    assert mem.SETUP_QUESTION in new_user.SETUP_QUESTIONS and "default: no" in mem.SETUP_QUESTION
    assert new_user.SETUP_QUESTIONS.index(mem.SETUP_QUESTION) == len(new_user.SETUP_QUESTIONS) - 2
    plans = new_user.setup_plans(cfg(root), root)
    assert plans["memory"]["session_start"] == "mem boot" and plans["memory"]["backup"]["enabled"] is False


def test_add_fact_log_find_boot(root):
    rid = mem.add(A, "rule", {"scope": "bot-terminator", "category": "safety", "text": "Never remove mutuals"}, root=root)
    assert rid == 1
    assert mem.fact(A, "settings", "daily_cap", "10", root=root)["closed"] == 0
    assert mem.fact(A, "settings", "daily_cap", "10", root=root)["unchanged"]
    r = mem.fact(A, "settings", "daily_cap", "20", root=root)
    assert r["closed"] == 1
    cur = rows(root, A, "SELECT value FROM fact WHERE predicate='daily_cap' AND valid_to IS NULL")
    assert cur == [("20",)] and len(rows(root, A, "SELECT id FROM fact")) == 2
    mem.log(A, "scan", "scanned 50: 10 likely bots", root=root)
    assert any(src == "event_log" for src, _, _ in mem.find(A, "likely bots", root=root))
    b = mem.boot(A, root=root)
    assert "Never remove mutuals" in b and "settings.daily_cap=20" in b and "scanned 50" in b and "Never store secrets" in b


def test_q_is_read_only(root):
    with pytest.raises(ValueError):
        mem.q(A, "DELETE FROM rule", root=root)
    with pytest.raises(sqlite3.Error):
        mem.q(A, "WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE rule", root=root)
    c = mem.connect(A, root, readonly=True)
    with pytest.raises(sqlite3.Error):
        c.execute("INSERT INTO entity(type,name) VALUES('a','b')")
    c.close()


def test_short_transactions_each_write_commits(root):
    mem.record_scan(A, scanned=50, bots=10, review=2, safe=38, follower_count=1234, root=root)
    # a separate connection sees it right away: committed per event, no batching
    c = sqlite3.connect(mem.db_path(A, root))
    assert c.execute("SELECT kind FROM event_log").fetchall() == [("scan",)]
    c.close()
    mem.record_removal(A, "spam_acct", reason="no posts", root=root)
    mem.record_list_action(A, "Crypto Spam", "left", result="verified", root=root)
    mem.record_project_status(A, "First cleanup", "in progress", root=root)
    mem.record_project_status(A, "First cleanup", "done", root=root)
    mem.record_rule_change(A, "Daily cap changed to 15", setting="daily_cap", value=15, root=root)
    mem.record_rule_change(A, "Keep all accounts with a podcast in bio", root=root)
    kinds = [k for (k,) in rows(root, A, "SELECT kind FROM event_log ORDER BY id")]
    assert kinds == ["scan", "removal", "list_action", "project_status", "project_status", "setting_change", "rule_change"]
    assert rows(root, A, "SELECT status FROM project") == [("done",)]


def test_failed_write_rolls_back(root):
    with pytest.raises(ValueError):
        mem.add(A, "rule", {"nope": "x"}, root=root)
    assert rows(root, A, "SELECT count(*) FROM rule") == [(0,)]


@pytest.mark.parametrize("bad", [
    "password: hunter22", "my api_key=abc123", "gh" + "p_" + "a" * 36, "github" + "_pat_" + "b" * 30, "s" + "k-" + "c" * 24,
    "Bear" + "er " + "d" * 30, "auth_token=" + "e" * 40, "4111 1111 1111 1111", "https://user:pw@github.com/x/y.git",
    "-----BEG" + "IN RSA PRIVATE KEY-----", "AKIA" + "A" * 16,
])
def test_secrets_are_refused(root, bad):
    with pytest.raises(mem.SecretRejected):
        mem.log(A, "note", bad, root=root)
    with pytest.raises(mem.SecretRejected):
        mem.fact(A, "settings", "x", bad, root=root)
    assert rows(root, A, "SELECT count(*) FROM event_log") == [(0,)]


def test_harmless_numbers_allowed(root):
    mem.log(A, "scan", "followers 1234567 at 2026-10-23 09:00, removed 10", root=root)


def test_isolation_between_users(root):
    mem.log(A, "note", "only for A", root=root)
    assert rows(root, B, "SELECT count(*) FROM event_log") == [(0,)]
    assert mem.find(B, "only", root=root) == []
    assert mem.db_path(A, root) != mem.db_path(B, root)
    with pytest.raises(ValueError):
        mem.db_path("../demo_a", root)
    with pytest.raises(ValueError):
        mem.db_path(None, root)


def test_backup_optional_private_only_no_tokens(root, tmp_path):
    with pytest.raises(ValueError):
        mem.initial_section(True, None)
    for bad in ("https://tok@github.com/a/b", "a/b:c", "git@github.com:a/b.git", "gh" + "p_" + "a" * 36 + "/x"):
        with pytest.raises(ValueError):
            mem.validate_repo(bad)
    assert mem.validate_repo("https://github.com/someone/my-memory.git") == "someone/my-memory"
    ch = mem.set_backup(cfg(root), True, "someone/my-memory")
    assert ch["memory"]["backup"]["enabled"] and "ON" in ch["book_change"]
    c = cfg(root); c["memory"] = ch["memory"]
    plan = mem.backup_plan(A, c, root)
    flat = json.dumps(plan)
    assert ["gh", "repo", "create", "someone/my-memory", "--private"] in [s.get("cmd") for s in plan["steps"]]
    assert any(s.get("must_equal") == "PRIVATE" for s in plan["steps"])
    assert "https://github.com/someone/my-memory.git" in flat and "@github.com" not in flat
    mem.check_no_secret(flat)
    assert "Memory backup: ON" in mem.status_line(c)
    with pytest.raises(ValueError):
        mem.check_backup_target("PUBLIC", "https://github.com/someone/my-memory.git")
    with pytest.raises(ValueError):
        mem.check_backup_target("PRIVATE", "https://x:y@github.com/someone/my-memory.git")
    mem.check_backup_target("PRIVATE", "https://github.com/someone/my-memory.git")
    assert mem.set_backup(c, False)["memory"]["backup"]["enabled"] is False


def test_export_jsonl_and_refuses_secret_rows(root, tmp_path):
    mem.log(A, "scan", "scanned 5", root=root)
    files = mem.export(A, tmp_path / "out", root=root)
    assert (tmp_path / "out/schema.sql").exists() and len(files) == len(mem.TABLES) + 1
    assert json.loads((tmp_path / "out/event_log.jsonl").read_text().splitlines()[0])["summary"] == "scanned 5"
    c = sqlite3.connect(mem.db_path(A, root)); c.execute("INSERT INTO event_log(kind,summary) VALUES('x','password: abcdef')"); c.commit(); c.close()
    with pytest.raises(mem.SecretRejected):
        mem.export(A, tmp_path / "out2", root=root)


def test_monthly_card_and_book(root):
    lines = mc.build(None, cfg=cfg(root))["extra_companion_lines"]
    assert any(x.startswith("Memory backup: OFF (default)") for x in lines)
    book = rules_book.render(cfg(root), root)
    assert "Backup to a private GitHub repo you own: off" in book and "mem boot" in book


def test_cli(root):
    def run(*a):
        return subprocess.run([sys.executable, "-m", "src.memory", "--user", A, "--root", str(root), *a],
                              cwd=ROOT, capture_output=True, text=True)
    assert run("log", "scan", "scanned", "7").stdout.strip() == "log#1"
    assert run("fact", "settings", "mode", "automatic").stdout.startswith("fact#")
    assert "mode" in run("q", "SELECT predicate FROM fact").stdout
    assert "event_log" in run("find", "scanned").stdout
    assert "SAFETY:" in run("boot").stdout
    r = run("log", "note", "password:", "x1")
    assert r.returncode == 2 and "secret" in r.stderr
    assert run("add", "rule", "text=Be kind").stdout.strip() == "rule#1"


# ---------- v3.4.0: memory habits + private check before every push ----------
class FakeRunner:
    """Records commands; `vis` is what `gh repo view` reports each time it's asked."""
    def __init__(self, vis):
        self.vis, self.calls = list(vis), []

    def __call__(self, cmd, cwd=None, capture_output=True, text=True):
        self.calls.append(cmd)
        out, code = "", 0
        if cmd[:3] == ["gh", "repo", "view"]:
            out = self.vis.pop(0) if self.vis else "PUBLIC"
        elif cmd[:3] == ["git", "remote", "get-url"]:
            out = "https://github.com/someone/my-memory.git"
        return subprocess.CompletedProcess(cmd, code, out, "")


def _on(root):
    c = cfg(root); c["memory"] = mem.set_backup(c, True, "someone/my-memory")["memory"]
    return c


def test_backup_rechecks_private_before_every_push(root):
    c = _on(root)
    r = FakeRunner(["PRIVATE", "PRIVATE"])
    assert mem.push_backup(A, c, root, runner=r)["pushed"]
    mem.log(A, "scan", "again", root=root)
    assert mem.push_backup(A, c, root, runner=r)["pushed"]
    views = [i for i, x in enumerate(r.calls) if x[:3] == ["gh", "repo", "view"]]
    pushes = [i for i, x in enumerate(r.calls) if x[:2] == ["git", "push"]]
    assert len(views) == len(pushes) == 2
    assert views[0] < pushes[0] < views[1] < pushes[1]   # a fresh visibility check right before each push


@pytest.mark.parametrize("vis", ["PUBLIC", "INTERNAL", ""])
def test_backup_refuses_push_unless_private(root, vis):
    r = FakeRunner(["PRIVATE", vis])
    c = _on(root)
    assert mem.push_backup(A, c, root, runner=r)["pushed"]
    res = mem.push_backup(A, c, root, runner=r)   # repo flipped since the last push
    assert res["pushed"] is False and "refused" in res["reason"].lower()
    assert sum(1 for x in r.calls if x[:2] == ["git", "push"]) == 1


def test_backup_off_never_runs_anything(root):
    r = FakeRunner([])
    assert mem.push_backup(A, cfg(root), root, runner=r)["pushed"] is False and r.calls == []


def test_plan_push_goes_through_checked_backup(root):
    plan = mem.backup_plan(A, _on(root), root)
    flat = json.dumps(plan)
    assert "git push" not in flat and ["python3", "-m", "src.memory", "--user", A, "backup"] in [s.get("cmd") for s in plan["steps"]]


def test_lessons_supersede_history_nothing_deleted(root):
    rid = mem.add(A, "rule", {"text": "Scan at 9am", "category": "schedule"}, root=root)
    l1 = mem.lesson(A, "lists", "removed list without verifying", "verify after each removal", root=root)
    assert l1["new"] and mem.lesson(A, "lists", "removed list without verifying", "verify after each removal", root=root)["new"] is False
    assert rows(root, A, "SELECT uses FROM lesson")[0][0] == 2
    assert mem.lessons(A, "lists", root=root)[0][3] == "verify after each removal"
    s = mem.supersede(A, "rule", rid, "Scan at 10am", why="owner moved scan time", root=root)
    assert rows(root, A, f"SELECT status,superseded_by FROM rule WHERE id={rid}") == [("superseded", s["new_id"])]
    with pytest.raises(ValueError):
        mem.supersede(A, "rule", rid, "dup", why="x", root=root)
    h = mem.history(A, "rule", s["new_id"], root=root)
    assert [x["text"] for x in h] == ["Scan at 9am", "Scan at 10am"] and h[0]["old"] and not h[1]["old"]
    assert rows(root, A, "SELECT count(*) FROM rule")[0][0] == 2      # nothing deleted
    hits = mem.find(A, "Scan", root=root)
    assert any(s_.startswith("[OLD]") for _, _, s_ in hits) and any(not s_.startswith("[OLD]") for _, _, s_ in hits)
    b = mem.boot(A, root, bot="Bot Terminator")
    assert "BOT: Bot Terminator" in b and "LESSONS:" in b and "Scan at 10am" in b
    rules_line = next(x for x in b.splitlines() if x.startswith("RULES:"))
    assert "Scan at 10am" in rules_line and "Scan at 9am" not in rules_line
    src = (ROOT / "src/memory.py").read_text().upper()
    assert "DELETE FROM" not in src and "DROP TABLE" not in src


def test_upgrade_v330_db_in_place(root):
    p = mem.db_path(A, root)
    c = sqlite3.connect(p)
    for t in ("lesson",):
        c.execute(f"DROP TABLE IF EXISTS {t}")
    c.commit(); c.close()
    mem.log(A, "scan", "after upgrade", root=root)
    assert rows(root, A, "SELECT count(*) FROM lesson")[0][0] == 0
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(rule)")}
    assert {"status", "reason", "changed_on"} <= cols


def test_hive_mind_client_queries_work_on_this_db(root):
    """The Hive Mind client reads fact(subject,value) and lesson(topic,wrong,right,uses,src,status,last)."""
    mem.fact(A, "owner", "name", "Demo", root=root)
    mem.lesson(A, "t", "w", "r", root=root)
    c = sqlite3.connect(mem.db_path(A, root))
    assert c.execute("SELECT subject,value FROM fact WHERE valid_to IS NULL").fetchall()
    assert c.execute("SELECT id,topic,wrong,right,uses FROM lesson WHERE status!='avoid' AND src!='hive' ORDER BY last").fetchall()


def test_cli_habits(root):
    def run(*a):
        return subprocess.run([sys.executable, "-m", "src.memory", "--user", A, "--root", str(root), *a],
                              cwd=ROOT, capture_output=True, text=True)
    assert "BOT: Bot Terminator" in run("boot", "Bot Terminator").stdout
    assert run("add", "rule", "text=Old way").stdout.strip() == "rule#1"
    assert "superseded" in run("supersede", "rule", "1", "New way", "--why", "better").stdout
    assert "[OLD]" in run("history", "rule", "2").stdout
    assert run("lesson", "x", "bad", "good").stdout.startswith("lesson#")
    assert "good" in run("lessons", "x").stdout
