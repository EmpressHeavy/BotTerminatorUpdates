"""Subscription gate for this Bot Terminator install.

The license server learns an install id, the product code, and Stripe status.
This file never sends an X handle, password, token, cookie, or follower profile.
Records, Graveyard, and Always Keep are not deleted when a check fails.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ACTIONS = ("scan", "removal", "block")
STATE_NAME = "install_license.json"
SUBSCRIBE_PAGE = "https://empressheavy.com/subscribe/"


def package_version() -> str:
    """First line of the package VERSION file. Fallback matches the current template."""
    try:
        line = (PACKAGE / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        line = ""
    return line if re.fullmatch(r"v\d+(?:\.\d+){1,3}", line or "") else "v3.5.21"


def user_agent() -> str:
    """Cloudflare error 1010 blocks urllib's default User-Agent. Send this on every license call."""
    return f"BotTerminator/{package_version()}"


class LicenseError(RuntimeError):
    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


def _config_path(root: Path) -> Path:
    local = root / "config" / "license.json"
    if local.is_file():
        return local
    return PACKAGE / "config" / "license.json"


def load_config(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else PACKAGE
    cfg = json.loads(_config_path(root).read_text(encoding="utf-8"))
    url = os.environ.get("BOT_TERMINATOR_LICENSE_URL", "").strip()
    if url:
        cfg["base_url"] = url
    grace = os.environ.get("BOT_TERMINATOR_LICENSE_GRACE_HOURS", "").strip()
    if grace:
        cfg["grace_hours"] = float(grace)
    return cfg


def state_path(root: Path | None = None) -> Path:
    root = Path(root) if root is not None else PACKAGE
    return root / "data" / STATE_NAME


def load_state(root: Path | None = None) -> dict:
    path = state_path(root)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_state(state: dict, root: Path | None = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {
        "install_id": state.get("install_id") or "",
        "last_active_at": state.get("last_active_at"),
        "last_renew_url": state.get("last_renew_url") or "",
        "last_price": state.get("last_price"),
    }
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _request_headers() -> dict:
    return {"content-type": "application/json", "User-Agent": user_agent()}


def _post(url: str, payload: dict, timeout: float, transport):
    body = json.dumps(payload).encode("utf-8")
    headers = _request_headers()
    if transport is not None:
        status, raw = transport(url, payload)
        return status, raw
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def subscribe_link(base: str, install_id: str, product: str = "bt") -> str:
    """Checkout for this install, or the public subscribe page when the install id is not known yet."""
    if base and install_id:
        return f"{base.rstrip('/')}/pay?install_id={install_id}&product={product or 'bt'}"
    return SUBSCRIBE_PAGE


def _message(kind: str, *, price: dict | None, renew_url: str, grace_hours: float) -> str:
    label = (price or {}).get("label") or "Bot Terminator"
    display = (price or {}).get("display") or ""
    priced = f" ({display})" if display else ""
    if renew_url and renew_url != SUBSCRIBE_PAGE:
        link = f" You can subscribe here: {renew_url} or at {SUBSCRIBE_PAGE}."
    else:
        link = f" You can subscribe here: {SUBSCRIBE_PAGE}."
    if kind == "inactive":
        return (f"Your {label} subscription{priced} isn't active, so I'm not going to scan, remove, or block "
                f"anyone right now. Your records are still here, and I haven't changed your X account.{link}")
    if kind == "grace_over":
        return (f"I couldn't confirm your {label} subscription, and it's been more than {grace_hours:g} hours "
                f"since the last confirmation, so I'm holding off on scans, removals, and blocks. "
                f"Your records are still here, and I haven't changed your X account.{link}")
    return (f"I couldn't reach the subscription check for {label}, and this install hasn't been confirmed yet, "
            f"so I'm holding off on scans, removals, and blocks. Your records are still here, and I haven't "
            f"changed your X account.{link}")


def evaluate(payload: dict | None, *, now: datetime, last_active_at, grace_hours: float,
             unreachable: bool, renew_url: str = "", price: dict | None = None) -> dict:
    """Decide whether an action may proceed. Unreachable uses the grace window. Inactive does not."""
    if not unreachable and payload is not None:
        if payload.get("active") is True:
            return {"allow": True, "reason": "active", "renew_url": renew_url,
                    "price": payload.get("price") or price}
        return {"allow": False, "reason": "inactive",
                "message": _message("inactive", price=payload.get("price") or price,
                                    renew_url=renew_url, grace_hours=grace_hours)}
    last = _parse_time(last_active_at)
    if last is not None and now - last <= timedelta(hours=float(grace_hours)):
        return {"allow": True, "reason": "grace", "renew_url": renew_url, "price": price}
    kind = "grace_over" if last is not None else "never"
    return {"allow": False, "reason": kind,
            "message": _message(kind, price=price, renew_url=renew_url, grace_hours=grace_hours)}


def register(*, root=None, transport=None, config=None) -> dict:
    cfg = config or load_config(root)
    base = str(cfg.get("base_url") or "").rstrip("/")
    page = SUBSCRIBE_PAGE
    if not base:
        raise LicenseError(_message("never", price=None, renew_url=page, grace_hours=float(cfg.get("grace_hours") or 72)),
                           reason="unconfigured")
    try:
        status, raw = _post(f"{base}/register", {}, float(cfg.get("timeout_seconds") or 10), transport)
    except Exception:
        raise LicenseError(_message("never", price=None, renew_url=page, grace_hours=float(cfg.get("grace_hours") or 72)),
                           reason="unreachable") from None
    if status != 201:
        raise LicenseError(_message("never", price=None, renew_url=page, grace_hours=float(cfg.get("grace_hours") or 72)),
                           reason="unreachable")
    body = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    install_id = str(body.get("install_id") or "")
    if not install_id:
        raise LicenseError(_message("never", price=None, renew_url=page, grace_hours=float(cfg.get("grace_hours") or 72)),
                           reason="unreachable")
    state = load_state(root)
    state["install_id"] = install_id
    save_state(state, root)
    return {"install_id": install_id}


def require(action: str, *, root=None, now: datetime | None = None, transport=None) -> dict:
    if action not in ACTIONS:
        raise LicenseError(f"Unknown license action {action}.", reason="bad_action")
    cfg = load_config(root)
    grace = float(cfg.get("grace_hours") or 72)
    base = str(cfg.get("base_url") or "").rstrip("/")
    state = load_state(root)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    product = cfg.get("product") or "bt"
    link = subscribe_link(base, state.get("install_id") or "", product)
    if not base:
        decision = evaluate(None, now=now, last_active_at=state.get("last_active_at"), grace_hours=grace,
                            unreachable=True, renew_url=link, price=state.get("last_price"))
        if not decision["allow"]:
            raise LicenseError(decision["message"], reason="unconfigured")
        return decision
    if not state.get("install_id"):
        try:
            registered = register(root=root, transport=transport, config=cfg)
        except LicenseError:
            decision = evaluate(None, now=now, last_active_at=None, grace_hours=grace, unreachable=True,
                                renew_url=SUBSCRIBE_PAGE)
            raise LicenseError(decision["message"], reason=decision["reason"]) from None
        state["install_id"] = registered["install_id"]
    link = subscribe_link(base, state["install_id"], product)
    url = f"{base}/check"
    payload = {"install_id": state["install_id"], "product": product}
    try:
        status, raw = _post(url, payload, float(cfg.get("timeout_seconds") or 10), transport)
        body = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if status != 200 or not isinstance(body, dict):
            raise ValueError("bad check response")
        unreachable = False
    except Exception:
        body = None
        unreachable = True
    decision = evaluate(body, now=now, last_active_at=state.get("last_active_at"), grace_hours=grace,
                        unreachable=unreachable, renew_url=link, price=state.get("last_price"))
    if not unreachable and isinstance(body, dict):
        state["last_renew_url"] = link
        state["last_price"] = body.get("price")
        state["last_active_at"] = now.isoformat() if body.get("active") is True else None
        save_state(state, root)
    if not decision["allow"]:
        raise LicenseError(decision["message"], reason=decision["reason"])
    return decision


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    try:
        if cmd == "register":
            print(json.dumps(register()))
            return 0
        if cmd == "require" and len(args) > 1:
            require(args[1])
            print("subscription active")
            return 0
    except LicenseError as exc:
        print(str(exc))
        return 2
    print("usage: python -m src.license_check register | require scan|removal|block", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
