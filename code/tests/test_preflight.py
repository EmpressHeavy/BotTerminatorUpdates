"""Grok Bot lockdown: Sheets + Drive rechecked EACH session; runtime locked to grokbot (owner 2026-10-16)."""
import datetime as dt, io, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import preflight, removal_runner as rr, graveyard_returns as gr, storage as st, sheet_connector as sc
import automatic_policy as ap
import run_classify_pipeline as rcp
from preflight_helpers import confirmed
from test_graveyard_returns import env, UK, set_cfg  # noqa: F401
from test_removal_runner import DryTestAdapter

ROOT = Path(__file__).resolve().parents[1]
SE = {preflight.STANDALONE_ENV: "1"}


def _drop(conn):
    c = confirmed(); c.pop(conn); return {"connections": c}


def test_refuses_without_sheets_drive_or_both():
    r = preflight.check(UK, cfg=_drop("google_sheets"), env={})
    assert not r["ok"] and r["missing"] == ["google_sheets"] and "Connect Google Sheets" in r["message"]
    r = preflight.check(UK, cfg=_drop("google_drive"), env={})
    assert r["missing"] == ["google_drive"] and "Connect Google Drive" in r["message"]
    c = confirmed(); c.pop("google_sheets"); c.pop("google_drive")
    r = preflight.check(UK, cfg={"connections": c}, env={})
    assert r["missing"] == ["google_sheets", "google_drive"]
    with pytest.raises(preflight.PreflightError): preflight.require(UK, cfg={"connections": c}, env={})


def test_passes_with_both_this_session():
    assert preflight.check(UK, cfg={"connections": confirmed()}, env={})["ok"]


def test_default_config_is_grokbot_locked_and_privacy_clean():
    d = json.loads((ROOT / "config/default_user_config.json").read_text())
    assert d["runtime"] == "grokbot" and d["sheets"]["backend"] == "connector" and "connections" not in d
    assert not preflight.check(UK, cfg=d, env=SE)["ok"]          # no session yet: refused even with the env flag
    assert not preflight.check(UK, cfg={}, env={})["ok"]          # missing runtime = grokbot (fail closed)


def test_grokbot_refuses_google_api_and_csv_backends():
    for b in ("google_api", "csv"):
        cfg = {"runtime": "grokbot", "sheets": {"backend": b}, "connections": confirmed()}
        r = preflight.check(UK, cfg=cfg, env=SE)
        assert not r["ok"] and "isn't allowed in Grok Bot" in r["message"]
        assert sc.select_backend(cfg, env=SE)["backend"] == "refused"
        # standalone runtime without the env flag is still Grok Bot mode
        assert not preflight.check(UK, cfg=dict(cfg, runtime="standalone"), env={})["ok"]


def test_refuses_runtime_and_backend_switch_via_helpers(tmp_path):
    d = st.user_data_root(UK, tmp_path); d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"user_key": UK, "runtime": "grokbot"}))
    with pytest.raises(preflight.PreflightError, match="stays in Grok Bot mode"):
        preflight.set_runtime(UK, "standalone", tmp_path, env=SE)
    for b in ("google_api", "csv"):
        with pytest.raises(preflight.PreflightError):
            preflight.set_sheets_backend(UK, b, tmp_path, env=SE)
    preflight.set_sheets_backend(UK, "connector", tmp_path, env={})
    assert json.loads((d / "config.json").read_text())["runtime"] == "grokbot"
    with pytest.raises(ValueError):                                # the mode switch only knows automatic/manual
        ap.ModeStore(tmp_path).switch(UK, "standalone", by="user")


def test_session_recheck_required_each_session(tmp_path):
    d = st.user_data_root(UK, tmp_path); d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"user_key": UK, "runtime": "grokbot"}))
    assert "haven't been checked this session" in preflight.check(UK, tmp_path, env={})["message"]
    with pytest.raises(preflight.PreflightError): preflight.record_confirmation(UK, "google_drive", tmp_path)
    preflight.start_session(UK, tmp_path, session_id="s1")
    preflight.record_confirmation(UK, "google_drive", tmp_path)
    preflight.record_confirmation(UK, "google_sheets", tmp_path)
    r = preflight.check(UK, tmp_path, env={})
    assert not r["ok"] and r["missing"] == ["bot_terminator_book"]   # rules doc read first
    preflight.record_book_read(UK, tmp_path, document_id="doc1")
    assert preflight.check(UK, tmp_path, env={})["ok"]
    preflight.start_session(UK, tmp_path, session_id="s2")          # new session: old confirmations don't count
    r = preflight.check(UK, tmp_path, env={})
    assert not r["ok"] and r["missing"] == ["google_sheets", "google_drive"]
    preflight.record_confirmation(UK, "google_sheets", tmp_path)
    preflight.record_confirmation(UK, "google_drive", tmp_path)
    assert not preflight.check(UK, tmp_path, env={})["ok"]           # book read again in the new session
    preflight.record_book_read(UK, tmp_path)
    assert preflight.check(UK, tmp_path, env={})["ok"]
    c = confirmed("s1"); c["session"]["id"] = "s9"                  # confirmations from another session id
    assert not preflight.check(UK, cfg={"connections": c}, env={})["ok"]


def test_stale_confirmation_refused():
    c = confirmed()
    old = (dt.datetime.now().astimezone() - dt.timedelta(hours=preflight.SESSION_MAX_HOURS + 1)).isoformat()
    c["session"]["started_at"] = old
    r = preflight.check(UK, cfg={"connections": c}, env={})
    assert not r["ok"] and r.get("stale") and "recheck" in r["message"]


def test_failure_mid_session_stops_runners_until_fresh_check(env):
    preflight.record_failure(UK, "google_drive", "HTTP 401", env["root"])
    for call in (lambda: rr.run_removals(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO()),
                 lambda: gr.run_blocks(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO()),
                 lambda: rcp.run_pipeline(env["root"], user_key=UK)):
        with pytest.raises(preflight.PreflightError, match="Google Drive connection failed"):
            call()
    preflight.record_confirmation(UK, "google_drive", env["root"])  # fresh successful check unlocks
    assert preflight.check(UK, env["root"], env={})["ok"]
    with pytest.raises(rr.RefusedError, match="authorized selection"):   # past preflight, runner's own checks
        rr.run_removals(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())


def test_runners_and_pipeline_refuse_without_confirmations(env):
    c = confirmed(); c.pop("google_drive")
    set_cfg(env, connections=c)
    for call in (lambda: rr.run_removals(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO()),
                 lambda: gr.run_blocks(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO()),
                 lambda: rcp.run_pipeline(env["root"], user_key=UK)):
        with pytest.raises(preflight.PreflightError, match="Google Drive"):
            call()


def test_standalone_path_still_works(env, monkeypatch):
    monkeypatch.setenv(preflight.STANDALONE_ENV, "1")
    set_cfg(env, runtime="standalone", connections={}, sheets={"backend": "csv"})
    assert preflight.check(UK, env["root"])["ok"]
    with pytest.raises(rr.RefusedError, match="authorized selection"):   # not a PreflightError
        rr.run_removals(UK, env["s2"], DryTestAdapter(), root=env["root"], sleep=lambda s: None, out=io.StringIO())
    preflight.set_runtime(UK, "standalone", env["root"])               # standalone config may keep its runtime


def test_book_read_goes_stale():
    c = confirmed()
    c["book_read"]["read_at"] = (dt.datetime.now().astimezone()
                                 - dt.timedelta(minutes=preflight.BOOK_READ_MAX_MINUTES + 1)).isoformat()
    r = preflight.check(UK, cfg={"connections": c}, env={})
    assert not r["ok"] and "Bot Terminator Book" in r["message"]
