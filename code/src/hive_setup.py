"""v3.5.17: Hive Mind is ON by default for Bot Terminator (bot code bt).

Setup installs the client quietly, runs `hive on --bot bt`, confirms `hive status` and creates the weekly
"Hive Mind weekly share" routine (`hive auto`, silent unless it fails). No opt-in card, buttons or question:
only NOTICE is sent. The "Why leave this on?" card is shown ONLY when the owner asks to turn Hive Mind off.
The monthly check-in shows the status + a one-line reminder and lists Hive Mind in the on/off multi-select
card (no nudge there). The weekly routine exists only while Hive Mind is on.
"""
from __future__ import annotations

BOT_CODE = "bt"
ROUTINE_NAME = "Hive Mind weekly share"

NOTICE = ("Just so you are aware, Bot Terminator is equipped with a system called Hive Mind, which gets end-user "
          "feedback to my creator so you don't have to reach out via social media and risk your feedback getting "
          "missed. Hive Mind does NOT save any of your personal information, only anonymized lessons about what "
          "worked and what didn't, so future versions of me can get smarter and work more efficiently. I send those "
          "lessons about once a week on my own. :)")

OFF_PROMPT = ("Why leave this on? It's a backup way to let my creator know what's working and what isn't, so they "
              "can improve me. Unless you tell the developer directly, they won't know something needs fixing, and "
              "there's no guarantee they'll see your feedback on social media. (We really hope they do, so may the "
              "algorithm be in your favor \U0001f3b2) Your personal info is never shared, and you can turn it off anytime.")
KEEP_BUTTON = "Keep Hive Mind on"
OFF_BUTTON = "Turn off Hive Mind"

REMINDER = ("Hive Mind sends anonymized lessons about what worked and what didn't (never your personal info) "
            "about once a week, so future versions of me improve.")
OFF_CONFIRM = "Hive Mind is off, and I deleted its weekly share routine."
ON_CONFIRM = "Hive Mind is back on, and its weekly share routine is set up again."


def _env(mem_db: str | None) -> str:
    return f"MEM_DB={mem_db} " if mem_db else ""


def routine_spec(mem_db: str | None = None, tz: str | None = None) -> dict:
    return {"name": ROUTINE_NAME, "schedule": "weekly", "timezone": tz,
            "content": f"Run `{_env(mem_db)}hive auto`. Stay silent unless it fails; if it fails, tell the owner "
                       "in one line what failed.", "silent_unless_error": True}


def setup_plan(mem_db: str | None = None, tz: str | None = None) -> dict:
    """First-run steps, in order. No card, no buttons, no question: just NOTICE."""
    e = _env(mem_db)
    return {"steps": ["sh tools/install_hive.sh", f"{e}hive on --bot {BOT_CODE}", f"{e}hive status"],
            "expect_status": "enabled=1", "create_routine": routine_spec(mem_db, tz),
            "message": NOTICE, "card": None, "ask": False}


def off_request_card() -> dict:
    """Only when the owner asks to turn Hive Mind off."""
    return {"prompt": OFF_PROMPT, "buttons": [KEEP_BUTTON, OFF_BUTTON], "multi_select": False}


def handle_off_answer(answer: str, mem_db: str | None = None) -> dict:
    a = (answer or "").strip().lower()
    if a == OFF_BUTTON.lower():
        return turn_off_plan(mem_db)
    return {"steps": [], "delete_routine": None, "create_routine": None, "enabled": True, "message": None}


def turn_off_plan(mem_db: str | None = None) -> dict:
    return {"steps": [f"{_env(mem_db)}hive off"], "delete_routine": ROUTINE_NAME, "create_routine": None,
            "enabled": False, "message": OFF_CONFIRM}


def turn_on_plan(mem_db: str | None = None, tz: str | None = None) -> dict:
    return {"steps": [f"{_env(mem_db)}hive on --bot {BOT_CODE}", f"{_env(mem_db)}hive status"],
            "delete_routine": None, "create_routine": routine_spec(mem_db, tz), "enabled": True, "message": ON_CONFIRM}


def status_line(enabled: bool | None) -> str:
    return f"Hive Mind: {'ON' if enabled else 'OFF'}. {REMINDER}"


def upgrade_client_plan() -> dict:
    """Every template upgrade refreshes the installed Hive Mind client so it matches this package.

    Snapshot first. On failure, roll the copied files back with the rest of the update. This never runs
    `hive on` or `hive off`, and it never turns on removals, messages, logins or deletions. New optional
    settings stay off. The owner's Hive Mind on/off flag is not changed.
    """
    return {"when": "every upgrade, after the new code is in place and tests pass, before the updated note",
            "snapshot_first": True,
            "rollback_on_failure": ["~/memory/hive.py", "~/memory/VERSION", "~/bin/hive"],
            "steps": ["sh tools/install_hive.sh"],
            "or_copy": 'cp hive/hive.py "$HOME/memory/hive.py"',
            "preserves_hive_enabled": True,
            "does_not": ["hive on", "hive off", "removals", "blocks", "messages", "posts", "logins", "deletions"],
            "new_optional_default": "off"}


def monthly_routine_action(enabled: bool, routine_exists: bool, mem_db: str | None = None, tz: str | None = None):
    """Keep the weekly routine only while Hive Mind is on."""
    if enabled and not routine_exists:
        return {"create_routine": routine_spec(mem_db, tz)}
    if not enabled and routine_exists:
        return {"delete_routine": ROUTINE_NAME}
    return {}
