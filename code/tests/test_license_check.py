"""Subscription gate. Synthetic install ids only. No X profiles or Stripe network calls."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import license_check as lc
import removal_runner as rr

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
PRICE = {"label": "Bot Terminator", "amount_cents": 449, "currency": "usd", "interval": "month",
         "display": "4.49 USD/month"}


def write_cfg(root: Path, **over):
    cfg = {"product": "bt", "base_url": "https://license.example", "grace_hours": 72, "timeout_seconds": 5}
    cfg.update(over)
    (root / "config").mkdir(parents=True)
    (root / "config" / "license.json").write_text(json.dumps(cfg), encoding="utf-8")


def test_source_does_not_hardcode_prices():
    text = (ROOT / "src" / "license_check.py").read_text(encoding="utf-8")
    for needle in ("4.49", "8.99", "449", "899"):
        assert needle not in text


def test_inactive_refuses_and_keeps_the_renew_link(tmp_path):
    write_cfg(tmp_path)
    seen = {}

    def transport(url, payload):
        seen["url"] = url
        seen["payload"] = payload
        if url.endswith("/register"):
            return 201, json.dumps({"install_id": "a" * 32}).encode()
        return 200, json.dumps({
            "active": False, "product": "bt", "expires": None,
            "renew_url": "https://license.example/pay?install_id=" + "a" * 32,
            "price": PRICE,
        }).encode()

    with pytest.raises(lc.LicenseError, match="isn't active") as exc:
        lc.require("scan", root=tmp_path, now=NOW, transport=transport)
    assert "records are still here" in str(exc.value)
    assert "4.49 USD/month" in str(exc.value)
    assert "https://license.example/pay" in str(exc.value)
    assert seen["payload"] == {"install_id": "a" * 32, "product": "bt"}
    state = json.loads((tmp_path / "data" / "install_license.json").read_text(encoding="utf-8"))
    assert set(state) == {"install_id", "last_active_at", "last_renew_url", "last_price"}
    assert state["last_active_at"] is None
    assert "handle" not in json.dumps(state)


def test_active_check_then_offline_grace_then_lapse(tmp_path):
    write_cfg(tmp_path, grace_hours=72)

    def ok(url, payload):
        if url.endswith("/register"):
            return 201, b'{"install_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
        return 200, json.dumps({"active": True, "product": "bt", "expires": None,
                                "renew_url": "https://license.example/pay?install_id=x", "price": PRICE}).encode()

    assert lc.require("removal", root=tmp_path, now=NOW, transport=ok)["allow"] is True

    def down(url, payload):
        raise OSError("offline")

    assert lc.require("block", root=tmp_path, now=NOW + timedelta(hours=71), transport=down)["reason"] == "grace"
    with pytest.raises(lc.LicenseError, match="more than 72 hours"):
        lc.require("scan", root=tmp_path, now=NOW + timedelta(hours=73), transport=down)


def test_inactive_is_not_kept_alive_by_an_older_grace_window(tmp_path):
    write_cfg(tmp_path)
    calls = {"n": 0}

    def transport(url, payload):
        calls["n"] += 1
        if url.endswith("/register"):
            return 201, b'{"install_id":"cccccccccccccccccccccccccccccccc"}'
        if calls["n"] == 2:
            return 200, json.dumps({"active": True, "renew_url": "https://license.example/pay", "price": PRICE}).encode()
        return 200, json.dumps({"active": False, "renew_url": "https://license.example/pay", "price": PRICE}).encode()

    lc.require("scan", root=tmp_path, now=NOW, transport=transport)
    with pytest.raises(lc.LicenseError, match="isn't active"):
        lc.require("scan", root=tmp_path, now=NOW + timedelta(minutes=5), transport=transport)
    state = lc.load_state(tmp_path)
    assert state["last_active_at"] is None


def test_removal_runner_refuses_before_any_x_work(tmp_path):
    with pytest.raises(rr.RefusedError, match="records are still here"):
        rr.run_removals("demo_user", "snap", None, root=tmp_path)


def test_instructions_make_the_check_mandatory():
    skill = (REPO / "skills" / "bot-terminator-getting-started" / "SKILL.md").read_text(encoding="utf-8")
    rules = (REPO / "docs" / "bot-rules.md").read_text(encoding="utf-8")
    steps = (ROOT / "src" / "daily_routine.py").read_text(encoding="utf-8")
    assert "python3 -m src.license_check require scan" in skill
    assert "do not delete" in skill.lower()
    assert "22." in rules and "license_check" in rules
    assert "license_check require scan" in steps
