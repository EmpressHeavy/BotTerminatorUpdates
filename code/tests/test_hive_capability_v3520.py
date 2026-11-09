"""v3.5.20: owner-taught capability kind, alias, scrub, weekly dedupe across ISO weeks."""
import importlib.util
import io
import json
import os
import sys
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import feedback  # noqa: E402


def load_hive(db):
    os.environ["MEM_DB"] = str(db)
    spec = importlib.util.spec_from_file_location("hive_cap_v3520", ROOT / "hive/hive.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(m, *a):
    buf = io.StringIO()
    with redirect_stdout(buf):
        m.main(list(a))
    return buf.getvalue()


class Resp:
    status = 200

    def read(self):
        return b'{"ok":true}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_alias_is_capability_and_eligible_once(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("net")))
    hive = load_hive(tmp_path / "brain.db")
    try:
        out = run(hive, "feedback", "add", "self_upgrade", "storage",
                  "shipped build logs follower records in a sheet", "this copy logs them on the bot computer")
        assert out.strip() == "capability added"
        kind = hive.con().execute("SELECT kind FROM lesson").fetchone()[0]
        assert kind == "capability"
        run(hive, "on", "--bot", "bt")
        recs, drop = hive.build(hive.con())
        assert drop == 0 and len(recs) == 1 and recs[0]["k"] == "capability" and recs[0]["n"] == 1
        assert recs[0]["tv"] == feedback.TEMPLATE_VERSION == "v3.5.20"
    finally:
        os.environ.pop("MEM_DB", None)


def test_capability_scrub_drops_private_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("net")))
    hive = load_hive(tmp_path / "brain.db")
    try:
        run(hive, "feedback", "add", "capability", "checks",
            "shipped flow calls https://x.com/u/123456789012345 and @owner",
            "generalized method keeps the check local")
        run(hive, "feedback", "add", "capability", "files",
            "shipped reads /home/someone/secret/token.txt", "this copy reads its own local notes")
        run(hive, "feedback", "add", "capability", "keys",
            "api key sk-abcdefghijklmnopqrstuvwxyz", "generalized method stores nothing secret")
        run(hive, "feedback", "add", "capability", "ids",
            "account number 1234567890123456", "use the local label")
        run(hive, "feedback", "add", "capability", "quotes",
            'owner said "mail me at a@b.com about account 99887766"', "generalized method skips private quotes")
        long = "word " * 40
        run(hive, "feedback", "add", "capability", "length", long, long)
        run(hive, "on", "--bot", "bt")
        recs, drop = hive.build(hive.con())
        blob = json.dumps(recs)
        assert "@" not in blob and "http" not in blob and "/home/" not in blob
        assert "sk-" not in blob and "99887766" not in blob and "1234567890123456" not in blob
        assert "a@b.com" not in blob
        topics = {d["t"] for d in recs}
        assert topics == {"checks", "files", "length"}
        assert drop == 3
        for d in recs:
            assert d["k"] == "capability"
            assert all(1 <= len(d[f]) <= 150 for f in ("t", "w", "r"))
        length = next(d for d in recs if d["t"] == "length")
        assert len(length["w"]) == 150 and len(length["r"]) == 150
        routed = next(d for d in recs if d["t"] == "checks")
        assert "<URL>" in routed["w"] and "<HANDLE>" in routed["w"]
        assert "<PATH>" in next(d for d in recs if d["t"] == "files")["w"]
    finally:
        os.environ.pop("MEM_DB", None)


def test_capability_is_not_an_urgent_batch(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: (sent.append(json.loads(req.data)), Resp())[1])
    hive = load_hive(tmp_path / "brain.db")
    try:
        run(hive, "feedback", "add", "capability", "storage", "shipped build uses a sheet", "this copy logs locally")
        run(hive, "on", "--bot", "bt")
        monkeypatch.setattr(hive, "wk", lambda: "2026-W44")
        run(hive, "auto")
        assert len(sent) == 1 and "urgent" not in sent[0] and sent[0]["batch"][0]["k"] == "capability"
        run(hive, "feedback", "add", "capability", "routine", "shipped build has no noon check", "this copy runs a noon check")
        run(hive, "auto")
        assert len(sent) == 1  # same ISO week: not urgent, so the new capability waits
    finally:
        os.environ.pop("MEM_DB", None)


def test_correction_sent_one_iso_week_is_not_resent_the_next(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: (sent.append(json.loads(req.data)), Resp())[1])
    hive = load_hive(tmp_path / "brain.db")
    try:
        run(hive, "feedback", "add", "correction", "cards", "showed one big list", "owner wanted rounds of 5")
        run(hive, "on", "--bot", "bt")
        monkeypatch.setattr(hive, "wk", lambda: "2026-W44")
        run(hive, "auto")
        assert len(sent) == 1 and sent[0]["batch"][0]["k"] == "correction"
        h = sent[0]["batch"][0]["h"]
        c = hive.con()
        assert c.execute("SELECT 1 FROM hive_sent_h WHERE h=?", (h,)).fetchone()
        assert c.execute("SELECT shared, status FROM lesson WHERE topic='cards'").fetchone() == (1, "current")
        monkeypatch.setattr(hive, "wk", lambda: "2026-W45")
        run(hive, "feedback", "add", "correction", "scan", "stopped early", "owner wanted a full pass")
        run(hive, "auto")
        assert len(sent) == 2
        assert [d["t"] for d in sent[1]["batch"]] == ["scan"]
        assert h not in {d["h"] for d in sent[1]["batch"]}
        # even with the sent-hash table cleared, a fully-sent row stays out of the weekly pool
        c.execute("DELETE FROM hive_sent_h")
        recs, _ = hive.build(c)
        assert [d["t"] for d in recs] == []
    finally:
        os.environ.pop("MEM_DB", None)


def test_version_file_is_preferred_over_fallback(tmp_path, monkeypatch):
    hive = load_hive(tmp_path / "brain.db")
    try:
        p = tmp_path / "VERSION"
        p.write_text("v9.9.9\n")
        monkeypatch.setenv("BT_VERSION_FILE", str(p))
        assert hive.read_template_version() == "v9.9.9"
        monkeypatch.setenv("BT_VERSION_FILE", str(tmp_path / "missing"))
        assert hive.read_template_version() == "v3.5.20"
    finally:
        os.environ.pop("MEM_DB", None)
