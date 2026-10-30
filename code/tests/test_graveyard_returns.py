"""Graveyard-return block flow: detection, separation from removals, authorization, safeguards (all test-only adapter)."""
import datetime as dt, hashlib, io, json, sys
from preflight_helpers import confirmed
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
import storage as st
import build_snapshot as bs
import run_classify_pipeline as rp
import build_candidate_cards as bcc
import record_chat_selection as rcs
import removal_runner as rr
import graveyard_returns as gr
from removal_test_adapter import DryTestAdapter

UK = "demo_user"
DEMO = json.loads((ROOT / "tests/fixtures/demo_followers.json").read_text())["records"]
TZ = dt.timezone(dt.timedelta(hours=-7))
CARD1 = {"demo_01", "demo_02", "demo_03", "demo_04", "demo_11"}


def _scan(root, d, records, sid, monkeypatch):
    (d / "scan_raw/batch_000.json").write_text(json.dumps(records))
    monkeypatch.setattr(bs, "_snapshot_id", lambda: sid)
    return Path(rp.run_pipeline(root, user_key=UK, write_checkpoint=False)["snapshot_dir"]).name


def _now():
    return dt.datetime.now(TZ)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Scan 1 -> remove card 1 (5 accounts into the graveyard) -> scan 2 where they follow again (demo_01 renamed)."""
    old = rcs.ROOT; rcs.ROOT = tmp_path
    d = st.user_data_root(UK, tmp_path); (d / "scan_raw").mkdir(parents=True)
    cfg = {"user_key": UK, "runtime": "grokbot", "connections": confirmed(), "owner_x_handle": "@demo_owner", "data_root_relative": f"data/users/{UK}", "time_zone": "America/Los_Angeles",
           "protected_handles": [],
           # card-mechanics harness: pin legacy inactivity (sample-only) so card contents stay fixed
           "inactivity": {"use_profile_fields_without_sample": False}}
    (d / "config.json").write_text(json.dumps(cfg))
    s1 = _scan(tmp_path, d, DEMO, "snap_readonly_20261016_100000", monkeypatch)
    cards1 = bcc.build_cards_for_snapshot(UK, s1, tmp_path)
    b = rcs.build(s1, 1, cards1["cards"]["1"], "Select all", user_key=UK)
    rcs.append_history(b["history_entry"], user_key=UK)
    rem = rr.run_removals(UK, s1, DryTestAdapter(), root=tmp_path, sleep=lambda s: None, out=io.StringIO())
    assert rem["removed"] == 5
    again = [dict(r, username="demo_01_renamed") if r["username"] == "demo_01" else r for r in DEMO]
    again += [dict(DEMO[0], username=f"demo_{n}", name=f"Demo Account {n}", user_id=f"20000000{n}") for n in (13, 14)]
    s2 = _scan(tmp_path, d, again, "snap_readonly_20261016_110000", monkeypatch)
    yield {"root": tmp_path, "s1": s1, "s2": s2, "dir": d, "cfg": cfg, "b1": b}
    rcs.ROOT = old


def set_cfg(env, **kw):
    env["cfg"].update(kw); (env["dir"] / "config.json").write_text(json.dumps(env["cfg"]))


def blocks(env, adapter, sleeps=None, now=None):
    return gr.run_blocks(UK, env["s2"], adapter, root=env["root"], now_fn=lambda: now or _now(),
                         sleep=(sleeps.append if sleeps is not None else (lambda s: None)), out=io.StringIO())


def authorize(env, handles):
    rets = {r["handle"]: r for r in gr.load_returns(UK, env["s2"], env["root"])}
    return gr.record_block_authorization(UK, env["s2"], [rets[h] for h in handles], root=env["root"], raw_answer="yes")


def hist(env):
    return [json.loads(l) for l in st.history_path(env["root"], user_key=UK).read_text().splitlines()]


def test_detects_returns_by_user_id_including_renamed_handle(env):
    rets = gr.load_returns(UK, env["s2"], env["root"])
    assert {r["handle"] for r in rets} == (CARD1 - {"demo_01"}) | {"demo_01_renamed"}
    assert all(r["match"] == "user_id" and r["flag"] == gr.FLAG for r in rets)
    cands = json.loads((st.snapshot_dir(env["s2"], env["root"], user_key=UK) / "candidates.json").read_text())
    assert sum(1 for c in cands if c.get("flag") == gr.FLAG) == 5
    csv_ = (st.reports_path(env["root"], user_key=UK) / f"graveyard_returns_{env['s2']}.csv").read_text().splitlines()
    assert csv_[0].startswith("n,handle,x_user_id") and len(csv_) == 6
    events = [g for g in gr.load_graveyard(UK, env["root"]) if g.get("event") == "RETURN_DETECTED"]
    assert len(events) == 5
    gr.detect_returns(UK, env["s2"], env["root"])  # re-detect: logged once per snapshot, append-only
    assert len([g for g in gr.load_graveyard(UK, env["root"]) if g.get("event") == "RETURN_DETECTED"]) == 5


def test_match_rules_id_first_handle_only_as_fallback():
    gy = [{"handle": "old", "x_user_id": "2000000099"}, {"handle": "noid", "x_user_id": None}]
    assert gr.match_graveyard({"username": "new", "user_id": "2000000099"}, gy)[1] == "user_id"
    assert gr.match_graveyard({"username": "old", "user_id": "2000000777"}, gy) is None  # reused handle, other ID
    assert gr.match_graveyard({"username": "noid", "user_id": "2000000555"}, gy)[1] == "handle (ID missing)"
    assert gr.match_graveyard({"username": "stranger", "user_id": "2000000556"}, gy) is None


def test_returnees_excluded_from_removal_cards_and_runs(env):
    cards2 = bcc.build_cards_for_snapshot(UK, env["s2"], env["root"])
    numbered = {a["handle"] for a in cards2["accounts"]}
    assert not numbered & (CARD1 | {"demo_01_renamed"})
    # even an old-style selection naming returnees cannot remove them in the new snapshot
    old = dict(env["b1"]["history_entry"]); old["snapshot_id"] = env["s2"]
    rcs.append_history({**old, "entry_id": "TH-9001", "prev_entry_sha256": rcs._prev_hash(rcs.history_path(UK))[0]},
                       user_key=UK)
    a = DryTestAdapter()
    assert rr.run_removals(UK, env["s2"], a, root=env["root"], sleep=lambda s: None, out=io.StringIO())["removed"] == 0
    assert not a.calls
    assert gr.returns_card(gr.load_returns(UK, env["s2"], env["root"]))["action"] == "BLOCK"


def test_refuses_block_without_authorization(env):
    a = DryTestAdapter()
    with pytest.raises(rr.RefusedError, match="no recorded authorization"):
        blocks(env, a)
    assert not a.calls
    with pytest.raises(ValueError, match="not a Graveyard return"):
        gr.record_block_authorization(UK, env["s2"], [{"handle": "demo_05", "x_user_id": "2000000005"}],
                                      root=env["root"])
    assert gr.main(["block", "--user", UK, "--snapshot", env["s2"], "--adapter",
                    "removal_test_adapter:DryTestAdapter", "--root", str(env["root"])]) == 2


def test_authorized_block_uses_block_never_remove_with_pacing_and_logging(env):
    authorize(env, ["demo_01_renamed", "demo_02", "demo_03"])
    a, sleeps = DryTestAdapter(), []
    s = blocks(env, a, sleeps)
    assert s["blocked"] == 3 and sleeps == [10.0, 10.0]
    assert {c[0] for c in a.calls} == {"lookup", "block"}          # never remove/unfollow/mute/dm/post
    assert [c[1] for c in a.calls if c[0] == "block"] == ["demo_01_renamed", "demo_02", "demo_03"]
    h = hist(env)
    assert [e["status"] for e in h].count("BLOCKED") == 3
    lines = st.history_path(env["root"], user_key=UK).read_bytes().splitlines()
    assert all(json.loads(lines[i])["prev_entry_sha256"] == hashlib.sha256(lines[i - 1]).hexdigest()
               for i in range(1, len(lines)))
    gy = gr.load_graveyard(UK, env["root"])
    assert [g["event"] for g in gy].count("BLOCKED") == 3 and [g["event"] for g in gy].count("REMOVED") == 5
    assert blocks(env, DryTestAdapter())["blocked"] == 0             # not blocked twice


def test_auto_block_setting_authorizes_default_does_not(env):
    defaults = json.loads((ROOT / "config/default_user_config.json").read_text())
    assert defaults["graveyard_return_action"] == "review"
    set_cfg(env, graveyard_return_action="auto_block")
    assert blocks(env, DryTestAdapter())["blocked"] == 5


def test_protection_recheck_stops_block(env):
    authorize(env, sorted((CARD1 - {"demo_01"}) | {"demo_01_renamed"}))
    set_cfg(env, protected_handles=["demo_04"])
    st.save_always_keep([{"user_id": "2000000003"}], env["root"], user_key=UK)
    a = DryTestAdapter(fresh={"demo_01_renamed": {"i_follow": True}, "demo_02": {"verified_type": "business"},
                              "demo_11": {"verified_type": None}})
    s = blocks(env, a)
    assert s["blocked"] == 0 and s["skipped_protected"] == 5
    assert not [c for c in a.calls if c[0] != "lookup"]


@pytest.mark.parametrize("status,reason", [("warning", "warning"), ("rate_limited", "rate limit")])
def test_block_warning_stops_and_locks_day_for_removals_too(env, status, reason):
    authorize(env, ["demo_02", "demo_03", "demo_04"])
    a = DryTestAdapter(results=[rr.RemovalResult("ok"), rr.RemovalResult(status, "slow down")])
    s = blocks(env, a)
    assert s["blocked"] == 1 and s["stopped_reason"] == reason and len([c for c in a.calls if c[0] == "block"]) == 2
    with pytest.raises(rr.RefusedError, match="paused for today"):
        blocks(env, DryTestAdapter())
    with pytest.raises(rr.RefusedError, match="paused for today"):
        rr.run_removals(UK, env["s2"], DryTestAdapter(), root=env["root"], out=io.StringIO())


def test_shared_daily_cap_counts_removals_and_blocks(env):
    set_cfg(env, daily_removal_cap=7)        # 5 removals already today
    authorize(env, ["demo_02", "demo_03", "demo_04"])
    s = blocks(env, DryTestAdapter())
    assert s["blocked"] == 2 and s["stopped_reason"] == "daily cap" and s["actions_today"] == 7
    with pytest.raises(rr.RefusedError, match="daily cap"):
        blocks(env, DryTestAdapter())


def test_stale_snapshot_refused_for_blocks(env):
    authorize(env, ["demo_02"])
    with pytest.raises(rr.RefusedError, match="older than 7"):
        blocks(env, DryTestAdapter(), now=_now() + dt.timedelta(days=8))


def test_regression_normal_removals_unchanged_in_new_snapshot(env):
    cards2 = bcc.build_cards_for_snapshot(UK, env["s2"], env["root"])
    b = rcs.build(env["s2"], 1, cards2["cards"]["1"], "Select all", user_key=UK)
    rcs.append_history(b["history_entry"], user_key=UK)
    a, sleeps = DryTestAdapter(), []
    s = rr.run_removals(UK, env["s2"], a, root=env["root"], sleep=sleeps.append, out=io.StringIO())
    n = len(b["history_entry"]["selected"])
    assert n > 0 and s["removed"] == n and sleeps == [10.0] * (n - 1)
    assert {c[0] for c in a.calls} == {"lookup", "remove"}
    assert {x.lstrip("@") for x in s["removed_handles"]} == {"demo_13", "demo_14"}
