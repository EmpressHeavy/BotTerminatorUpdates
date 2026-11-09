"""Terminate reminder (v3.2.0, optional, default OFF; v3.5.19 cadence): the bot's OWN nudge, sent in chat.

Daily, or weekly on a chosen day, at a time the owner sets, the bot sends "Hey, want to terminate some bots?" with a
card of exactly three buttons, no free text. Each button is a real action:

  Yes              -> start the normal daily scan/card flow NOW (same steps as the daily scan: preflight, Book read,
                      daily cap, protections; nothing is removed without the owner's marks).
  Remind me later  -> ask for a time (small follow-up card or typed time), then send the SAME message + card again at
                      that time (a one-off scheduled follow-up; picking "later" again schedules again).
  Not today        -> nothing today (no re-prompt, no scan). The bot asks again at the next normal time
                      (tomorrow if daily, or the next chosen weekday if weekly).

This is NOT the "reminder through your front-door bot" (config daily_scan.reminder_via_front_door, a ping that the daily
cards are ready, sent through a different bot). The terminate reminder is the bot's direct question in this chat.
Both can be on, off, or mixed; they are separate settings.

State is per user, in that user's own config (data/users/<user_key>/config.json, key "terminate_reminder") and
append-only history (data/users/<user_key>/history/history.jsonl). Nothing here touches X or Google: the functions only
return what to do (a message, a card, a routine spec, a scan plan); the bot runs those with its own tools.

config["terminate_reminder"] = {
    "enabled": false,            # default OFF; asked at setup, shown and changeable in the monthly settings check-in
    "time": null,                # HH:MM, 24-hour, the owner's time zone
    "tz": null,                  # IANA zone (falls back to config time_zone, then America/Los_Angeles like the daily scan)
    "cadence": "daily",          # "daily" | "weekly". Missing (older configs) means daily; do not re-ask those owners
    "weekday": null,             # null for daily; 0=Sunday ... 6=Saturday for weekly (standard cron dow)
    "snoozed_until": null,       # ISO time of the pending one-off follow-up ("Remind me later"), else null
    "last_answer_date": null,    # local date (YYYY-MM-DD) of the last completed answer
    "last_answer": null,         # "yes" | "later" | "not_today"
    "last_prompt_at": null, "last_answer_at": null, "awaiting_time": false }
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

try:
    from . import storage as st, daily_routine, removal_runner as rr, rules_book, preflight
except ImportError:  # pragma: no cover
    import storage as st, daily_routine, removal_runner as rr, rules_book, preflight

MESSAGE = "Hey, want to terminate some bots?"
YES, LATER, NOT_TODAY = "Yes", "Remind me later", "Not today"
BUTTONS = (YES, LATER, NOT_TODAY)
MAX_OPTIONS = 6
DAILY_NAME = "Bot Terminator terminate reminder"
ONE_OFF_NAME = "Bot Terminator terminate reminder (one-off)"
DEFAULT_ZONE = "America/Los_Angeles"   # same fallback as the daily scan routine
MAX_SNOOZE_HOURS = 24
SETUP_QUESTION = "How often do you want me to remind you to terminate bots?"
CADENCE_MORE_PROMPT = "Which day should I remind you?"
SETUP_TIME_QUESTION = "What time should I send it? (e.g. 18:00 or 6:00 PM, your time zone; only after you pick Daily or a Weekly day)"
MORE_DAYS = "More days"
NOT_NOW = "No, not now"
WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")  # index == cron dow
CADENCE_LABELS = ("Daily", "Weekly (Monday)", "Weekly (Tuesday)", "Weekly (Wednesday)", "Weekly (Thursday)", MORE_DAYS)
CADENCE_MORE_LABELS = ("Weekly (Friday)", "Weekly (Saturday)", "Weekly (Sunday)", NOT_NOW)
DEFAULTS = {"enabled": False, "time": None, "tz": None, "cadence": "daily", "weekday": None,
            "snoozed_until": None, "last_answer_date": None, "last_answer": None, "last_prompt_at": None,
            "last_answer_at": None, "awaiting_time": False}


# ---------- settings ----------
def section(cfg: dict | None) -> dict:
    s = dict(DEFAULTS); s.update((cfg or {}).get("terminate_reminder") or {})
    return s


def enabled(cfg: dict | None) -> bool:
    return bool(section(cfg).get("enabled"))


def zone_name(cfg: dict | None) -> str:
    return section(cfg).get("tz") or (cfg or {}).get("time_zone") or DEFAULT_ZONE


def zone(cfg: dict | None) -> ZoneInfo:
    return ZoneInfo(zone_name(cfg))


def initial_section(enabled_: bool, time: str | None, tz: str | None = None,
                    cadence: str | None = None, weekday=None) -> dict:
    """The config block written at setup. Off by default; on needs a valid HH:MM.

    cadence is "daily" or "weekly". Omitted means daily (a weekday with no cadence means weekly).
    weekday is null for daily, or 0=Sunday ... 6=Saturday for weekly."""
    s = dict(DEFAULTS)
    s["tz"] = tz
    if not enabled_:
        return s
    cad, wd = _choice(cadence, weekday, blank_means_daily=True)
    if not time:
        raise ValueError("the terminate reminder needs a time (HH:MM), e.g. 18:00")
    s.update(enabled=True, time=_valid_hhmm(time), cadence=cad, weekday=wd)
    return s


def _valid_hhmm(t: str) -> str:
    try:
        return daily_routine.validate_time(t)
    except ValueError:
        raise ValueError("the terminate reminder time must be HH:MM (24-hour), e.g. 18:00") from None


def _now(cfg, now):
    return now.astimezone(zone(cfg)) if now is not None else dt.datetime.now(zone(cfg))


def _cfg_path(user_key, root):
    p = st.user_config_path(root, user_key=user_key)
    if p is None:
        raise FileNotFoundError(f"no config for user {user_key!r}")
    return p


def load_cfg(user_key: str, root=None) -> dict:
    st.validate_user_key(user_key)
    return st.load_user_config_dict(root, user_key=user_key)


def _save_section(user_key, root, new: dict) -> dict:
    p = _cfg_path(user_key, root)
    cfg = st.load_user_config_dict(root, user_key=user_key)
    cfg["terminate_reminder"] = new
    st.save_json(p, cfg)
    st.apply_user_permissions(user_key, root)
    return cfg


def _log(user_key, root, status, now, **extra):
    rr._append(user_key, root, {"status": status, "action": extra.pop("action"), "bot_terminator_executed": False,
                                "recorded_by": "src/terminate_reminder.py", "recorded_at": now.isoformat(), **extra})


def label(t: dt.datetime) -> str:
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


# ---------- message + cards ----------
def card() -> dict:
    """The reminder card: exactly three buttons, no free text."""
    c = {"multiSelect": False, "allowCustom": False, "prompt": MESSAGE,
         "options": [{"label": b, "value": b} for b in BUTTONS]}
    assert len(c["options"]) <= MAX_OPTIONS
    return c


def _choice_card(prompt: str, labels: tuple[str, ...]) -> dict:
    c = {"multiSelect": False, "allowCustom": False, "prompt": prompt,
         "options": [{"label": lab, "value": lab} for lab in labels]}
    assert 1 <= len(c["options"]) <= MAX_OPTIONS
    return c


def cadence_card() -> dict:
    """First setup card: how often. Six buttons, no free-text box. More days opens cadence_more_card()."""
    return _choice_card(SETUP_QUESTION, CADENCE_LABELS)


def cadence_more_card() -> dict:
    """Friday, Saturday, Sunday, or leave the reminder off. No free-text box."""
    return _choice_card(CADENCE_MORE_PROMPT, CADENCE_MORE_LABELS)


def weekly_label(dow: int) -> str:
    return f"Weekly ({WEEKDAYS[_valid_weekday(dow)]})"


def _valid_weekday(v) -> int:
    if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
        raise ValueError("a weekly reminder needs a weekday (0=Sunday ... 6=Saturday)")
    if isinstance(v, str) and not v.strip().lstrip("-").isdigit():
        name = v.strip().lower()
        if name not in {d.lower() for d in WEEKDAYS}:
            raise ValueError("weekday must be 0 (Sunday) through 6 (Saturday), or a day name")
        return next(i for i, d in enumerate(WEEKDAYS) if d.lower() == name)
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("weekday must be 0 (Sunday) through 6 (Saturday)") from None
    if not 0 <= n <= 6:
        raise ValueError("weekday must be 0 (Sunday) through 6 (Saturday)")
    return n


def _choice(cadence, weekday, *, blank_means_daily: bool) -> tuple[str, int | None]:
    """Return (cadence, weekday). A weekday with no cadence means weekly. Blank means daily when allowed."""
    if cadence is None and weekday not in (None, ""):
        cadence = "weekly"
    if cadence is None or (isinstance(cadence, str) and not cadence.strip()):
        if not blank_means_daily:
            raise ValueError("cadence must be daily or weekly")
        return "daily", None
    cad = str(cadence).strip().lower()
    if cad == "daily":
        if weekday not in (None, ""):
            raise ValueError("a daily terminate reminder has no weekday")
        return "daily", None
    if cad == "weekly":
        return "weekly", _valid_weekday(weekday)
    raise ValueError("cadence must be daily or weekly")


def _resolved_cadence(s: dict) -> tuple[str, int | None]:
    """Stored cadence. Missing or blank is daily, so an owner who set a time before v3.5.19 stays daily."""
    raw = s.get("cadence")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "daily", None
    return _choice(raw, s.get("weekday"), blank_means_daily=False)


_OFF_ANSWERS = {"no", "nope", "nah", "not now", "no not now", "skip", "no thanks", "none", "off"}
_MORE_ANSWERS = {"more days", "more", "other days", "more day"}
_DAILY_ANSWERS = {"daily", "every day", "everyday"}


def parse_cadence_answer(text: str) -> dict:
    """A tapped label or a typed answer.

    more -> show cadence_more_card (do not ask for a time yet).
    off  -> reminder stays OFF (No / not now / skip); do not ask for a time.
    schedule -> Daily (weekday null) or Weekly (weekday 0-6). Then ask for a time.
    "daily" and "weekly monday" parse the same as the buttons. Weekly (Sunday) is dow 0; Monday is 1.
    """
    s = re.sub(r"[^\w\s]", " ", str(text or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    if s in _MORE_ANSWERS:
        return {"action": "more"}
    if s in _OFF_ANSWERS:
        return {"action": "off", "enabled": False}
    if s in _DAILY_ANSWERS:
        return {"action": "schedule", "enabled": True, "cadence": "daily", "weekday": None}
    m = re.fullmatch(r"(?:weekly|every|each)(?:\s+on)?\s+([a-z]+)", s)
    day = m.group(1) if m else (s if s in {d.lower() for d in WEEKDAYS} else None)
    if day in {d.lower() for d in WEEKDAYS}:
        dow = next(i for i, name in enumerate(WEEKDAYS) if name.lower() == day)
        return {"action": "schedule", "enabled": True, "cadence": "weekly", "weekday": dow}
    raise ValueError("Say Daily, Weekly (Monday) (or another day), More days, or No, not now.")


def describe(s: dict, tz: str | None = None) -> str:
    """'daily at HH:MM' or 'weekly (Monday) at HH:MM', with the zone in parentheses when tz is given."""
    cad, dow = _resolved_cadence(s)
    if cad == "weekly":
        base = f"weekly ({WEEKDAYS[dow]}) at {s.get('time')}"
    else:
        base = f"daily at {s.get('time')}"
    return f"{base} ({tz})" if tz else base


def time_card(cfg: dict | None = None, now: dt.datetime | None = None) -> dict:
    """Follow-up after "Remind me later": a few quick times, or type one (6:30 PM, 18:30, in 2 hours)."""
    opts = [("In 1 hour", "in 1 hour"), ("In 3 hours", "in 3 hours")]
    n = _now(cfg, now)
    if n.hour < 18:
        opts.append(("This evening (6:00 PM)", "6:00 PM"))
    opts.append(("Tomorrow morning (9:00 AM)", "tomorrow 9:00 AM"))
    c = {"multiSelect": False, "allowCustom": True,
         "prompt": "When should I ask again? Tap a time, or type one like 6:30 PM, 18:30 or in 2 hours.",
         "options": [{"label": a, "value": b} for a, b in opts]}
    assert len(c["options"]) <= MAX_OPTIONS
    return c


# ---------- time parsing ----------
_REL = re.compile(r"^in\s+(\d+(?:\.\d+)?|an?|half an?)\s*(hours?|hrs?|h|minutes?|mins?|m)$")
_CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm|a|p)?$")


def parse_when(text: str, now: dt.datetime, tz: ZoneInfo | None = None) -> dict:
    """HH:MM (24-hour), 6:30 PM, 6pm, noon, midnight, tomorrow 9am or in 2 hours -> the next such moment in the owner's
    time zone. A clock time that already passed today means tomorrow at that time. Raises ValueError (with a
    plain-words reason) for anything else, e.g. a bare '6' (am or pm?), 25:00, 7:75 pm."""
    tz = tz or now.tzinfo
    now = now.astimezone(tz)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)|,", "", str(text or "").strip().lower())   # keep the dot in 1.5
    s = re.sub(r"\b(at|around|about|please)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        raise ValueError("tell me a time, like 6:30 PM or 18:30")
    m = _REL.match(s)
    if m:
        q = m.group(1)
        n = 1.0 if q in ("a", "an") else 0.5 if q.startswith("half") else float(q)
        delta = dt.timedelta(hours=n) if m.group(2).startswith("h") else dt.timedelta(minutes=n)
        if delta < dt.timedelta(minutes=1) or delta > dt.timedelta(hours=MAX_SNOOZE_HOURS):
            raise ValueError(f"I can ask again between 1 minute and {MAX_SNOOZE_HOURS} hours from now")
        t = (now + delta).replace(second=0, microsecond=0)
        return {"when": t, "day": "today" if t.date() == now.date() else "tomorrow", "label": label(t)}
    force = None
    for word in ("tomorrow", "today", "tonight"):
        if s.startswith(word + " ") or s == word:
            force = "tomorrow" if word == "tomorrow" else "today"
            s = s[len(word):].strip()
            break
    if s in ("noon", "midday"):
        hh, mm = 12, 0
    elif s == "midnight":
        hh, mm = 0, 0
    else:
        m = _CLOCK.match(s)
        if not m:
            raise ValueError("I couldn't read that time. Try 6:30 PM, 18:30 or in 2 hours")
        hh, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if mm > 59:
            raise ValueError("minutes must be 00 to 59")
        if ap:
            if not 1 <= hh <= 12:
                raise ValueError("with AM/PM the hour must be 1 to 12")
            hh = hh % 12 + (12 if ap.startswith("p") else 0)
        else:
            if m.group(2) is None:
                raise ValueError("is that AM or PM? Say 6 PM, or use 24-hour like 18:00")
            if hh > 23:
                raise ValueError("the hour must be 0 to 23 (or add AM/PM)")
    day = now.date() + dt.timedelta(days=1 if force == "tomorrow" else 0)
    t = dt.datetime.combine(day, dt.time(hh, mm), tzinfo=tz)
    if t <= now:
        if force == "today":
            raise ValueError("that time has already passed today. Pick a later time, or say tomorrow")
        if force is None:
            t = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(hh, mm), tzinfo=tz)
    return {"when": t, "day": "today" if t.date() == now.date() else "tomorrow", "label": label(t)}


# ---------- routines ----------
def _spec_steps(user_key_hint: str = "<user_key>") -> list[str]:
    return ["send_prompt = terminate_reminder.build_prompt(user_key, source=...); if send_prompt['send'] is false, stop quietly",
            f"send the message \"{MESSAGE}\" in this chat, then the card (terminate_reminder.card): Yes / Remind me later / Not today",
            "on a tap: terminate_reminder.handle_answer(user_key, answer) and do the action it returns "
            "(start the scan now / ask for a time then schedule the one-off / do nothing today)",
            "this routine never scans, removes or takes any X action by itself"]


def _cron(time_hhmm: str, cadence: str, weekday: int | None) -> str:
    hh, mm = time_hhmm.split(":")
    if cadence == "weekly":
        return f"{int(mm)} {int(hh)} * * {weekday}"
    return f"{int(mm)} {int(hh)} * * *"


def routine_spec(cfg: dict) -> dict | None:
    """Recurring routine at the owner's time, or None when the terminate reminder is off.

    Daily cron is `{mm} {hh} * * *`. Weekly is `{mm} {hh} * * {dow}` with 0=Sunday ... 6=Saturday.
    A missing cadence is daily (owners who already picked a time keep that schedule)."""
    s = section(cfg)
    if not s["enabled"]:
        return None
    t = _valid_hhmm(s.get("time") or "")
    cad, dow = _resolved_cadence(s)
    return {"name": DAILY_NAME, "cron": _cron(t, cad, dow), "time_zone": zone_name(cfg),
            "cadence": cad, "weekday": dow, "source": "daily", "steps": _spec_steps(),
            "separate_from_front_door_reminder": True, "scans_or_removes_by_itself": False}


def one_off_spec(when: dt.datetime, cfg: dict) -> dict:
    """The "Remind me later" follow-up: runs once at `when`, same message + card. Replaces any earlier pending one."""
    w = when.astimezone(zone(cfg))
    return {"name": ONE_OFF_NAME, "one_off": True, "run_at": w.isoformat(),
            "cron": f"{w.minute} {w.hour} {w.day} {w.month} *", "time_zone": zone_name(cfg), "source": "later",
            "replaces_previous": True, "delete_after_run": True, "steps": _spec_steps(),
            "scans_or_removes_by_itself": False}


# ---------- when to ask ----------
def _parse_ts(v):
    try:
        return dt.datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def should_prompt(cfg: dict, now: dt.datetime | None = None, *, source: str = "daily") -> tuple[bool, str]:
    s = section(cfg)
    n = _now(cfg, now)
    if not s["enabled"]:
        return False, "off"
    snooze = _parse_ts(s.get("snoozed_until"))
    if source == "later":
        if snooze is None:
            return False, "no follow-up is scheduled"
        if n < snooze - dt.timedelta(minutes=2):
            return False, "too early for the scheduled follow-up"
        return True, "follow-up due"
    if snooze is not None and snooze > n:
        return False, "a follow-up is already scheduled"
    today = n.date().isoformat()
    if s.get("last_answer_date") == today and s.get("last_answer") in ("yes", "not_today"):
        return False, "already answered today"
    lp = _parse_ts(s.get("last_prompt_at"))
    la = _parse_ts(s.get("last_answer_at"))
    if lp is not None and lp.astimezone(zone(cfg)).date().isoformat() == today and (la is None or la < lp):
        return False, "already asked today, waiting for an answer"
    return True, "daily"


def build_prompt(user_key: str, root=None, *, now: dt.datetime | None = None, source: str = "daily") -> dict:
    """Called by the daily routine (source="daily") and the one-off follow-up (source="later"). When it says send,
    send `message`, then `card`. Records the prompt in this user's history."""
    if source not in ("daily", "later"):
        raise ValueError("source must be 'daily' or 'later'")
    cfg = load_cfg(user_key, root)
    n = _now(cfg, now)
    ok, why = should_prompt(cfg, n, source=source)
    if not ok:
        return {"send": False, "reason": why}
    s = section(cfg)
    s.update(last_prompt_at=n.isoformat(), awaiting_time=False)
    if source == "later":
        s["snoozed_until"] = None   # this follow-up has now fired
    _save_section(user_key, root, s)
    _log(user_key, root, "TERMINATE_REMINDER_SENT", n, action="SENT reminder message + card (no X action)", source=source)
    return {"send": True, "message": MESSAGE, "card": card(), "source": source}


# ---------- answers ----------
def _outstanding(s: dict) -> bool:
    lp, la = _parse_ts(s.get("last_prompt_at")), _parse_ts(s.get("last_answer_at"))
    return lp is not None and (la is None or la < lp)


def _norm(answer) -> str:
    a = str(answer or "").strip().lower()
    for b, k in ((YES, "yes"), (LATER, "later"), (NOT_TODAY, "not_today")):
        if a in (b.lower(), k):
            return k
    raise ValueError(f"pick one of the three buttons: {', '.join(BUTTONS)}")


def handle_answer(user_key: str, answer, root=None, *, now: dt.datetime | None = None) -> dict:
    """A tap on the card. Returns the concrete action for that button and records it in the history.
    yes -> action "start_scan_now"; later -> "ask_time" (then call schedule_later); not_today -> "none_today"."""
    key = _norm(answer)
    cfg = load_cfg(user_key, root)
    n = _now(cfg, now)
    s = section(cfg)
    if not s["enabled"]:
        return {"action": "none", "message": "The terminate reminder is off."}
    if not _outstanding(s):
        return {"action": "already_handled", "message": "That reminder was already answered; I'll ask again at the next one."}
    if key == "yes":
        s.update(last_answer="yes", last_answer_date=n.date().isoformat(), last_answer_at=n.isoformat(),
                 snoozed_until=None, awaiting_time=False)
        _save_section(user_key, root, s)
        _log(user_key, root, "TERMINATE_REMINDER_YES", n, action="START SCAN NOW (the normal daily scan/card flow)")
        pf = preflight.check(user_key, root, cfg)
        return {"action": "start_scan_now", "flow": "daily_scan", "steps": daily_routine.scan_steps(cfg),
                "preflight": pf, "preflight_first": not pf["ok"],
                "requires": ["preflight (Google Sheets + Drive rechecked this session)", "Bot Terminator Book read",
                             "daily removal cap", "protections rechecked before every removal"],
                "message": "Great, starting your scan now. Nothing is removed without your marks.",
                "removes_without_marks": False}
    if key == "later":
        s.update(awaiting_time=True)
        _save_section(user_key, root, s)
        _log(user_key, root, "TERMINATE_REMINDER_LATER_ASKED", n, action="ASK FOR A TIME (no X action)")
        return {"action": "ask_time", "message": "Sure. When should I ask again?", "card": time_card(cfg, n)}
    s.update(last_answer="not_today", last_answer_date=n.date().isoformat(), last_answer_at=n.isoformat(),
             snoozed_until=None, awaiting_time=False)
    _save_section(user_key, root, s)
    nxt = next_daily(cfg, n)
    _log(user_key, root, "TERMINATE_REMINDER_NOT_TODAY", n, action="NONE today (no scan, no re-prompt)",
         next_prompt=nxt.isoformat() if nxt else None)
    if not nxt:
        message = "No problem, not today."
    else:
        cad, dow = _resolved_cadence(section(cfg))
        when = "tomorrow" if cad == "daily" else f"next {WEEKDAYS[dow]}"
        message = f"No problem, not today. I'll ask again {when} at {label(nxt)}."
    return {"action": "none_today", "scan": False, "schedule": None, "next_prompt": nxt.isoformat() if nxt else None,
            "message": message}


def next_daily(cfg: dict, now: dt.datetime) -> dt.datetime | None:
    """The next normal reminder time after today: tomorrow (daily) or the next chosen weekday (weekly)."""
    s = section(cfg)
    if not s.get("time"):
        return None
    hh, mm = (int(x) for x in s["time"].split(":"))
    z = zone(cfg)
    n = now.astimezone(z)
    cad, dow = _resolved_cadence(s)
    if cad == "weekly":
        py = (dow - 1) % 7  # cron 0=Sunday -> date.weekday() Sunday=6
        ahead = (py - n.weekday()) % 7 or 7
        day = n.date() + dt.timedelta(days=ahead)
    else:
        day = n.date() + dt.timedelta(days=1)
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=z)


def schedule_later(user_key: str, time_text: str, root=None, *, now: dt.datetime | None = None) -> dict:
    """The time the owner picked after "Remind me later" (tapped or typed). Valid -> records it in config + history and
    returns the one-off routine spec to schedule (it replaces any earlier pending follow-up). Invalid -> asks again."""
    cfg = load_cfg(user_key, root)
    n = _now(cfg, now)
    s = section(cfg)
    if not s["enabled"] or not s.get("awaiting_time"):
        return {"action": "none", "message": "I'm not waiting for a reminder time right now."}
    try:
        w = parse_when(time_text, n, zone(cfg))
    except ValueError as exc:
        return {"action": "ask_time_again", "error": str(exc), "message": f"{exc}.", "card": time_card(cfg, n)}
    prev = s.get("snoozed_until")
    s.update(snoozed_until=w["when"].isoformat(), awaiting_time=False, last_answer="later",
             last_answer_date=n.date().isoformat(), last_answer_at=n.isoformat())
    _save_section(user_key, root, s)
    _log(user_key, root, "TERMINATE_REMINDER_LATER_SCHEDULED", n, action="SCHEDULE one-off reminder (no X action)",
         remind_at=w["when"].isoformat(), replaced=prev)
    return {"action": "schedule_one_off", "run_at": w["when"].isoformat(), "spec": one_off_spec(w["when"], cfg),
            "replaces": prev,
            "message": f"Okay, I'll ask again {w['day']} at {w['label']}."}


# ---------- setup / monthly check-in ----------
def set_reminder(user_key: str, enabled_: bool, time: str | None = None, root=None, *, now: dt.datetime | None = None,
                 tz: str | None = None, cadence: str | None = None, weekday=None) -> dict:
    """Turn the reminder on/off or change its time and cadence (setup later, or the monthly check-in).

    Omitting cadence and weekday keeps the stored schedule (missing cadence stays daily). Returns the routine to
    (re)schedule or delete, the Book change-log plan, and records the change in the history."""
    cfg = load_cfg(user_key, root)
    n = _now(cfg, now)
    s = section(cfg)
    if enabled_:
        time = _valid_hhmm(time or s.get("time") or "")
        if tz:
            ZoneInfo(tz)
        if cadence is None and weekday is None:
            cad, wd = _resolved_cadence(s)
        else:
            # An explicit daily switch must not keep a stored weekday. A weekday alone means weekly.
            if cadence is None:
                cadence = "weekly" if weekday not in (None, "") else s.get("cadence")
            if str(cadence or "daily").strip().lower() == "daily":
                wd_arg = None if weekday in (None, "") else weekday
            else:
                wd_arg = s.get("weekday") if weekday is None else weekday
            cad, wd = _choice(cadence, wd_arg, blank_means_daily=True)
        s.update(enabled=True, time=time, tz=tz or s.get("tz"), cadence=cad, weekday=wd)
    else:
        s.update(enabled=False, snoozed_until=None, awaiting_time=False)
    cfg = _save_section(user_key, root, s)
    line = (f"Terminate reminder on, {describe(s, zone_name(cfg))}." if enabled_
            else "Terminate reminder off.")
    _log(user_key, root, "TERMINATE_REMINDER_SETTING", n, action=line, enabled=bool(enabled_), time=s.get("time"),
         cadence=s.get("cadence"), weekday=s.get("weekday"))
    book = (cfg.get("book") or {}).get("document_id")
    return {"enabled": bool(enabled_), "time": s.get("time"), "cadence": s.get("cadence"), "weekday": s.get("weekday"),
            "routine": routine_spec(cfg) if enabled_ else {"delete": DAILY_NAME},
            "cancel_pending_one_off": None if enabled_ else ONE_OFF_NAME,
            "book_change": line, "book_plan": rules_book.rule_change_plan(book, line) if book else None,
            "message": line + " Changes affect future reminders only."}


def status_line(cfg: dict | None) -> str:
    """The monthly check-in line for this setting (kept separate from the front-door reminder, shown beside it)."""
    s = section(cfg)
    fd = bool(((cfg or {}).get("daily_scan") or {}).get("reminder_via_front_door"))
    if s["enabled"]:
        head = f"Terminate reminder (chat nudge): ON, {describe(s, zone_name(cfg))}"
        tail = "Tap 6\u20137 to change how often, the time, or turn it off."
    else:
        head = "Terminate reminder (chat nudge): OFF (default)"
        tail = "Tap 6\u20137 to turn it on and pick how often and a time."
    return (f"{head}. {tail} Separate from the front-door reminder, which is {'ON' if fd else 'OFF'}.")
