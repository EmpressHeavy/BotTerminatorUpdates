"""v3.5.16: the one removal flow every copy must follow. The X connector has no remove-follower tool, so the bot
removes followers itself in its own signed-in box browser (computerUse). It never hands the owner a TXT/DOCX/HTML
report or tells them to remove accounts by hand. The only file it may give the owner is the optional CSV backup."""
import re

ROUND_SIZE = 5
SECONDS_APART = 10
ALLOWED_OWNER_FILE = "csv_backup"
REQUIRED_SKILL_TERMS = (
    "computerUse", "request_box_help", "sign-in skill", "Remove this follower",
    "Mark all 5 for termination", "10 seconds", "Follows you", "Graveyard",
    "rounds of 5", "CSV backup", "x.com/<handle>",
)
FLOW_STEPS = (
    "review flagged followers in chat in rounds of 5: clickable x.com link, label, reason, stats",
    "multi-select card with 'Mark all 5 for termination'",
    "bot removes checked accounts in its signed-in box browser via 'Remove this follower', ~10 s apart",
    "verify the 'Follows you' badge is gone",
    "log to the Graveyard",
    "stop on any X warning",
)
FORBIDDEN = [re.compile(p, re.I) for p in (
    r"remove (?:them|these|those|the accounts|each|it|followers?) (?:by hand|manually|yourself)",
    r"(?:you|owner) (?:can|should|will need to|must) remove",
    r"(?<!requirements)(?<!-dev)(?<!-sheets)\.txt\b", r"\b(?:txt|docx|html|word) (?:file|report|export|list)",
    r"download (?:the|this) (?:list|report)",
)]
NEGATED = re.compile(r"\b(?:never|no|not|don't|do not|without)\b", re.I)


def check_text(text):
    """Return offending lines: manual-removal or file-handoff wording not inside a 'never/no' rule."""
    bad = []
    for line in text.splitlines():
        if any(p.search(line) for p in FORBIDDEN) and not NEGATED.search(line):
            bad.append(line.strip())
    return bad


def missing_terms(text):
    return [t for t in REQUIRED_SKILL_TERMS if t not in text]
