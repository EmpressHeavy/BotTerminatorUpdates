"""Removal runner rules (2026-10-16). Uses only made-up demo accounts and the TEST-ONLY adapter."""
import datetime as dt, hashlib, io, json, sys
from preflight_helpers import confirmed
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st
import run_classify_pipeline as rp
import build_candidate_cards as bcc
import record_chat_selection as rcs
import removal_runner as rr
from removal_test_adapter import DryTestAdapter

UK = "demo_user"
DEMO = json.loads((ROOT / "tests/fixtures/demo_followers.json").read_text())["records"]
TZ = dt.timezone(dt.timedelta(hours=-7))


@pytest.fixture
def env(tmp_path):
    old = rcs.ROOT; rcs.ROOT = tmp_path
    d = st.user_data_root(UK, tmp_path); (d / "scan_raw").mkdir(parents=True)
    cfg = {"user_key": UK, "runtime": "grokbot", "connections": confirmed(), "owner_x_handle": "@demo_owner", "data_root_relative": f"data/users/{UK}",
           "time_zone": "America/Los_Angeles", "protected_handles": [],
           "inactivity": {"use_profile_fields_without_sample": False}}  # pin legacy inactivity for card mechanics
    (d / "config.json").write_text(json.dumps(cfg))
    (d / "scan_raw/batch_000.json").write_text(json.dumps(DEMO))
    snap = Path(rp.run_pipeline(tmp_path, user_key=UK, write_checkpoint=False)["snapshot_dir"])
    res = bcc.build_cards_for_snapshot(UK, snap.name, tmp_path)
    yield {"root": tmp_path, "sid": snap.name, "cards": res, "dir": d, "cfg": cfg}
    rcs.ROOT = old


def select(env, card="1", raw="Select all"):
    b = rcs.build(env["sid"], int(card), env["cards"]["cards"][card], raw, user_key=UK)
    rcs.append_history(b["history_entry"], user_key=UK)
    return [a["handle"].lstrip("@") for a in b["history_entry"]["selected"]]


def set_cfg(env, **kw):
    env["cfg"].update(kw); (env["dir"] / "config.json").write_text(json.dumps(env["cfg"]))


def run(env, adapter, sleeps=None, now=None):
    now = now or dt.datetime.now(TZ)
    return rr.run_removals(UK, env["sid"], adapter, root=env["root"], now_fn=lambda: now,
                           sleep=(sleeps.append if sleeps is not None else (lambda s: None)), out=io.StringIO())


def hist(env):
    return [json.loads(l) for l in st.history_path(env["root"], user_key=UK).read_text().splitlines()]


def test_refuses_without_authorized_selection(env):
    with pytest.raises(rr.RefusedError, match="authorized selection"):
        run(env, DryTestAdapter())
    # a manual-mode (awaiting confirmation) selection is not authorization either
    b = rcs.build(env["sid"], 1, env["cards"]["cards"]["1"], "1", user_key=UK, mode="manual")
    rcs.append_history(b["history_entry"], user_key=UK)
    with pytest.raises(rr.RefusedError):
        run(env, DryTestAdapter())


def test_manual_confirmation_authorizes(env):
    b = rcs.build(env["sid"], 1, env["cards"]["cards"]["1"], "2", user_key=UK, mode="manual")
    rcs.append_history(b["history_entry"], user_key=UK)
    rr.record_manual_confirmation(UK, env["sid"], b["history_entry"]["selected"], root=env["root"], confirmed_text="yes")
    assert run(env, DryTestAdapter())["removed"] == 1


def test_pacing_constant_no_jitter_and_only_remove_calls(env):
    sel = select(env)
    a, sleeps = DryTestAdapter(), []
    s = run(env, a, sleeps)
    assert s["removed"] == len(sel) == 5
    assert sleeps == [rr.PACING_SECONDS] * 4 and rr.PACING_SECONDS == 10.0
    assert {c[0] for c in a.calls} == {"lookup", "remove"}  # __getattr__ would fail on block/unfollow/mute/dm/post
    gy = (env["dir"] / "graveyard.jsonl").read_text().splitlines()
    assert len(gy) == 5
    # rerun: already removed accounts are not removed again
    assert run(env, DryTestAdapter())["removed"] == 0


@pytest.mark.parametrize("status,reason", [("warning", "warning"), ("rate_limited", "rate limit")])
def test_stop_on_warning_or_rate_limit_locks_day(env, status, reason):
    select(env)
    a = DryTestAdapter(results=[rr.RemovalResult("ok"), rr.RemovalResult(status, "X said slow down")])
    s = run(env, a)
    assert s["removed"] == 1 and s["stopped_reason"] == reason
    assert [c for c in a.calls if c[0] == "remove"].__len__() == 2  # stopped immediately after the warning
    with pytest.raises(rr.RefusedError, match="paused for today"):
        run(env, DryTestAdapter())
    # next day: the old selection is void; only a NEW authorized selection resumes
    tomorrow = dt.datetime.now(TZ) + dt.timedelta(days=1)
    with pytest.raises(rr.RefusedError, match="authorized selection"):
        run(env, DryTestAdapter(), now=tomorrow)
    select(env)
    assert run(env, DryTestAdapter(), now=tomorrow)["removed"] == 4


def test_daily_cap_counts_prior_removals_and_never_above_100(env):
    # 2026-10-20: cap asked at setup; unset falls back to the suggested low start (10); never above 100
    assert rr.daily_cap({"daily_removal_cap": 500}) == 100 and rr.daily_cap({}) == 10
    set_cfg(env, daily_removal_cap=3)
    select(env)
    now = dt.datetime.now(TZ)
    s1 = run(env, DryTestAdapter(), now=now)
    assert s1["removed"] == 3 and s1["stopped_reason"] == "daily cap"
    with pytest.raises(rr.RefusedError, match="daily cap"):
        run(env, DryTestAdapter(), now=now)
    set_cfg(env, daily_removal_cap=4)
    assert run(env, DryTestAdapter(), now=now)["removed"] == 1  # 3 earlier today count toward the cap


def test_protection_recheck_fail_safe(env):
    sel = select(env)  # demo_01..demo_04 + demo_11 (card 1)
    set_cfg(env, protected_handles=["demo_04"])
    st.save_always_keep([{"user_id": "2000000003", "username": "old_name"}], env["root"], user_key=UK)
    fresh = {
        "demo_01": {"i_follow": True},                         # now followed
        "demo_02": {"verified_type": "blue"},                  # now verified
        "demo_03": {"handle": "renamed_03"},                   # renamed; Always Keep matches by ID
        "demo_11": {"i_follow": None},                         # unknown follow status -> protected
    }
    a = DryTestAdapter(fresh=fresh)
    s = run(env, a)
    reasons = {x["handle"].lstrip("@"): x["reason"] for x in s["skipped"]}
    assert s["removed"] == 0 and set(reasons) == set(sel)
    assert reasons["demo_01"] == "you follow this account" and reasons["demo_02"].startswith("verified")
    assert reasons["demo_03"] == "Always Keep" and reasons["demo_04"] == "owner-protected account"
    assert "unknown" in reasons["demo_11"]
    assert not [c for c in a.calls if c[0] == "remove"]


def test_missing_verified_treated_as_protected():
    from protections import execution_protection_reason as epr
    assert "unknown" in epr({"i_follow": False, "handle": "x"})
    assert epr({"i_follow": False, "verified": False, "handle": "x"}) is None


def test_stale_snapshot_refused(env):
    select(env)
    with pytest.raises(rr.RefusedError, match="older than 7"):
        run(env, DryTestAdapter(), now=dt.datetime.now(TZ) + dt.timedelta(days=8))
    set_cfg(env, max_snapshot_age_days=10)
    assert run(env, DryTestAdapter(), now=dt.datetime.now(TZ) + dt.timedelta(days=8))["removed"] == 5


def test_history_chain_intact_and_modes(env):
    select(env)
    run(env, DryTestAdapter(results=[rr.RemovalResult("ok"), rr.RemovalResult("ok"), rr.RemovalResult("error", "x")]))
    lines = st.history_path(env["root"], user_key=UK).read_bytes().splitlines()
    for i in range(1, len(lines)):
        assert json.loads(lines[i])["prev_entry_sha256"] == hashlib.sha256(lines[i - 1]).hexdigest()
    statuses = [json.loads(l)["status"] for l in lines]
    assert statuses.count("REMOVED") == 2 and statuses[-1] == "REMOVAL_STOPPED"
    assert json.loads(lines[-1])["locks_day"] is False  # plain error stops the session but doesn't lock the day


def test_cli_refuses_without_adapter_or_selection(env, capsys):
    assert rr.main(["--user", UK, "--snapshot", env["sid"], "--adapter", "removal_test_adapter:DryTestAdapter",
                    "--root", str(env["root"])]) == 2
    assert "authorized selection" in capsys.readouterr().err
