"""Optional tip prompt (v3.5.24). Bot Terminator stays free.

After first-run setup, a small counter in data/users/<user_key>/tip_prompt.json counts
completed scans and work sessions. The prompt may appear on the use that reaches 10,
then at most once every 7 days. Maybe later keeps that 7-day gap. Remind me monthly,
or dismissing the prompt, switches the gap to 30 days. There is no forever off switch.

Nothing here touches X, Google, removals, or the network. Call it only after the work
is already done. A store problem returns show=False. It never blocks or delays a feature.
The QR image is pre-generated at assets/tip/stripe.png (the Stripe link). Do not generate
one at runtime.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

try:
    from . import storage as st
except ImportError:  # pragma: no cover
    import storage as st

PROMPT = "Wow you seem to be using Bot Terminator a lot lately! Would you mind sending my creator a tip? 🪙"
FREE_NOTE = "Tips are optional. Bot Terminator stays free either way."
THRESHOLD = 10
WEEKLY_DAYS = 7
MONTHLY_DAYS = 30
MAYBE_LATER = "Maybe later"
REMIND_MONTHLY = "Remind me monthly"
BUTTONS = (MAYBE_LATER, REMIND_MONTHLY)
WEEKLY = "weekly"
MONTHLY = "monthly"

STRIPE_URL = "https://buy.stripe.com/aFacN40Mw0Arcz02VubMQ00"
CASH_APP_URL = "https://cash.app/$EmpressHeavy"
VENMO_URL = "https://venmo.com/u/EmpressHeavy"
X_MONEY_URL = "https://x.com/HeavyMetalShip"
X_MONEY_HANDLE = "@HeavyMetalShip"
IMAGE_RELATIVE = "assets/tip/stripe.png"

LINKS = (
    {"label": "Stripe (card)", "url": STRIPE_URL},
    {"label": "Cash App", "url": CASH_APP_URL},
    {"label": "Venmo", "url": VENMO_URL},
    {"label": "X Money", "url": X_MONEY_URL, "handle": X_MONEY_HANDLE},
)

_KINDS = {"scan", "session"}
_MAYBE = {"maybe later", "later", "maybe", "ask later", "remind me later"}
_MONTHLY = {"remind me monthly", "monthly", "remind monthly", "once a month", "ask monthly",
            "remind me in a month", "remind me once a month"}
# Closing the card, or asking to stop, is not a forever opt-out. It uses the 30-day gap.
_DISMISS = {"dismiss", "dismissed", "no thanks", "no thank you", "skip", "close", "closed",
            "not now", "cancel", "don't ask again", "dont ask again", "do not ask again",
            "stop asking", "never", "never ask", "go away"}

DEFAULTS = {"version": 1, "uses": 0, "setup_complete": False, "cadence": WEEKLY,
            "last_prompt_at": None, "last_answer": None, "last_kind": None}


class _StoreError(Exception):
    pass


def image_path() -> Path:
    """Pre-generated Stripe QR. Relative to the package root (the installed code folder)."""
    return Path(__file__).resolve().parents[1] / IMAGE_RELATIVE


def state_path(user_key: str, root=None) -> Path:
    return st.user_data_root(user_key, root) / "tip_prompt.json"


def card() -> dict:
    """Two buttons, no free-text box. There is no forever-off button."""
    c = {"multiSelect": False, "allowCustom": False, "prompt": PROMPT,
         "options": [{"label": b, "value": b} for b in BUTTONS]}
    assert len(c["options"]) <= 6
    return c


def link_lines() -> list[str]:
    lines = []
    for item in LINKS:
        if item.get("handle"):
            lines.append(f"{item['label']}: {item['handle']} ({item['url']})")
        else:
            lines.append(f"{item['label']}: {item['url']}")
    return lines


def presentation() -> dict:
    """What to send when a prompt is due. The sentence is PROMPT, unchanged."""
    return {"text": PROMPT, "note": FREE_NOTE, "image": str(image_path()),
            "image_relative": IMAGE_RELATIVE, "links": [dict(item) for item in LINKS],
            "link_lines": link_lines(), "card": card(), "blocks": False}


def mark_setup_complete(user_key: str, root=None) -> dict:
    """Record that first-run setup is finished. Does not show a prompt or change the counter."""
    st.validate_user_key(user_key)
    try:
        state = _load(user_key, root)
        state["setup_complete"] = True
        _save(user_key, root, state)
    except _StoreError:
        return {"setup_complete": False, "show": False, "blocks": False, "reason": "store_unavailable", "uses": None}
    return {"setup_complete": True, "show": False, "blocks": False, "uses": state["uses"], "reason": "setup_complete"}


def record_use(user_key: str, *, kind: str = "scan", root=None, now=None, during_setup: bool = False) -> dict:
    """Count one completed scan or work session, then say whether to show the prompt.

    during_setup, or a call before mark_setup_complete, counts nothing and shows nothing.
    """
    st.validate_user_key(user_key)
    if kind not in _KINDS:
        return _quiet(reason="bad_kind")
    try:
        return _record_use(user_key, kind, root, now, during_setup)
    except _StoreError:
        return _quiet(reason="store_unavailable")


def handle_answer(user_key: str, answer: str, *, root=None, now=None) -> dict:
    """Maybe later keeps the current gap. Remind me monthly, or a dismiss, switches to 30 days."""
    st.validate_user_key(user_key)
    action = classify_answer(answer)
    if action is None:
        cadence = None
        try:
            cadence = _load(user_key, root)["cadence"]
        except _StoreError:
            pass
        return {"ok": False, "reason": "unrecognized", "show": False, "blocks": False,
                "cadence": cadence, "message": None}
    return _commit_answer(user_key, action, root=root, now=now)


def dismiss(user_key: str, *, root=None, now=None) -> dict:
    """They closed the prompt or waved it off. Same 30-day gap as Remind me monthly."""
    st.validate_user_key(user_key)
    return _commit_answer(user_key, "dismissed", root=root, now=now)


def classify_answer(answer: str) -> str | None:
    a = _norm(answer)
    if a in _MAYBE:
        return "maybe_later"
    if a in _MONTHLY:
        return "monthly"
    if a in _DISMISS:
        return "dismissed"
    return None


def _quiet(*, reason: str) -> dict:
    return {"counted": False, "show": False, "reason": reason, "uses": None, "cadence": None,
            "last_answer": None, "next_eligible": None, "prompt": None, "blocks": False}


def _record_use(user_key, kind, root, now, during_setup) -> dict:
    state = _load(user_key, root)
    now = _as_utc(now)
    if during_setup or not state["setup_complete"]:
        return _view(state, counted=False, show=False, reason="setup")
    state["uses"] = _uses(state) + 1
    state["last_kind"] = kind
    show = _due(state, now)
    if show:
        state["last_prompt_at"] = _iso(now)
    _save(user_key, root, state)
    return _view(state, counted=True, show=show, reason="shown" if show else _hidden_reason(state))


def _hidden_reason(state) -> str:
    if state["uses"] < THRESHOLD:
        return "below_threshold"
    return "cooldown"


def _commit_answer(user_key, action, *, root, now) -> dict:
    # The gap is measured from when the prompt was shown, not from this answer.
    del now
    try:
        state = _load(user_key, root)
        state["last_answer"] = action
        if action in {"monthly", "dismissed"}:
            state["cadence"] = MONTHLY
        _save(user_key, root, state)
    except _StoreError:
        return {"ok": False, "reason": "store_unavailable", "show": False, "blocks": False,
                "cadence": None, "message": None, "action": action}
    if action == "monthly":
        message = "Sounds good. I'll ask at most once a month."
    elif state["cadence"] == MONTHLY:
        message = "No problem. I'll ask at most once a month."
    else:
        message = "No problem. I'll check back in about a week."
    return {"ok": True, "action": action, "cadence": state["cadence"], "message": message,
            "next_eligible": _next_iso(state), "show": False, "blocks": False, "uses": state["uses"]}


def _view(state, *, counted, show, reason) -> dict:
    return {"counted": counted, "show": show, "reason": reason, "uses": state["uses"],
            "cadence": state["cadence"], "last_answer": state.get("last_answer"),
            "next_eligible": _next_iso(state), "prompt": presentation() if show else None, "blocks": False}


def _due(state, now) -> bool:
    if not state["setup_complete"] or _uses(state) < THRESHOLD:
        return False
    last = _parse(state.get("last_prompt_at"))
    if last is None:
        return True
    return now >= last + dt.timedelta(days=_interval_days(state["cadence"]))


def _interval_days(cadence: str) -> int:
    return MONTHLY_DAYS if cadence == MONTHLY else WEEKLY_DAYS


def _next_iso(state) -> str | None:
    last = _parse(state.get("last_prompt_at"))
    if last is None:
        return None
    return _iso(last + dt.timedelta(days=_interval_days(state["cadence"])))


def _uses(state) -> int:
    try:
        n = int(state.get("uses") or 0)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _norm(answer: str) -> str:
    text = re.sub(r"\s+", " ", (answer or "").strip().lower())
    return text.strip(" .!?")


def _as_utc(now) -> dt.datetime:
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return _as_utc(when).replace(microsecond=0).isoformat()


def _parse(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return False


def _load(user_key, root) -> dict:
    path = state_path(user_key, root)
    try:
        raw = st.load_json(path, {})
    except (OSError, ValueError) as exc:
        raise _StoreError(str(exc)) from exc
    if not isinstance(raw, dict):
        raw = {}
    state = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            state[key] = raw[key]
    state["version"] = 1
    state["uses"] = _uses(state)
    state["setup_complete"] = _as_bool(state.get("setup_complete"))
    cadence = str(state.get("cadence") or "").strip().lower()
    state["cadence"] = MONTHLY if cadence == MONTHLY else WEEKLY
    if state.get("last_prompt_at") is not None and _parse(state.get("last_prompt_at")) is None:
        state["last_prompt_at"] = None
    if state.get("last_answer") is not None and not isinstance(state.get("last_answer"), str):
        state["last_answer"] = None
    if state.get("last_kind") not in _KINDS:
        state["last_kind"] = None
    return state


def _save(user_key, root, state) -> None:
    try:
        st.save_json(state_path(user_key, root), state)
        st.apply_user_permissions(user_key, root)
    except OSError as exc:
        raise _StoreError(str(exc)) from exc
