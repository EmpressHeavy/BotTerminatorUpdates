"""Monthly settings review card builder (added 2026-10-16 ~5:34 PM PT; format finalized ~4:24/4:25 PM PT).

Setting 8 (Last bot cleanup) is listed ONLY when the user entered a last-cleanup date, tool or count at setup.
Setting 2 covers returnees AND the list checks (on/off, default off).
Settings 6-7 (pacing, reminders and connectors) include the optional Terminate reminder (the bot's own daily chat
nudge, on/off + time, default off) next to the front-door reminder; a companion line always shows both, kept apart.
v3.5.0: a companion line shows the records backup (GitHub / cloud CSV / download / Sheets / not yet) for owners with a records section.
v3.3.0: a companion line shows the optional memory backup (on/off + private repo; default off), under 6-7.
The card stays at 6 options: when setting 8 exists, it folds into the '6-8' button.
"""
from __future__ import annotations

try:
    from . import memory as mem
    from . import records as rec
    from . import terminate_reminder as tr
except ImportError:  # pragma: no cover
    import memory as mem
    import records as rec
    import terminate_reminder as tr

INTRO = ("Hey, this is Bot Terminator. This is your monthly review of your current settings. "
         "Is there anything you want to change?")
INSTRUCTION = ("Tap the settings you want to change, or reply with numbers like 'all except 3'. "
               "Untapped settings stay as-is. Hit done when you're finished.")
KEEP_ALL = "Keep everything as-is"
MAX_OPTIONS = 6


def last_cleanup_line(pc: dict | None) -> str | None:
    pc = pc or {}
    if pc.get("skipped"):
        return None
    date, tool, count = pc.get("last_purge_date"), pc.get("last_purge_tool"), pc.get("last_purge_follower_count")
    if not (date or tool or count):
        return None
    when = date or "date not given"
    extra = [x for x in (tool, f"{count:,} followers then" if isinstance(count, int) else None) if x]
    tail = f" ({', '.join(extra)})" if extra else ""
    return f"8. Last bot cleanup: {when}{tail}. Your first scans covered followers since then."


def lists_line(lists_enabled: bool | None) -> str | None:
    if lists_enabled is None:
        return None
    return ("List checks: " + ("ON" if lists_enabled else "OFF (default)")
            + ". Tap 2 to turn them " + ("off" if lists_enabled else "on") + " or change how they run "
            "(which lists are shown, auto-block for owners who return).")


def build(prior_cleanup: dict | None = None, lists_enabled: bool | None = None, cfg: dict | None = None) -> dict:
    """lists_enabled (from the user's config) adds a companion line that says whether list checks are on.
    cfg (the user's own config) fills the Terminate reminder line (on/off, time) and the front-door reminder state;
    without it the line shows the default: OFF."""
    line8 = last_cleanup_line(prior_cleanup)
    buttons = ["1. Mode", "2. Returnees and list checks", "3. Always Keep list: your current keeps",
               "4\u20135. Protections and bot/inactive cutoffs",
               "6\u20138. Pacing, reminders and connectors \u2014 tap to review" if line8 else "6\u20137. Pacing, reminders and connectors",
               KEEP_ALL]
    assert len(buttons) <= MAX_OPTIONS
    settings = list(range(1, 9 if line8 else 8))
    return {"intro": INTRO, "instruction": INSTRUCTION, "buttons": buttons, "settings": settings,
            "extra_companion_lines": [x for x in (line8, lists_line(lists_enabled), tr.status_line(cfg), mem.status_line(cfg),
                                                                         rec.status_line(cfg) if cfg and "records" in cfg else None) if x], "multi_select": True}
