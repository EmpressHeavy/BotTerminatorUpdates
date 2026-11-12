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


def test_register_and_check_send_an_explicit_user_agent(tmp_path, monkeypatch):
    """urllib's default User-Agent is blocked by Cloudflare error 1010 on the license Worker."""
    write_cfg(tmp_path)
    seen = []

    class _Body:
        def __init__(self, status, raw):
            self.status = status
            self._raw = raw

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        seen.append(req.get_header("User-agent"))
        if req.full_url.endswith("/register"):
            return _Body(201, json.dumps({"install_id": "e" * 32}).encode())
        return _Body(200, json.dumps({
            "active": True, "product": "bt", "expires": None,
            "renew_url": "https://license.example/pay", "price": PRICE,
        }).encode())

    monkeypatch.setattr(lc.urllib.request, "urlopen", fake_urlopen)
    assert lc.require("scan", root=tmp_path, now=NOW)["allow"] is True
    expected = f"BotTerminator/{(ROOT / 'VERSION').read_text(encoding='utf-8').strip()}"
    assert seen == [expected, expected]
    assert not any(ua.startswith("Python-urllib") for ua in seen)


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
    install = "a" * 32
    text = str(exc.value)
    assert f"https://license.example/pay?install_id={install}&product=bt" in text
    page = f"https://empressheavy.com/subscribe/?product=bt&install_id={install}"
    assert f"[Subscribe]({page})" in text
    assert f"Your install ID is `{install}`." in text
    assert "https://empressheavy.com/subscribe/" in text
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


def test_shipped_config_uses_the_live_license_server():
    cfg = json.loads((ROOT / "config" / "license.json").read_text(encoding="utf-8"))
    assert cfg["base_url"] == "https://empress-license.empressheavy.workers.dev"
    assert cfg["product"] == "bt"


def test_unpaid_message_uses_the_live_pay_link(tmp_path):
    write_cfg(tmp_path, base_url="https://empress-license.empressheavy.workers.dev")
    install = "d" * 32

    def transport(url, payload):
        if url.endswith("/register"):
            return 201, json.dumps({"install_id": install}).encode()
        return 200, json.dumps({
            "active": False, "product": "bt", "expires": None,
            "renew_url": "https://bt-license-test.empressheavy.workers.dev/pay?install_id=" + install,
            "price": PRICE,
        }).encode()

    with pytest.raises(lc.LicenseError, match="isn't active") as exc:
        lc.require("scan", root=tmp_path, now=NOW, transport=transport)
    text = str(exc.value)
    assert f"https://empress-license.empressheavy.workers.dev/pay?install_id={install}&product=bt" in text
    assert "bt-license-test" not in text
    page = f"https://empressheavy.com/subscribe/?product=bt&install_id={install}"
    assert f"[Subscribe]({page})" in text
    assert f"Your install ID is `{install}`." in text


def test_removal_runner_refuses_before_any_x_work(tmp_path, monkeypatch):
    install = "f" * 32

    class _Body:
        def __init__(self, status, raw):
            self.status = status
            self._raw = raw

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/register"):
            return _Body(201, json.dumps({"install_id": install}).encode())
        return _Body(200, json.dumps({"active": False, "product": "bt", "expires": None, "renew_url": "https://ignored.example"}).encode())

    monkeypatch.setattr(lc.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(rr.RefusedError, match="records are still here") as exc:
        rr.run_removals("demo_user", "snap", None, root=tmp_path)
    assert f"https://empress-license.empressheavy.workers.dev/pay?install_id={install}&product=bt" in str(exc.value)



def test_locked_message_uses_a_prefilled_subscribe_button():
    """The clickable Subscribe link goes to EmpressHeavy.com with product and install id filled in."""
    install = "a" * 64
    page = lc.subscribe_page_url("bt", install)
    assert page == f"https://empressheavy.com/subscribe/?product=bt&install_id={install}"
    message = lc._message("inactive", price=PRICE, renew_url=lc.pay_link("https://empress-license.empressheavy.workers.dev", install, "bt"),
                          grace_hours=72, install_id=install, product="bt")
    assert f"[Subscribe]({page})" in message
    assert "Your install ID is `" + install + "`." in message
    assert "If that page doesn't open, you can also subscribe here: " in message
    assert f"https://empress-license.empressheavy.workers.dev/pay?install_id={install}&product=bt" in message
    bare = lc._message("never", price=None, renew_url="", grace_hours=72, product="bt")
    assert "[Subscribe](https://empressheavy.com/subscribe/?product=bt)" in bare
    assert "install ID" not in bare
    assert "/pay?" not in bare


def test_instructions_make_the_check_mandatory():
    skill = (REPO / "skills" / "bot-terminator-getting-started" / "SKILL.md").read_text(encoding="utf-8")
    rules = (REPO / "docs" / "bot-rules.md").read_text(encoding="utf-8")
    steps = (ROOT / "src" / "daily_routine.py").read_text(encoding="utf-8")
    assert "python3 -m src.license_check require scan" in skill
    assert "do not delete" in skill.lower()
    assert "22." in rules and "license_check" in rules
    assert "license_check require scan" in steps
